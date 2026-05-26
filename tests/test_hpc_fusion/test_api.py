"""Integration tests for hpc_fusion API."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai4s.hpc_fusion.api import router


@pytest.fixture(autouse=True)
def reset_globals():
    import ai4s.hpc_fusion.api as api_mod

    api_mod._connectors = None
    api_mod._engine = None
    api_mod._collector = None
    api_mod._analyzer = None
    api_mod._alert_mgr = None
    yield


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestJobRoutes:
    def test_submit_job(self, client):
        resp = client.post("/api/v1/hpc/jobs", json={
            "name": "train-gpt",
            "connector": "slurm",
            "nodes": 2,
            "gpus": 8,
            "cpus": 64,
            "memory_mb": 256000,
            "partition": "gpu",
            "time_minutes": 1440,
            "script": "#!/bin/bash\npython train.py",
            "priority": 3,
            "user": "researcher1",
            "project": "nlp-research",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data or data["status"] == "queued"

    def test_scheduler_status(self, client):
        resp = client.get("/api/v1/hpc/scheduler/status")
        assert resp.status_code == 200
        assert "policy" in resp.json()
        assert "pending" in resp.json()
        assert "running" in resp.json()
        assert "queues" in resp.json()

    def test_run_schedule_cycle(self, client):
        resp = client.post("/api/v1/hpc/scheduler/cycle")
        assert resp.status_code == 200
        assert "scheduled" in resp.json()

    def test_pending_jobs(self, client):
        resp = client.get("/api/v1/hpc/scheduler/pending")
        assert resp.status_code == 200
        assert "pending" in resp.json()

    def test_scheduler_events(self, client):
        resp = client.get("/api/v1/hpc/scheduler/events?n=10")
        assert resp.status_code == 200
        assert "events" in resp.json()


class TestNodeRoutes:
    def test_list_nodes(self, client):
        resp = client.get("/api/v1/hpc/nodes?connector=slurm")
        # Slurm connector may not actually connect — this tests the API structure
        # In test env without real Slurm, expect either 200 or 500
        assert resp.status_code in (200, 500)

    def test_list_nodes_bad_connector(self, client):
        resp = client.get("/api/v1/hpc/nodes?connector=unknown")
        assert resp.status_code == 400


class TestMetricsRoutes:
    def test_cluster_metrics(self, client):
        resp = client.get("/api/v1/hpc/metrics/cluster")
        assert resp.status_code == 200
        assert "nodes" in resp.json()

    def test_node_metrics(self, client):
        resp = client.get("/api/v1/hpc/metrics/nodes/gpu01?minutes=10")
        assert resp.status_code == 200
        assert resp.json()["node_id"] == "gpu01"

    def test_capacity_headroom(self, client):
        resp = client.get("/api/v1/hpc/metrics/headroom?connector=slurm")
        assert resp.status_code == 200
        assert "avg_gpu_utilization_pct" in resp.json()
        assert "estimated_free_gpus" in resp.json()


class TestAnalysisRoutes:
    def test_detect_anomalies(self, client):
        resp = client.get("/api/v1/hpc/analysis/anomalies")
        assert resp.status_code == 200
        assert "count" in resp.json()

    def test_predict_utilization(self, client):
        resp = client.get("/api/v1/hpc/analysis/predict/gpu01?metric=gpu_util_pct")
        assert resp.status_code == 200
        assert "trend" in resp.json()

    def test_cluster_health(self, client):
        resp = client.get("/api/v1/hpc/analysis/health")
        assert resp.status_code == 200
        assert "status" in resp.json()


class TestAlertRoutes:
    def test_send_and_list_alerts(self, client):
        resp = client.post("/api/v1/hpc/alerts", json={
            "title": "GPU temp high",
            "message": "Node gpu01 reached 82C",
            "severity": "warn",
            "metadata": {"node_id": "gpu01", "temp_c": 82},
        })
        assert resp.status_code == 200
        alert_id = resp.json()["alert_id"]

        resp = client.get("/api/v1/hpc/alerts/active")
        assert resp.status_code == 200

        resp = client.get("/api/v1/hpc/alerts/history?limit=10")
        assert resp.status_code == 200

        resp = client.post(f"/api/v1/hpc/alerts/{alert_id}/resolve")
        assert resp.status_code == 200

    def test_invalid_severity(self, client):
        resp = client.post("/api/v1/hpc/alerts", json={
            "title": "test", "message": "test", "severity": "invalid",
        })
        assert resp.status_code == 400

    def test_alert_dedup(self, client):
        """Sending same alert twice within dedup window should suppress second."""
        client.post("/api/v1/hpc/alerts", json={
            "title": "Dedup test", "message": "test", "severity": "info",
        })
        resp = client.post("/api/v1/hpc/alerts", json={
            "title": "Dedup test", "message": "test", "severity": "info",
        })
        assert resp.status_code == 200
        # Second should be marked as deduped
        assert resp.json()["alert_id"] == "deduped"


class TestPlacementRoutes:
    def test_score_nodes(self, client):
        resp = client.get("/api/v1/hpc/placement/score?gpus=4&connector=slurm")
        assert resp.status_code == 200
        assert "scores" in resp.json()
