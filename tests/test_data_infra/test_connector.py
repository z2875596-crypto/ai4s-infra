"""Tests for data ingestion connectors."""

import pytest

from ai4s.data_infra.ingestion.connector import S3Connector, PostgresConnector
from ai4s.data_infra.ingestion.registry import ConnectorRegistry
from ai4s.data_infra.ingestion.pipeline import IngestionPipeline


class TestConnectorRegistry:
    def test_register_s3_connector(self):
        registry = ConnectorRegistry()
        registry.register("my_s3", "s3", {"bucket": "test", "region": "us-east-1"})
        conn = registry.get("my_s3")
        assert conn is not None
        assert isinstance(conn, S3Connector)
        assert conn.name == "my_s3"

    def test_register_unknown_type_raises(self):
        registry = ConnectorRegistry()
        with pytest.raises(ValueError, match="Unsupported source type"):
            registry.register("bad", "unknown_type", {})

    def test_list_sources(self):
        registry = ConnectorRegistry()
        registry.register("a", "s3", {"bucket": "b"})
        registry.register("b", "postgresql", {})
        assert set(registry.list_sources()) == {"a", "b"}

    def test_get_unknown_returns_none(self):
        registry = ConnectorRegistry()
        assert registry.get("nonexistent") is None


class TestIngestionPipeline:
    @pytest.mark.asyncio
    async def test_run_unknown_source_raises(self):
        registry = ConnectorRegistry()
        pipeline = IngestionPipeline(registry)
        with pytest.raises(ValueError, match="Unknown source"):
            await pipeline.run("no_such_source", "table1", "/tmp/output")
