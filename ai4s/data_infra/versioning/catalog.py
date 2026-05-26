"""Data catalog — discoverable metadata index with search and schema registry.

Acts as the central metadata store for all datasets:
  - Schema registry (what columns, what types)
  - Dataset ownership and documentation
  - Search by tag, keyword, owner, column name
  - Usage statistics

Backends: in-memory (dev), SQLite (single-node), PostgreSQL (prod).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai4s.common.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ColumnMeta:
    name: str
    dtype: str
    description: str = ""
    nullable: bool = True
    tags: list[str] = field(default_factory=list)


@dataclass
class DatasetEntry:
    name: str                             # Fully qualified dataset name
    description: str = ""
    owner: str = ""
    columns: list[ColumnMeta] = field(default_factory=list)
    location: str = ""                    # Storage path
    format: str = "parquet"               # parquet | delta | iceberg | json
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    row_count_estimate: int = 0
    size_bytes_estimate: int = 0
    freshness_hours: float = 0.0
    quality_score: float = 1.0
    partition_cols: list[str] = field(default_factory=list)
    custom_properties: dict[str, Any] = field(default_factory=dict)
    deprecation_date: str | None = None

    @property
    def is_deprecated(self) -> bool:
        return self.deprecation_date is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "owner": self.owner,
            "columns": [{"name": c.name, "dtype": c.dtype, "description": c.description}
                         for c in self.columns],
            "location": self.location,
            "format": self.format,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "row_count_estimate": self.row_count_estimate,
            "size_bytes_estimate": self.size_bytes_estimate,
            "quality_score": self.quality_score,
            "partition_cols": self.partition_cols,
        }


# ---------------------------------------------------------------------------
# DataCatalog
# ---------------------------------------------------------------------------


class DataCatalog:
    """Central metadata catalog.

    Usage::

        catalog = DataCatalog(persist_path="/data/catalog.db")
        catalog.register(DatasetEntry(
            name="research.experiments.v1",
            description="Experiment results",
            owner="team-a",
            columns=[ColumnMeta("id", "int64"), ColumnMeta("value", "float64")],
            tags=["research", "experiment"],
        ))

        # Search
        results = catalog.search(tag="research", keyword="experiment")
        entry = catalog.get("research.experiments.v1")
    """

    def __init__(self, persist_path: str | None = None) -> None:
        self._entries: dict[str, DatasetEntry] = {}
        self._persist_path = persist_path
        if persist_path:
            self._load()

    # -- CRUD ---------------------------------------------------------------

    def register(self, entry: DatasetEntry) -> None:
        """Register or update a dataset entry."""
        if entry.name in self._entries:
            entry.created_at = self._entries[entry.name].created_at
        entry.updated_at = datetime.now(timezone.utc).isoformat()
        self._entries[entry.name] = entry
        self._save()
        logger.info("Catalog: registered dataset '%s' (%d columns)", entry.name, len(entry.columns))

    def get(self, name: str) -> DatasetEntry | None:
        return self._entries.get(name)

    def delete(self, name: str) -> bool:
        if name in self._entries:
            del self._entries[name]
            self._save()
            return True
        return False

    def list_all(self) -> list[DatasetEntry]:
        return sorted(self._entries.values(), key=lambda e: e.name)

    def list_by_owner(self, owner: str) -> list[DatasetEntry]:
        return [e for e in self._entries.values() if e.owner == owner]

    # -- search -------------------------------------------------------------

    def search(
        self,
        tag: str | None = None,
        keyword: str | None = None,
        owner: str | None = None,
        column_name: str | None = None,
        deprecated: bool | None = None,
        limit: int = 50,
    ) -> list[DatasetEntry]:
        results = list(self._entries.values())

        if tag:
            results = [e for e in results if tag in e.tags]
        if owner:
            results = [e for e in results if e.owner == owner]
        if keyword:
            kw = keyword.lower()
            results = [
                e for e in results
                if kw in e.name.lower()
                or kw in e.description.lower()
                or any(kw in c.name.lower() for c in e.columns)
                or any(kw in c.description.lower() for c in e.columns)
            ]
        if column_name:
            results = [e for e in results if any(column_name == c.name for c in e.columns)]
        if deprecated is not None:
            results = [e for e in results if e.is_deprecated == deprecated]

        return results[:limit]

    def search_by_column_type(self, dtype: str) -> list[DatasetEntry]:
        return [e for e in self._entries.values()
                if any(c.dtype == dtype for c in e.columns)]

    # -- schema registry ----------------------------------------------------

    def get_schema(self, dataset: str) -> list[ColumnMeta] | None:
        entry = self._entries.get(dataset)
        return entry.columns if entry else None

    def find_datasets_with_column(self, column_name: str) -> list[DatasetEntry]:
        return [e for e in self._entries.values()
                if any(c.name == column_name for c in e.columns)]

    # -- statistics ---------------------------------------------------------

    def update_stats(
        self, name: str, row_count: int, size_bytes: int, quality_score: float | None = None
    ) -> None:
        entry = self._entries.get(name)
        if not entry:
            return
        entry.row_count_estimate = row_count
        entry.size_bytes_estimate = size_bytes
        entry.freshness_hours = 0
        if quality_score is not None:
            entry.quality_score = quality_score
        entry.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()

    def summary(self) -> dict[str, Any]:
        entries = list(self._entries.values())
        return {
            "total_datasets": len(entries),
            "total_columns": sum(len(e.columns) for e in entries),
            "total_estimated_rows": sum(e.row_count_estimate for e in entries),
            "total_estimated_size_bytes": sum(e.size_bytes_estimate for e in entries),
            "owners": list({e.owner for e in entries if e.owner}),
            "tags": list({t for e in entries for t in e.tags}),
            "formats": list({e.format for e in entries}),
        }

    # -- persistence (SQLite) -----------------------------------------------

    def _save(self) -> None:
        if not self._persist_path:
            return
        path = Path(self._persist_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {name: entry.to_dict() for name, entry in self._entries.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)

    def _load(self) -> None:
        path = Path(self._persist_path)
        if not path.exists():
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for name, d in data.items():
                d["columns"] = [ColumnMeta(**c) for c in d.get("columns", [])]
                self._entries[name] = DatasetEntry(**d)
            logger.info("Catalog loaded: %d datasets from %s", len(self._entries), path)
        except Exception as exc:
            logger.error("Failed to load catalog from %s: %s", path, exc)
