"""Tests for schema validator."""

import pytest

from ai4s.data_infra.ingestion.connector import SourceRecord
from ai4s.data_infra.cleaning.validator import SchemaValidator


@pytest.mark.asyncio
async def test_validate_batch_strict_mode():
    validator = SchemaValidator("/tmp/schemas", mode="strict")
    validator.register_schema("mytable", {"age": "int64", "name": "string"})

    batch = SourceRecord(
        source="test", table="mytable", batch_id="b1",
        rows=[
            {"age": 25, "name": "Alice"},
            {"age": "bad", "name": "Bob"},  # invalid type
        ],
    )

    clean_batch, errors = await validator.validate_batch(batch)
    assert len(errors) == 1
    assert errors[0].column == "age"


@pytest.mark.asyncio
async def test_validate_batch_no_schema_raises_in_strict():
    validator = SchemaValidator("/tmp/schemas", mode="strict")
    batch = SourceRecord(source="test", table="unknown_table", batch_id="b1", rows=[])
    with pytest.raises(ValueError, match="No schema registered"):
        await validator.validate_batch(batch)
