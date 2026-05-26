"""Schema validator — column-level and row-level validation with JSON Schema support.

Supports three modes:
  - strict  : reject rows that fail validation
  - warn    : keep row, log a warning
  - skip    : no validation for unregistered tables
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa

from ai4s.common.logging import get_logger
from ai4s.common.metrics import MetricsRegistry
from ai4s.data_infra.ingestion.connector import SourceRecord

logger = get_logger(__name__)


@dataclass
class ValidationError:
    row_index: int
    column: str
    expected_type: str
    actual_value: Any
    message: str


@dataclass
class ValidationReport:
    batch_id: str
    table: str
    total_rows: int
    errors: list[ValidationError] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def is_valid(self) -> bool:
        return self.error_count == 0

    @property
    def pass_rate(self) -> float:
        return 1.0 - (self.error_count / max(self.total_rows, 1))


# ---------------------------------------------------------------------------
# type-system helpers
# ---------------------------------------------------------------------------

_ARROW_TYPE_MAP: dict[str, pa.DataType] = {
    "int8": pa.int8(), "int16": pa.int16(), "int32": pa.int32(), "int64": pa.int64(),
    "uint8": pa.uint8(), "uint16": pa.uint16(), "uint32": pa.uint32(), "uint64": pa.uint64(),
    "float32": pa.float32(), "float64": pa.float64(),
    "string": pa.string(), "utf8": pa.string(), "large_string": pa.large_string(),
    "bool": pa.bool_(), "boolean": pa.bool_(),
    "timestamp": pa.timestamp("us"), "date": pa.date32(),
    "binary": pa.binary(), "large_binary": pa.large_binary(),
    # Aliases
    "int": pa.int64(), "integer": pa.int64(),
    "float": pa.float64(), "double": pa.float64(),
    "str": pa.string(), "text": pa.string(),
}

_PYTHON_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "int8": int, "int16": int, "int32": int, "int64": int, "int": int, "integer": int,
    "uint8": int, "uint16": int, "uint32": int, "uint64": int,
    "float32": (int, float), "float64": (int, float), "float": (int, float), "double": (int, float),
    "string": str, "utf8": str, "large_string": str, "str": str, "text": str,
    "bool": bool, "boolean": bool,
    "timestamp": str, "date": str,
}


# ---------------------------------------------------------------------------
# SchemaValidator
# ---------------------------------------------------------------------------


class SchemaValidator:
    """Validates batches against a registered per-table schema.

    Schemas can be registered programmatically or loaded from a directory
    of JSON-schema files.
    """

    def __init__(self, schema_registry_path: str = "/data/schemas", mode: str = "strict") -> None:
        self._registry_path = Path(schema_registry_path)
        self._mode = mode                      # strict | warn | skip
        self._schemas: dict[str, dict[str, str]] = {}        # table → {col: arrow_type}
        self._required_columns: dict[str, set[str]] = {}     # table → {required_cols}
        self._json_schemas: dict[str, dict[str, Any]] = {}   # table → JSON Schema
        self._load_registry()

    # -- schema management ---------------------------------------------------

    def register_schema(
        self,
        table: str,
        columns: dict[str, str],
        required: list[str] | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> None:
        self._schemas[table] = columns
        self._required_columns[table] = set(required or [])
        if json_schema:
            self._json_schemas[table] = json_schema
        logger.info("Schema registered for table=%s cols=%d required=%d",
                     table, len(columns), len(required or []))

    def has_schema(self, table: str) -> bool:
        return table in self._schemas

    # -- validation ----------------------------------------------------------

    async def validate_batch(self, batch: SourceRecord) -> tuple[SourceRecord, list[ValidationError]]:
        """Validate a batch. Returns (clean_batch, errors)."""
        table = batch.table

        # No schema registered
        if table not in self._schemas:
            if self._mode == "strict":
                raise ValueError(f"No schema registered for table: {table}")
            return batch, []

        expected = self._schemas[table]
        required = self._required_columns.get(table, set())
        all_errors: list[ValidationError] = []
        clean_rows: list[dict[str, Any]] = []

        for i, row in enumerate(batch.rows):
            row_errors = self._validate_row(i, row, expected, required)

            # JSON Schema validation (if registered)
            if table in self._json_schemas:
                row_errors += self._validate_json_schema(i, row, self._json_schemas[table])

            if row_errors:
                all_errors.extend(row_errors)
                MetricsRegistry.data_cleaning_issues.labels(severity="error").inc()
                if self._mode == "strict":
                    continue  # Drop this row
            clean_rows.append(row)

        # Build clean batch
        clean_batch = SourceRecord(
            source=batch.source,
            table=table,
            batch_id=batch.batch_id,
            rows=clean_rows,
            metadata={**batch.metadata, "validated": True, "validator_mode": self._mode},
        )

        if all_errors:
            logger.warning(
                "Batch %s: %d validation errors (mode=%s, dropped=%d)",
                batch.batch_id, len(all_errors), self._mode,
                batch.row_count - clean_batch.row_count,
            )

        return clean_batch, all_errors

    # -- row-level checks ----------------------------------------------------

    def _validate_row(
        self,
        index: int,
        row: dict[str, Any],
        expected: dict[str, str],
        required: set[str],
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []

        # Required column check
        for col in required:
            if col not in row or row[col] is None:
                errors.append(ValidationError(
                    index, col, "required",
                    None,
                    f"Required column '{col}' is missing or null",
                ))

        # Type check
        for col, exp_type in expected.items():
            if col not in row:
                continue
            actual = row[col]
            if actual is None:
                continue

            py_type = _PYTHON_TYPE_MAP.get(exp_type)
            if py_type and not isinstance(actual, py_type):
                errors.append(ValidationError(
                    index, col, exp_type, actual,
                    f"Expected {exp_type}, got {type(actual).__name__} (value={actual!r})",
                ))

        # Value constraints
        for col in row:
            if col in expected and isinstance(row[col], str):
                val = row[col]
                if len(val) > 1_000_000:
                    errors.append(ValidationError(
                        index, col, "string", f"<{len(val)} chars>",
                        f"String exceeds max length (1M chars)",
                    ))

        return errors

    def _validate_json_schema(
        self, index: int, row: dict[str, Any], schema: dict[str, Any]
    ) -> list[ValidationError]:
        try:
            import jsonschema
            jsonschema.validate(instance=row, schema=schema)
            return []
        except ImportError:
            return []
        except jsonschema.ValidationError as e:
            return [ValidationError(
                index, e.path[-1] if e.path else "?",
                e.schema.get("type", "?"),
                e.instance,
                e.message,
            )]

    # -- persistent schema registry -----------------------------------------

    def _load_registry(self) -> None:
        if not self._registry_path.exists():
            return
        for schema_file in self._registry_path.glob("*.json"):
            try:
                with open(schema_file, encoding="utf-8") as f:
                    data = json.load(f)
                table = schema_file.stem
                self._schemas[table] = data.get("columns", {})
                self._required_columns[table] = set(data.get("required", []))
                self._json_schemas[table] = data.get("json_schema", {})
                logger.debug("Loaded schema from %s: table=%s", schema_file, table)
            except Exception as exc:
                logger.error("Failed to load schema %s: %s", schema_file, exc)

    def save_schema(self, table: str) -> None:
        self._registry_path.mkdir(parents=True, exist_ok=True)
        data = {
            "table": table,
            "columns": self._schemas.get(table, {}),
            "required": list(self._required_columns.get(table, set())),
            "json_schema": self._json_schemas.get(table, {}),
        }
        filepath = self._registry_path / f"{table}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info("Schema saved: %s", filepath)
