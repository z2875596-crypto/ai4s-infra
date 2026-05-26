"""Ingestion pipeline — orchestrates reading, validation, cleaning, quality, and writing.

Full data flow:
  1. Connector reads batches from source
  2. SchemaValidator checks column types and required fields
  3. DataTransformer applies user-defined column transformations
  4. QualityChecker verifies null ratios, duplicates, distribution drift
  5. Writer persists to target (Parquet / Delta / Iceberg)
  6. LineageTracker records the operation
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from ai4s.common.exceptions import IngestionError
from ai4s.common.logging import get_logger
from ai4s.common.metrics import MetricsRegistry
from ai4s.data_infra.cleaning.quality import QualityChecker, QualityReport
from ai4s.data_infra.cleaning.transformer import DataTransformer
from ai4s.data_infra.cleaning.validator import SchemaValidator, ValidationError
from ai4s.data_infra.ingestion.connector import DataConnector, SourceRecord
from ai4s.data_infra.ingestion.registry import ConnectorRegistry
from ai4s.data_infra.versioning.lineage import LineageTracker, LineageStepType

logger = get_logger(__name__)


@dataclass
class IngestionReport:
    """Result of a single ingestion run."""

    source: str
    table: str
    target_path: str
    rows_read: int = 0
    rows_valid: int = 0
    rows_invalid: int = 0
    rows_transformed: int = 0
    rows_written: int = 0
    batches_processed: int = 0
    quality_reports: list[QualityReport] = field(default_factory=list)
    validation_errors: list[ValidationError] = field(default_factory=list)
    duration_sec: float = 0.0
    status: str = "success"

    @property
    def pass_rate(self) -> float:
        return self.rows_written / max(self.rows_read, 1)


class IngestionPipeline:
    """End-to-end ingestion pipeline.

    Usage::

        registry = ConnectorRegistry()
        registry.register("my_pg", "postgresql", {...})

        validator = SchemaValidator("/schemas")
        validator.register_schema("mytable", {"id": "int64", "name": "string"})

        transformer = DataTransformer()
        transformer.add_transform(transformer.drop_nulls("temp_col"))

        quality = QualityChecker(max_null_ratio=0.05)

        pipeline = IngestionPipeline(registry, validator, transformer, quality)
        report = await pipeline.run("my_pg", "mytable", "s3://lake/mytable/")
    """

    def __init__(
        self,
        registry: ConnectorRegistry,
        validator: SchemaValidator | None = None,
        transformer: DataTransformer | None = None,
        quality_checker: QualityChecker | None = None,
        lineage: LineageTracker | None = None,
        max_retries: int = 3,
        retry_backoff_sec: float = 5.0,
    ) -> None:
        self._registry = registry
        self._validator = validator
        self._transformer = transformer
        self._quality = quality_checker
        self._lineage = lineage or LineageTracker()
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff_sec

    # ------------------------------------------------------------------

    async def run(
        self,
        source_name: str,
        table: str,
        target_path: str,
        batch_size: int = 10000,
        target_format: str = "parquet",
        partition_cols: list[str] | None = None,
    ) -> IngestionReport:
        connector = self._registry.get(source_name)
        if connector is None:
            raise IngestionError(f"Unknown source: {source_name}")

        t0 = time.monotonic()
        report = IngestionReport(source=source_name, table=table, target_path=target_path)

        try:
            await connector.connect()

            async for batch in connector.read_batches(table, batch_size):
                report.rows_read += batch.row_count

                # 1. validate
                batch, v_errs = await self._validate(batch)
                report.validation_errors.extend(v_errs)
                report.rows_invalid += len(v_errs)

                # 2. transform
                batch = await self._transform(batch)
                report.rows_transformed += batch.row_count

                # 3. quality
                q_report = await self._quality_check(batch)
                if q_report:
                    report.quality_reports.append(q_report)

                # 4. write
                await self._write_batch(batch, target_path, target_format, partition_cols)
                report.rows_written += batch.row_count
                report.rows_valid += batch.row_count - len(v_errs)
                report.batches_processed += 1

                MetricsRegistry.data_ingested_rows.labels(
                    source=source_name, status="success"
                ).inc(batch.row_count)

            # 5. record lineage
            self._lineage.record(
                source_id=f"{source_name}/{table}",
                target_id=target_path.rstrip("/"),
                step_type=LineageStepType.INGEST,
                metadata={"rows": report.rows_written, "format": target_format},
            )

        except Exception as exc:
            report.status = "failed"
            logger.error("Ingestion failed source=%s table=%s: %s", source_name, table, exc)
            MetricsRegistry.data_ingested_rows.labels(source=source_name, status="failed").inc()
            raise IngestionError(f"Ingestion failed: {source_name}/{table}") from exc
        finally:
            await connector.disconnect()

        report.duration_sec = round(time.monotonic() - t0, 2)
        logger.info(
            "Ingestion done source=%s table=%s read=%d written=%d duration=%.1fs pass_rate=%.2f",
            source_name, table, report.rows_read, report.rows_written,
            report.duration_sec, report.pass_rate,
        )
        return report

    # -- internal stages ----------------------------------------------------

    async def _validate(self, batch: SourceRecord) -> tuple[SourceRecord, list[ValidationError]]:
        if self._validator is None:
            return batch, []
        return await self._validator.validate_batch(batch)

    async def _transform(self, batch: SourceRecord) -> SourceRecord:
        if self._transformer is None:
            return batch
        return await self._transformer.transform(batch)

    async def _quality_check(self, batch: SourceRecord) -> QualityReport | None:
        if self._quality is None:
            return None
        return await self._quality.check_batch(batch)

    async def _write_batch(
        self,
        batch: SourceRecord,
        target: str,
        fmt: str,
        partition_cols: list[str] | None,
    ) -> None:
        table_arrow = batch.to_arrow()
        target_path = Path(target)

        if target.startswith("s3://"):
            await self._write_s3(table_arrow, target, fmt, partition_cols)
        elif fmt == "parquet":
            target_path.mkdir(parents=True, exist_ok=True)
            fname = target_path / f"{batch.batch_id.replace('/', '_')}.parquet"
            pq.write_table(table_arrow, str(fname))
        elif fmt == "delta":
            self._write_delta(table_arrow, target, partition_cols)
        else:
            raise IngestionError(f"Unsupported target format: {fmt}")

    async def _write_s3(
        self,
        table_arrow: pa.Table,
        target: str,
        fmt: str,
        partition_cols: list[str] | None,
    ) -> None:
        import io

        import boto3

        # Parse s3://bucket/prefix
        path = target[5:]
        parts = path.split("/", 1)
        bucket = parts[0]
        prefix = parts[1] if len(parts) > 1 else ""

        buf = io.BytesIO()
        pq.write_table(table_arrow, buf)
        buf.seek(0)

        s3 = boto3.client("s3")
        key = f"{prefix}/{uuid.uuid4().hex}.parquet"
        s3.upload_fileobj(buf, bucket, key)

    @staticmethod
    def _write_delta(table_arrow: pa.Table, target: str, partition_cols: list[str] | None) -> None:
        try:
            from deltalake import write_deltalake
            write_deltalake(target, table_arrow, partition_by=partition_cols, mode="append")
        except ImportError:
            logger.warning("deltalake not installed — falling back to parquet")
            pq.write_to_dataset(table_arrow, target, partition_cols=partition_cols)
