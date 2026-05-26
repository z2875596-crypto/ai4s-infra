"""PubChem API connector — fetch molecular data via PUG REST API.

Supports three search modes passed through the ``table`` parameter as ``mode:query``:
  - ``name:aspirin`` — search compounds by name
  - ``cid:2244`` — fetch a specific compound by CID
  - ``substructure:c1ccccc1`` — substructure search via SMILES
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncIterator
from urllib.parse import quote

import httpx

from ai4s.common.exceptions import IngestionError
from ai4s.common.logging import get_logger
from ai4s.common.metrics import MetricsRegistry
from ai4s.data_infra.ingestion.connector import DataConnector, SourceRecord

logger = get_logger(__name__)

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

DEFAULT_PROPERTIES = [
    "MolecularFormula",
    "MolecularWeight",
    "CanonicalSMILES",
    "InChI",
    "InChIKey",
    "IUPACName",
    "XLogP",
    "TPSA",
    "HBondDonorCount",
    "HBondAcceptorCount",
    "RotatableBondCount",
    "Complexity",
    "Charge",
    "MonoisotopicMass",
]


class PubChemConnector(DataConnector):
    """Fetch molecular data from PubChem's PUG REST API.

    The ``table`` argument in ``read_batches`` uses a colon-delimited format:
    ``<mode>:<query>`` where *mode* is one of ``name``, ``cid``, or ``substructure``.

    Config keys:
        - *properties* (list[str]): PubChem property names to fetch
        - *max_records* (int): max CIDs to retrieve, default 100
        - *timeout* (int): HTTP request timeout in seconds, default 30
    """

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name, config or {})
        self._client: httpx.AsyncClient | None = None
        self._properties: list[str] = self.config.get("properties", DEFAULT_PROPERTIES)
        self._max_records: int = int(self.config.get("max_records", 100))
        self._timeout: int = int(self.config.get("timeout", 30))
        self._search_limit: int = min(self._max_records, 200)

    # -- lifecycle ------------------------------------------------------------

    async def connect(self) -> None:
        if self._connected:
            return
        verify = self.config.get("verify_ssl", True)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            headers={"Accept": "application/json"},
            verify=verify,
        )
        self._connected = True
        logger.info("PubChem connector %r connected (verify_ssl=%s)", self.name, verify)

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._connected = False
        logger.info("PubChem connector %r disconnected", self.name)

    # -- read batches ---------------------------------------------------------

    async def read_batches(
        self, table: str, batch_size: int = 10000
    ) -> AsyncIterator[SourceRecord]:
        if ":" not in table:
            raise IngestionError(
                f"PubChem table must be 'mode:query', got {table!r}"
            )

        mode, query = table.split(":", 1)
        mode = mode.strip().lower()
        query = query.strip()

        if mode not in ("name", "cid", "substructure"):
            raise IngestionError(
                f"Unknown PubChem search mode {mode!r}. Use: name, cid, or substructure"
            )

        if not query:
            raise IngestionError("PubChem query must not be empty")

        cids = await self._get_cids(mode, query)
        if not cids:
            logger.warning("PubChem search %r:%r returned no CIDs", mode, query)
            return

        properties = await self._get_properties(cids)
        batch_id = f"pubchem-{mode}-{query[:30]}-{datetime.now(timezone.utc).timestamp():.0f}"

        yield SourceRecord(
            source=f"pubchem:{self.name}",
            table=table,
            batch_id=batch_id,
            rows=properties,
            metadata={
                "mode": mode,
                "query": query,
                "cid_count": len(cids),
                "properties": self._properties,
            },
        )

    async def schema(self, table: str) -> dict[str, str]:
        type_map = {
            "MolecularFormula": "string",
            "MolecularWeight": "float64",
            "CanonicalSMILES": "string",
            "InChI": "string",
            "InChIKey": "string",
            "IUPACName": "string",
            "XLogP": "float64",
            "TPSA": "float64",
            "HBondDonorCount": "int32",
            "HBondAcceptorCount": "int32",
            "RotatableBondCount": "int32",
            "Complexity": "float64",
            "Charge": "int32",
            "MonoisotopicMass": "float64",
            "CID": "int32",
        }
        return {p: type_map.get(p, "string") for p in ["CID"] + self._properties}

    # -- PubChem API calls ----------------------------------------------------

    async def _get_cids(self, mode: str, query: str) -> list[int]:
        """Retrieve CIDs from PubChem for the given search mode and query."""
        assert self._client is not None

        if mode == "cid":
            # Support comma-separated CID list: "1,2,3,4,5"
            parts = query.replace(" ", "").split(",")
            cids = []
            for p in parts:
                if "-" in p and p.count("-") == 1:
                    # Range: "1-100"
                    lo, hi = p.split("-", 1)
                    cids.extend(range(int(lo), int(hi) + 1))
                else:
                    cids.append(int(p))
            return cids[: self._max_records]

        encoded = quote(query, safe="")

        if mode == "name":
            url = f"{PUBCHEM_BASE}/compound/name/{encoded}/cids/JSON"
        else:  # substructure
            url = f"{PUBCHEM_BASE}/compound/fastsubstructure/smiles/{encoded}/cids/JSON"
            url += f"?MaxRecords={self._search_limit}"

        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            MetricsRegistry.data_ingested_rows.labels(
                source="pubchem", status="failed"
            ).inc()
            raise IngestionError(
                f"PubChem CID lookup failed for {mode}={query}: {exc}"
            ) from exc

        id_list = data.get("IdentifierList", {})
        cids = id_list.get("CID", [])
        # Cap to max_records
        return cids[: self._max_records]

    async def _get_properties(self, cids: list[int]) -> list[dict[str, Any]]:
        """Fetch molecular properties for a list of CIDs."""
        assert self._client is not None

        cid_str = ",".join(str(c) for c in cids)
        prop_str = ",".join(self._properties)
        url = f"{PUBCHEM_BASE}/compound/cid/{cid_str}/property/{prop_str}/JSON"

        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            MetricsRegistry.data_ingested_rows.labels(
                source="pubchem", status="failed"
            ).inc()
            raise IngestionError(
                f"PubChem property fetch failed for {len(cids)} CIDs: {exc}"
            ) from exc

        props = data.get("PropertyTable", {}).get("Properties", [])
        for entry in props:
            entry.setdefault("CID", entry.get("CID"))
            MetricsRegistry.data_ingested_rows.labels(
                source="pubchem", status="success"
            ).inc()

        logger.info(
            "PubChem: fetched %d properties for %d CIDs", len(props), len(cids)
        )
        return props

    # -- convenience ----------------------------------------------------------

    async def search(
        self, mode: str, query: str, max_records: int | None = None
    ) -> list[dict[str, Any]]:
        """Convenience: search PubChem and return property rows directly."""
        saved = self._max_records
        if max_records is not None:
            self._max_records = max_records
            self._search_limit = min(self._max_records, 200)
        try:
            cids = await self._get_cids(mode, query)
            if not cids:
                return []
            return await self._get_properties(cids)
        finally:
            self._max_records = saved
            self._search_limit = min(saved, 200)
