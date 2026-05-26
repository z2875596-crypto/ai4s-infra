"""FastAPI routes for hpc_fusion — job scheduling, node monitoring, alerts."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ai4s.common.config import Config
from ai4s.common.logging import get_logger
from ai4s.hpc_fusion.connector.base import HPCConnector
from ai4s.hpc_fusion.connector.k8s import K8sConnector
from ai4s.hpc_fusion.connector.slurm import SlurmConnector
from ai4s.hpc_fusion.monitor.alert import AlertManager, AlertSeverity
from ai4s.hpc_fusion.monitor.analyzer import ResourceAnalyzer
from ai4s.hpc_fusion.monitor.collector import MetricsCollector
from ai4s.hpc_fusion.scheduler.engine import SchedulingEngine, SchedulingPolicy
from ai4s.hpc_fusion.scheduler.placement import ResourcePlacement
from ai4s.hpc_fusion.scheduler.priority import JobPrioritizer

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# globals
# ---------------------------------------------------------------------------

_connectors: dict[str, HPCConnector] | None = None
_engine: SchedulingEngine | None = None
_collector: MetricsCollector | None = None
_analyzer: ResourceAnalyzer | None = None
_alert_mgr: AlertManager | None = None


def get_connectors() -> dict[str, HPCConnector]:
    global _connectors
    if _connectors is None:
        cfg = Config()
        _connectors = {
            "slurm": SlurmConnector("slurm", cfg.hpc_fusion.get("connectors", {}).get("slurm", {})),
            "k8s": K8sConnector("k8s", cfg.hpc_fusion.get("connectors", {}).get("kubernetes", {})),
        }
    return _connectors


def get_engine() -> SchedulingEngine:
    global _engine
    if _engine is None:
        _engine = SchedulingEngine(get_connectors())
    return _engine


def get_collector() -> MetricsCollector:
    global _collector
    if _collector is None:
        _collector = MetricsCollector(get_connectors())
    return _collector


def get_analyzer() -> ResourceAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = ResourceAnalyzer(get_collector())
    return _analyzer


def get_alert_mgr() -> AlertManager:
    global _alert_mgr
    if _alert_mgr is None:
        _alert_mgr = AlertManager()
    return _alert_mgr


# ---------------------------------------------------------------------------
# router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/hpc", tags=["hpc-fusion"])

# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------


class SubmitJobRequest(BaseModel):
    name: str = "ai4s-job"
    connector: str = "slurm"
    nodes: int = 1
    gpus: int = 1
    cpus: int = 4
    memory_mb: int = 32000
    partition: str = ""
    time_minutes: int = 60
    script: str = "#!/bin/bash\nhostname"
    priority: int = 5
    user: str = "unknown"
    project: str = "default"
    metadata: dict[str, Any] | None = None


class SendAlertRequest(BaseModel):
    title: str
    message: str
    severity: str = "warn"
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# job routes
# ---------------------------------------------------------------------------


@router.post("/jobs")
async def submit_job(req: SubmitJobRequest):
    engine = get_engine()
    job_spec = {
        "name": req.name,
        "connector": req.connector,
        "nodes": req.nodes,
        "gpus": req.gpus,
        "cpus": req.cpus,
        "memory_mb": req.memory_mb,
        "partition": req.partition,
        "time": req.time_minutes,
        "script": req.script,
        "priority": req.priority,
        "user": req.user,
        "project": req.project,
    }
    try:
        job_id = await engine.submit(job_spec, connector_name=req.connector)
        if job_id:
            return {"job_id": job_id, "status": "scheduled"}
        else:
            return {"job_id": None, "status": "queued"}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    engine = get_engine()
    connector_name = engine._job_connector_map.get(job_id)
    if not connector_name:
        raise HTTPException(404, f"Job '{job_id}' not found")

    connector = get_connectors()[connector_name]
    job = await connector.get_job(job_id)
    return {
        "job_id": job.job_id, "name": job.name, "state": job.state.value,
        "partition": job.partition, "nodes": job.nodes, "gpus_per_node": job.gpus_per_node,
    }


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    engine = get_engine()
    ok = await engine.cancel_job(job_id)
    if ok:
        return {"status": "cancelled", "job_id": job_id}
    raise HTTPException(404, f"Job '{job_id}' not found or already completed")


@router.get("/jobs")
async def list_jobs(connector: str = "slurm", partition: str | None = None):
    connectors = get_connectors()
    conn = connectors.get(connector)
    if not conn:
        raise HTTPException(400, f"Unknown connector: {connector}")
    jobs = await conn.list_jobs(partition=partition)
    return {
        "count": len(jobs),
        "jobs": [{"job_id": j.job_id, "name": j.name, "state": j.state.value} for j in jobs],
    }


# ---------------------------------------------------------------------------
# scheduling routes
# ---------------------------------------------------------------------------


@router.get("/scheduler/status")
async def scheduler_status():
    engine = get_engine()
    return await engine.get_status()


@router.post("/scheduler/cycle")
async def run_schedule_cycle():
    engine = get_engine()
    n = await engine.schedule_cycle()
    return {"scheduled": n}


@router.get("/scheduler/pending")
async def pending_jobs():
    engine = get_engine()
    return {"pending": engine.pending_jobs}


@router.get("/scheduler/events")
async def scheduler_events(n: int = 50):
    engine = get_engine()
    return {"events": await engine.get_recent_events(n)}


# ---------------------------------------------------------------------------
# node / metrics routes
# ---------------------------------------------------------------------------


@router.get("/nodes")
async def list_nodes(connector: str = "slurm"):
    connectors = get_connectors()
    conn = connectors.get(connector)
    if not conn:
        raise HTTPException(400, f"Unknown connector: {connector}")

    try:
        await conn.connect()
        nodes = await conn.get_nodes()
        await conn.disconnect()
        return {
            "count": len(nodes),
            "nodes": [
                {"node_id": n.node_id, "state": n.state,
                 "gpu_free": n.gpu_total - n.gpu_alloc,
                 "gpu_total": n.gpu_total,
                 "cpu_free": n.cpu_total - n.cpu_alloc}
                for n in nodes
            ],
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/metrics/cluster")
async def cluster_metrics():
    collector = get_collector()
    await collector.collect_once()
    return collector.get_cluster_snapshot()


@router.get("/metrics/nodes/{node_id}")
async def node_metrics(node_id: str, minutes: int = 30):
    collector = get_collector()
    history = collector.get_history(node_id, minutes=minutes)
    return {"node_id": node_id, "data_points": len(history),
            "latest": {
                "gpu_util": history[-1].gpu_util_pct if history else None,
                "cpu_util": history[-1].cpu_util_pct if history else None,
                "temperature": history[-1].temperature_c if history else None,
            } if history else None}


@router.get("/metrics/headroom")
async def capacity_headroom(connector: str = "slurm"):
    analyzer = get_analyzer()
    return await analyzer.estimate_headroom(connector)


# ---------------------------------------------------------------------------
# analysis routes
# ---------------------------------------------------------------------------


@router.get("/analysis/anomalies")
async def detect_anomalies():
    collector = get_collector()
    await collector.collect_once()
    analyzer = get_analyzer()
    anomalies = await analyzer.detect_anomalies()
    return {"count": len(anomalies), "anomalies": [
        {"node": a.node_id, "metric": a.metric, "severity": a.severity, "message": a.message}
        for a in anomalies
    ]}


@router.get("/analysis/predict/{node_id}")
async def predict_utilization(node_id: str, metric: str = "gpu_util_pct"):
    analyzer = get_analyzer()
    forecast = await analyzer.predict_utilization(node_id, metric)
    return {
        "node_id": forecast.node_id,
        "metric": forecast.metric,
        "current": forecast.current_value,
        "predicted_5min": forecast.predicted_5min,
        "predicted_30min": forecast.predicted_30min,
        "trend": forecast.trend,
        "saturation_eta_minutes": forecast.saturation_eta_minutes,
    }


@router.get("/analysis/health")
async def cluster_health():
    analyzer = get_analyzer()
    return await analyzer.cluster_health_report()


# ---------------------------------------------------------------------------
# alert routes
# ---------------------------------------------------------------------------


@router.post("/alerts")
async def send_alert(req: SendAlertRequest):
    mgr = get_alert_mgr()
    try:
        sev = AlertSeverity(req.severity)
    except ValueError:
        raise HTTPException(400, f"Invalid severity '{req.severity}'")
    alert = await mgr.send_alert(req.title, req.message, sev, req.metadata)
    return alert.to_dict()


@router.get("/alerts/active")
async def active_alerts():
    return {"alerts": get_alert_mgr().get_active_alerts()}


@router.get("/alerts/history")
async def alert_history(severity: str | None = None, limit: int = 50):
    return {"alerts": get_alert_mgr().get_alert_history(severity=severity, limit=limit)}


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    await get_alert_mgr().resolve_alert(alert_id)
    return {"status": "resolved", "alert_id": alert_id}


# ---------------------------------------------------------------------------
# resource placement
# ---------------------------------------------------------------------------


@router.get("/placement/score")
async def score_nodes(gpus: int = 1, connector: str = "slurm"):
    placement = ResourcePlacement(get_connectors())
    scores = await placement.score_nodes(connector, gpus)
    return {"scores": scores}
