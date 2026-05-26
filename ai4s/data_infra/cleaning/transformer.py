"""Data transformer — chainable column operations with Arrow acceleration."""

from __future__ import annotations

import re
from typing import Any, Callable

import pyarrow as pa
import pyarrow.compute as pc

from ai4s.common.logging import get_logger
from ai4s.data_infra.ingestion.connector import SourceRecord

logger = get_logger(__name__)

TransformFunc = Callable[[SourceRecord], SourceRecord]


class DataTransformer:
    """Pipeline of transformations applied to each batch.

    Transformations operate on the Arrow table for performance,
    falling back to Python row-level ops for complex logic.

    Usage::

        t = DataTransformer()
        t.drop_columns("_raw", "_tmp")
        t.rename_column("old_name", "new_name")
        t.fill_null("score", 0.0)
        t.cast_type("count", pa.int64())
        result = await t.transform(batch)
    """

    def __init__(self) -> None:
        self._transforms: list[TransformFunc] = []

    # -- transform ----------------------------------------------------------

    async def transform(self, batch: SourceRecord) -> SourceRecord:
        for tf in self._transforms:
            batch = tf(batch)
        return SourceRecord(
            source=batch.source,
            table=batch.table,
            batch_id=batch.batch_id,
            rows=batch.rows,
            metadata={**batch.metadata, "transformed": True, "num_transforms": len(self._transforms)},
        )

    # -- column operations --------------------------------------------------

    def drop_columns(self, *columns: str) -> DataTransformer:
        def _fn(batch: SourceRecord) -> SourceRecord:
            table = batch.to_arrow()
            existing = [c for c in columns if c in table.schema.names]
            if existing:
                table = table.drop_columns(existing)
            batch.rows = table.to_pylist()
            return batch
        self._transforms.append(_fn)
        return self

    def keep_columns(self, *columns: str) -> DataTransformer:
        def _fn(batch: SourceRecord) -> SourceRecord:
            table = batch.to_arrow()
            table = table.select(list(columns))
            batch.rows = table.to_pylist()
            return batch
        self._transforms.append(_fn)
        return self

    def rename_column(self, old: str, new: str) -> DataTransformer:
        def _fn(batch: SourceRecord) -> SourceRecord:
            table = batch.to_arrow()
            if old in table.schema.names:
                idx = table.schema.get_field_index(old)
                new_names = list(table.schema.names)
                new_names[idx] = new
                table = table.rename_columns(new_names)
            batch.rows = table.to_pylist()
            return batch
        self._transforms.append(_fn)
        return self

    def cast_type(self, column: str, target_type: pa.DataType) -> DataTransformer:
        def _fn(batch: SourceRecord) -> SourceRecord:
            table = batch.to_arrow()
            if column in table.schema.names:
                try:
                    table = table.set_column(
                        table.schema.get_field_index(column),
                        pa.field(column, target_type),
                        table.column(column).cast(target_type),
                    )
                except pa.ArrowInvalid as e:
                    logger.warning("Cast failed for column=%s: %s — keeping original", column, e)
            batch.rows = table.to_pylist()
            return batch
        self._transforms.append(_fn)
        return self

    def fill_null(self, column: str, value: Any) -> DataTransformer:
        def _fn(batch: SourceRecord) -> SourceRecord:
            table = batch.to_arrow()
            if column in table.schema.names:
                col = table.column(column)
                col = col if col.null_count == 0 else pc.fill_null(col, pa.scalar(value))
                table = table.set_column(
                    table.schema.get_field_index(column), column, col
                )
            batch.rows = table.to_pylist()
            return batch
        self._transforms.append(_fn)
        return self

    def map_column(self, column: str, fn: Callable[[Any], Any]) -> DataTransformer:
        def _tf(batch: SourceRecord) -> SourceRecord:
            for row in batch.rows:
                if column in row:
                    try:
                        row[column] = fn(row[column])
                    except Exception:
                        pass
            return batch
        self._transforms.append(_tf)
        return self

    def add_column(self, column: str, value: Any) -> DataTransformer:
        def _fn(batch: SourceRecord) -> SourceRecord:
            table = batch.to_arrow()
            new_col = pa.array([value] * table.num_rows)
            table = table.append_column(pa.field(column, new_col.type), new_col)
            batch.rows = table.to_pylist()
            return batch
        self._transforms.append(_fn)
        return self

    def filter_rows(self, predicate: Callable[[dict[str, Any]], bool]) -> DataTransformer:
        def _fn(batch: SourceRecord) -> SourceRecord:
            batch.rows = [r for r in batch.rows if predicate(r)]
            return batch
        self._transforms.append(_fn)
        return self

    def normalize_whitespace(self, *columns: str) -> DataTransformer:
        def _fn(batch: SourceRecord) -> SourceRecord:
            cols = columns or list(batch.rows[0].keys()) if batch.rows else []
            for row in batch.rows:
                for c in cols:
                    if isinstance(row.get(c), str):
                        row[c] = re.sub(r"\s+", " ", row[c]).strip()
            return batch
        self._transforms.append(_fn)
        return self

    def lowercase_columns(self, *columns: str) -> DataTransformer:
        def _fn(batch: SourceRecord) -> SourceRecord:
            cols = columns or list(batch.rows[0].keys()) if batch.rows else []
            for row in batch.rows:
                for c in cols:
                    if isinstance(row.get(c), str):
                        row[c] = row[c].lower()
            return batch
        self._transforms.append(_fn)
        return self

    def add_row_hash(self, output_column: str = "_hash", columns: list[str] | None = None) -> DataTransformer:
        import hashlib

        def _fn(batch: SourceRecord) -> SourceRecord:
            for row in batch.rows:
                to_hash = {k: row[k] for k in (columns or row.keys()) if k in row}
                raw = json.dumps(to_hash, sort_keys=True, default=str)
                row[output_column] = hashlib.sha256(raw.encode()).hexdigest()
            return batch
        self._transforms.append(_fn)
        return self
