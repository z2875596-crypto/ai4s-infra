"""FastAPI routes for data_infra — ingestion, cleaning, versioning, catalog."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from ai4s.common.config import Config
from ai4s.common.logging import get_logger
from ai4s.data_infra.cleaning.quality import QualityChecker
from ai4s.data_infra.cleaning.transformer import DataTransformer
from ai4s.data_infra.cleaning.validator import SchemaValidator
from ai4s.data_infra.ingestion.pipeline import IngestionPipeline, IngestionReport
from ai4s.data_infra.ingestion.registry import ConnectorRegistry
from ai4s.data_infra.versioning.catalog import ColumnMeta, DataCatalog, DatasetEntry
from ai4s.data_infra.versioning.lineage import LineageTracker, LineageStepType
from ai4s.data_infra.versioning.snapshot import SnapshotManager

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# lifespan — global singletons
# ---------------------------------------------------------------------------

_registry: ConnectorRegistry | None = None
_catalog: DataCatalog | None = None
_snapshots: SnapshotManager | None = None
_lineage: LineageTracker | None = None
_config: Config | None = None


def get_registry() -> ConnectorRegistry:
    global _registry
    if _registry is None:
        _registry = ConnectorRegistry()
    return _registry


def get_catalog() -> DataCatalog:
    global _catalog
    if _catalog is None:
        _catalog = DataCatalog()
    return _catalog


def get_snapshots() -> SnapshotManager:
    global _snapshots
    if _snapshots is None:
        _snapshots = SnapshotManager()
    return _snapshots


def get_lineage() -> LineageTracker:
    global _lineage
    if _lineage is None:
        _lineage = LineageTracker()
    return _lineage


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


# ---------------------------------------------------------------------------
# router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/data", tags=["data-infra"])

# ---------------------------------------------------------------------------
# request / response models
# ---------------------------------------------------------------------------


class ConnectorRegisterRequest(BaseModel):
    name: str
    source_type: str = Field(..., description="s3 | postgresql | rest | local")
    config: dict[str, Any] = Field(default_factory=dict)


class IngestionRunRequest(BaseModel):
    source_name: str
    table: str
    target_path: str
    batch_size: int = 10000
    target_format: str = "parquet"
    partition_cols: list[str] | None = None


class SchemaRegisterRequest(BaseModel):
    table: str
    columns: dict[str, str]
    required: list[str] | None = None


class QualityCheckRequest(BaseModel):
    max_null_ratio: float = 0.10
    max_duplicate_ratio: float = 0.05


class CreateSnapshotRequest(BaseModel):
    dataset: str
    source_path: str
    tags: dict[str, str] | None = None
    parent_id: str | None = None


class CatalogRegisterRequest(BaseModel):
    name: str
    description: str = ""
    owner: str = ""
    columns: list[dict[str, str]] = Field(default_factory=list)
    location: str = ""
    format: str = "parquet"
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# connector routes
# ---------------------------------------------------------------------------


@router.get("/connectors")
async def list_connectors():
    registry = get_registry()
    return {"sources": registry.list_sources()}


@router.post("/connectors")
async def register_connector(req: ConnectorRegisterRequest):
    registry = get_registry()
    try:
        registry.register(req.name, req.source_type, req.config)
        await registry.connect_all()
        return {"status": "registered", "name": req.name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/connectors/{name}")
async def unregister_connector(name: str):
    registry = get_registry()
    if registry.unregister(name):
        return {"status": "removed", "name": name}
    raise HTTPException(status_code=404, detail=f"Connector '{name}' not found")


# ---------------------------------------------------------------------------
# ingestion routes
# ---------------------------------------------------------------------------


@router.post("/ingest", response_model=dict)
async def run_ingestion(req: IngestionRunRequest):
    registry = get_registry()
    cfg = get_config()

    source_name = req.source_name
    table = req.table

    # Auto-detect PubChem: if source_name looks like a pubchem reference,
    # create a PubChemConnector on the fly instead of requiring pre-registration.
    if source_name.lower().startswith("pubchem") or source_name.lower() == "pubchem":
        pubchem_cfg = cfg.data_infra.get("pubchem", {})
        max_records = pubchem_cfg.get("max_records", req.batch_size)
        source_name = "_pubchem_auto"

        # Format table for PubChem: if no colon, default to name search
        if ":" not in table:
            table = f"name:{table}"

        _pubchem_opts = {
            "max_records": max_records,
            "timeout": pubchem_cfg.get("timeout", 30),
            "verify_ssl": pubchem_cfg.get("verify_ssl", False),
            "properties": pubchem_cfg.get("properties", [
                "MolecularFormula", "MolecularWeight", "SMILES",
                "InChI", "InChIKey", "IUPACName", "XLogP", "TPSA",
            ]),
        }
        try:
            registry.register(source_name, "pubchem", _pubchem_opts)
        except ValueError:
            registry.unregister(source_name)
            registry.register(source_name, "pubchem", _pubchem_opts)

    validator = SchemaValidator(mode=cfg.data_infra.get("cleaning", {}).get("validation_mode", "warn"))
    transformer = DataTransformer()
    quality = QualityChecker(
        max_null_ratio=cfg.data_infra.get("cleaning", {}).get("max_null_ratio", 0.10),
        quality_threshold=cfg.data_infra.get("cleaning", {}).get("quality_threshold", 0.95),
    )

    # Resolve connector and capture schema BEFORE pipeline run
    # (pipeline.disconnect() might invalidate connector state)
    connector = registry.get(source_name)
    schema: dict[str, str] = {}
    if connector:
        try:
            await connector.connect()
            schema = await connector.schema(table)
        except Exception:
            pass

    pipeline = IngestionPipeline(
        registry, validator=validator, transformer=transformer,
        quality_checker=quality, lineage=get_lineage(),
    )

    try:
        report = await pipeline.run(
            source_name, table, req.target_path,
            batch_size=req.batch_size, target_format=req.target_format,
            partition_cols=req.partition_cols,
        )

        # Auto-register in catalog after successful ingestion
        dataset_name = f"{req.source_name}/{req.table}"
        columns = [
            ColumnMeta(name=col_name, dtype=col_type)
            for col_name, col_type in schema.items()
        ]
        if not columns:
            # Fallback: infer basic columns from report
            columns = [
                ColumnMeta(name="rows_read", dtype="int32"),
                ColumnMeta(name="rows_written", dtype="int32"),
            ]

        tags = [req.source_name]
        if "pubchem" in req.source_name.lower():
            tags.extend(["chemistry", "molecule"])

        catalog = get_catalog()
        entry = DatasetEntry(
            name=dataset_name,
            description=f"Ingested from {req.source_name}: {req.table}",
            owner="system",
            columns=columns,
            location=req.target_path,
            format=req.target_format,
            tags=tags,
            row_count_estimate=report.rows_written,
            quality_score=report.pass_rate,
        )
        catalog.register(entry)
        logger.info("Auto-registered dataset '%s' in catalog (%d columns)", dataset_name, len(columns))

        return {
            "status": report.status,
            "rows_read": report.rows_read,
            "rows_written": report.rows_written,
            "pass_rate": report.pass_rate,
            "duration_sec": report.duration_sec,
            "validation_errors": report.validation_errors[:20],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ingest/{source}/{table}/status")
async def ingestion_status(source: str, table: str):
    lineage = get_lineage()
    dataset_id = f"{source}/{table}"
    return lineage.full_lineage(dataset_id)


# ---------------------------------------------------------------------------
# schema routes
# ---------------------------------------------------------------------------


@router.post("/schemas")
async def register_schema(req: SchemaRegisterRequest):
    validator = SchemaValidator(mode="strict")
    validator.register_schema(req.table, req.columns, required=req.required)
    validator.save_schema(req.table)
    return {"status": "registered", "table": req.table, "columns": len(req.columns)}


@router.get("/schemas/{table}")
async def get_schema(table: str):
    validator = SchemaValidator(mode="strict")
    if not validator.has_schema(table):
        raise HTTPException(status_code=404, detail=f"No schema for table: {table}")
    return {"table": table, "columns": validator._schemas.get(table, {})}


# ---------------------------------------------------------------------------
# catalog routes
# ---------------------------------------------------------------------------


@router.post("/catalog")
async def register_dataset(req: CatalogRegisterRequest):
    catalog = get_catalog()
    entry = DatasetEntry(
        name=req.name,
        description=req.description,
        owner=req.owner,
        columns=[ColumnMeta(name=c["name"], dtype=c["dtype"], description=c.get("description", ""))
                  for c in req.columns],
        location=req.location,
        format=req.format,
        tags=req.tags,
    )
    catalog.register(entry)
    return {"status": "registered", "name": req.name}


@router.get("/catalog")
async def search_catalog(
    tag: str | None = Query(None),
    keyword: str | None = Query(None),
    owner: str | None = Query(None),
    limit: int = Query(50),
):
    catalog = get_catalog()
    results = catalog.search(tag=tag, keyword=keyword, owner=owner, limit=limit)
    return {"count": len(results), "datasets": [r.to_dict() for r in results]}


@router.get("/catalog/summary")
async def catalog_summary():
    return get_catalog().summary()


@router.get("/catalog/{name}")
async def get_dataset(name: str):
    catalog = get_catalog()
    entry = catalog.get(name)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Dataset '{name}' not found")
    return entry.to_dict()


# ---------------------------------------------------------------------------
# snapshot routes
# ---------------------------------------------------------------------------


@router.post("/snapshots")
async def create_snapshot(req: CreateSnapshotRequest):
    mgr = get_snapshots()
    snap = await mgr.create_snapshot(
        req.dataset, req.source_path, tags=req.tags, parent_id=req.parent_id
    )
    return snap.to_dict()


@router.get("/snapshots")
async def list_snapshots(dataset: str | None = Query(None)):
    mgr = get_snapshots()
    snaps = await mgr.list_snapshots(dataset=dataset)
    return {"count": len(snaps), "snapshots": [s.to_dict() for s in snaps]}


@router.get("/snapshots/{snapshot_id}")
async def get_snapshot(snapshot_id: str):
    mgr = get_snapshots()
    # Quick lookup
    for s in mgr._snapshots.values():
        if s.snapshot_id == snapshot_id:
            return s.to_dict()
    raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' not found")


@router.get("/snapshots/{id_a}/diff/{id_b}")
async def diff_snapshots(id_a: str, id_b: str):
    mgr = get_snapshots()
    return await mgr.diff_snapshots(id_a, id_b)


# ---------------------------------------------------------------------------
# lineage routes
# ---------------------------------------------------------------------------


@router.get("/lineage/{dataset_id}")
async def get_lineage_graph(dataset_id: str):
    lineage = get_lineage()
    return lineage.full_lineage(dataset_id)


@router.get("/lineage/{dataset_id}/mermaid")
async def get_lineage_mermaid(dataset_id: str):
    lineage = get_lineage()
    full = lineage.to_mermaid()
    return {"mermaid": full}


# ---------------------------------------------------------------------------
# pubchem routes
# ---------------------------------------------------------------------------

from ai4s.data_infra.ingestion.pubchem_connector import PubChemConnector


class PubChemSearchParams(BaseModel):
    q: str = Field(..., description="Search query (name, CID, or SMILES)")
    mode: str = Field("name", description="name | cid | substructure")
    max_records: int = Field(100, ge=1, le=500, description="Max compounds to return")


@router.get("/pubchem/search")
async def pubchem_search(
    q: str = Query(..., description="Search query"),
    mode: str = Query("name", description="name | cid | substructure"),
    max_records: int = Query(100, ge=1, le=500),
):
    """Search PubChem by compound name, CID, or SMILES substructure."""
    cfg = get_config()
    pubchem_cfg = cfg.data_infra.get("pubchem", {})
    conn = PubChemConnector("api-search", {
        "max_records": max_records,
        "timeout": pubchem_cfg.get("timeout", 30),
        "verify_ssl": pubchem_cfg.get("verify_ssl", False),
        "properties": pubchem_cfg.get(
            "properties",
            ["MolecularFormula", "MolecularWeight", "SMILES", "InChI",
             "InChIKey", "IUPACName", "XLogP", "TPSA"],
        ),
    })
    try:
        await conn.connect()
        results = await conn.search(mode, q, max_records=max_records)
        return {"count": len(results), "compounds": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.disconnect()


@router.get("/pubchem/cid/{cid}")
async def pubchem_get_by_cid(cid: int):
    """Fetch a single compound from PubChem by CID."""
    cfg = get_config()
    pubchem_cfg = cfg.data_infra.get("pubchem", {})
    conn = PubChemConnector("api-cid", {
        "max_records": 1,
        "timeout": pubchem_cfg.get("timeout", 30),
        "verify_ssl": pubchem_cfg.get("verify_ssl", False),
        "properties": pubchem_cfg.get(
            "properties",
            ["MolecularFormula", "MolecularWeight", "SMILES", "InChI",
             "InChIKey", "IUPACName", "XLogP", "TPSA"],
        ),
    })
    try:
        await conn.connect()
        results = await conn.search("cid", str(cid))
        if not results:
            raise HTTPException(status_code=404, detail=f"CID {cid} not found")
        return results[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.disconnect()


@router.post("/pubchem/ingest")
async def pubchem_ingest(
    q: str = Query(...),
    mode: str = Query("name"),
    target_path: str = Query("/data/pubchem"),
    max_records: int = Query(100),
):
    """Run a full ingestion pipeline against PubChem data."""
    registry = get_registry()
    cfg = get_config()

    registry.register("pubchem-ingest", "pubchem", {
        "max_records": max_records,
        "properties": cfg.data_infra.get("pubchem", {}).get(
            "properties",
            ["MolecularFormula", "MolecularWeight", "SMILES", "InChI",
             "InChIKey", "IUPACName", "XLogP", "TPSA"],
        ),
    })

    validator = SchemaValidator(mode=cfg.data_infra.get("cleaning", {}).get("validation_mode", "warn"))
    transformer = DataTransformer()
    quality = QualityChecker(
        max_null_ratio=cfg.data_infra.get("cleaning", {}).get("max_null_ratio", 0.10),
        quality_threshold=cfg.data_infra.get("cleaning", {}).get("quality_threshold", 0.95),
    )

    pipeline = IngestionPipeline(
        registry, validator=validator, transformer=transformer,
        quality_checker=quality, lineage=get_lineage(),
    )

    try:
        report = await pipeline.run(
            "pubchem-ingest", f"{mode}:{q}", target_path,
            batch_size=max_records, target_format="parquet",
        )
        return {
            "status": report.status,
            "rows_read": report.rows_read,
            "rows_written": report.rows_written,
            "pass_rate": report.pass_rate,
            "duration_sec": report.duration_sec,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# prediction routes
# ---------------------------------------------------------------------------


class PredictRequest(BaseModel):
    smiles: str = Field(..., description="SMILES string of the molecule")


@router.post("/predict")
async def predict_molecule(req: PredictRequest):
    """Predict molecular properties from a SMILES string using RDKit."""
    try:
        from ai4s.data_infra.prediction import predict_properties
    except ImportError as e:
        raise HTTPException(status_code=501, detail=f"RDKit not available: {e}")

    result = predict_properties(req.smiles)
    if not result.get("valid"):
        raise HTTPException(status_code=400, detail=result.get("error", "Invalid SMILES"))
    return result


# ---------------------------------------------------------------------------
# pdf extraction routes
# ---------------------------------------------------------------------------


class PDFExtractRequest(BaseModel):
    file_path: str = Field(..., description="Absolute path to the PDF file")


@router.post("/pdf/extract")
async def pdf_extract(req: PDFExtractRequest):
    """Extract molecular structures and tables from a PDF file."""
    try:
        from ai4s.data_infra.ingestion.pdf_extractor import extract_from_pdf
    except ImportError as e:
        raise HTTPException(status_code=501, detail=str(e))

    try:
        result = extract_from_pdf(req.file_path)
        return {
            "filename": result.filename,
            "structure_count": len(result.structures),
            "table_count": len(result.tables),
            "char_count": len(result.full_text),
            "structures": [
                {"smiles": s.smiles, "inchi": s.inchi, "page": s.page, "context": s.context}
                for s in result.structures
            ],
            "tables": [
                {"page": t.page, "headers": t.headers, "rows": t.rows, "caption": t.caption}
                for t in result.tables
            ],
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
