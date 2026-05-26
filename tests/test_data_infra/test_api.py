"""Integration tests for data_infra API."""

import pytest
from fastapi.testclient import TestClient

from ai4s.data_infra.api import (
    get_catalog,
    get_config,
    get_lineage,
    get_registry,
    get_snapshots,
    router,
)
from fastapi import FastAPI

# ---- reset globals before each test ----


@pytest.fixture(autouse=True)
def reset_globals():
    import ai4s.data_infra.api as api_mod

    api_mod._registry = None
    api_mod._catalog = None
    api_mod._snapshots = None
    api_mod._lineage = None
    api_mod._config = None
    yield


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestConnectorRoutes:
    def test_list_connectors_empty(self, client):
        resp = client.get("/api/v1/data/connectors")
        assert resp.status_code == 200
        assert resp.json()["sources"] == []

    def test_register_and_list(self, client):
        resp = client.post("/api/v1/data/connectors", json={
            "name": "test_source", "source_type": "local",
            "config": {"root_path": "/tmp"},
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "registered"

        resp = client.get("/api/v1/data/connectors")
        assert "test_source" in resp.json()["sources"]

    def test_unregister_connector(self, client):
        client.post("/api/v1/data/connectors", json={
            "name": "tmp", "source_type": "local", "config": {"root_path": "/tmp"},
        })
        resp = client.delete("/api/v1/data/connectors/tmp")
        assert resp.status_code == 200

    def test_register_bad_type(self, client):
        resp = client.post("/api/v1/data/connectors", json={
            "name": "bad", "source_type": "invalid_type", "config": {},
        })
        assert resp.status_code == 400


class TestSchemaRoutes:
    def test_register_and_get_schema(self, client):
        resp = client.post("/api/v1/data/schemas", json={
            "table": "experiment_a",
            "columns": {"id": "int64", "name": "string"},
            "required": ["id"],
        })
        assert resp.status_code == 200

        resp = client.get("/api/v1/data/schemas/experiment_a")
        assert resp.status_code == 200
        assert "id" in resp.json()["columns"]

    def test_get_missing_schema(self, client):
        resp = client.get("/api/v1/data/schemas/nonexistent")
        assert resp.status_code == 404


class TestCatalogRoutes:
    def test_register_and_search(self, client):
        resp = client.post("/api/v1/data/catalog", json={
            "name": "research.results.v1",
            "description": "ML experiment results",
            "owner": "team-ml",
            "columns": [{"name": "id", "dtype": "int64"}, {"name": "accuracy", "dtype": "float64"}],
            "location": "s3://data-lake/results",
            "format": "parquet",
            "tags": ["ml", "experiment"],
        })
        assert resp.status_code == 200

        resp = client.get("/api/v1/data/catalog?tag=ml")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

        resp = client.get("/api/v1/data/catalog?keyword=experiment")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

        resp = client.get("/api/v1/data/catalog/research.results.v1")
        assert resp.status_code == 200
        assert resp.json()["owner"] == "team-ml"

    def test_summary(self, client):
        client.post("/api/v1/data/catalog", json={
            "name": "d1", "description": "", "owner": "a",
            "columns": [], "location": "", "tags": [],
        })
        resp = client.get("/api/v1/data/catalog/summary")
        assert resp.status_code == 200
        assert resp.json()["total_datasets"] == 1


class TestSnapshotRoutes:
    def test_create_and_list(self, client, tmp_path):
        snap_dir = tmp_path / "snaps"
        snap_dir.mkdir()

        resp = client.post("/api/v1/data/snapshots", json={
            "dataset": "test_ds",
            "source_path": str(snap_dir),
            "tags": {"version": "v1"},
        })
        assert resp.status_code == 200
        snap_id = resp.json()["snapshot_id"]

        resp = client.get("/api/v1/data/snapshots?dataset=test_ds")
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

        resp = client.get(f"/api/v1/data/snapshots/{snap_id}")
        assert resp.status_code == 200


class TestLineageRoutes:
    def test_get_lineage(self, client):
        # First register a dataset and run ingestion to create lineage
        resp = client.get("/api/v1/data/lineage/research.results.v1")
        assert resp.status_code == 200
        assert "upstream" in resp.json()

    def test_mermaid(self, client):
        resp = client.get("/api/v1/data/lineage/test_ds/mermaid")
        assert resp.status_code == 200
        assert "mermaid" in resp.json()
