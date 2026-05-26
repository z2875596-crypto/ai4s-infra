#!/usr/bin/env python3
"""AI4S Infrastructure — unified FastAPI entry point.

Mounts all four module API routers plus shared health/metrics endpoints.

Usage:
    python main.py                          # start on :8000
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    AI4S_DATA_INFRA__INGESTION__BATCH_SIZE=5000 python main.py
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from ai4s.common.config import Config
from ai4s.common.logging import get_logger
from ai4s.common.metrics import MetricsRegistry

# ── API routers ──────────────────────────────────────────────────────────

from ai4s.data_infra.api import router as data_router
from ai4s.agent_runtime.api import router as agent_router

logger = get_logger("ai4s.main")

# Optional heavy-dependency modules — server starts even if they're unavailable
_available_modules: dict[str, bool] = {
    "data_infra": True,
    "agent_runtime": True,
    "rlhf": False,
    "hpc_fusion": False,
}

rlhf_router = None
try:
    from ai4s.rlhf.api import router as rlhf_router  # type: ignore[no-redef]
    _available_modules["rlhf"] = True
except ImportError as e:
    logger.warning("RLHF module unavailable (missing deps): %s", e)

hpc_router = None
try:
    from ai4s.hpc_fusion.api import router as hpc_router  # type: ignore[no-redef]
    _available_modules["hpc_fusion"] = True
except ImportError as e:
    logger.warning("HPC Fusion module unavailable (missing deps): %s", e)

# ── Application ──────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    config = Config()
    active = [m for m, ok in _available_modules.items() if ok]
    logger.info("AI4S Infrastructure starting (version=%s)", __import__("ai4s").__version__)
    logger.info("Active modules: %s", ", ".join(active))
    inactive = [m for m, ok in _available_modules.items() if not ok]
    if inactive:
        logger.warning("Inactive modules (missing deps): %s", ", ".join(inactive))
    yield
    logger.info("AI4S Infrastructure shutting down")


app = FastAPI(
    title="AI4S Infrastructure",
    description="Unified AI-for-Science platform: data, RLHF, agent runtime, HPC fusion.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── Middleware ───────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────

app.include_router(data_router)
app.include_router(agent_router)
if rlhf_router is not None:
    app.include_router(rlhf_router)
if hpc_router is not None:
    app.include_router(hpc_router)

# ── Shared endpoints ─────────────────────────────────────────────────────


@app.get("/", tags=["root"])
async def root():
    return {
        "service": "AI4S Infrastructure",
        "version": "0.1.0",
        "modules": {
            "data_infra": {"prefix": "/api/v1/data", "available": _available_modules["data_infra"]},
            "rlhf": {"prefix": "/api/v1/rlhf", "available": _available_modules["rlhf"]},
            "agent_runtime": {"prefix": "/api/v1/agent", "available": _available_modules["agent_runtime"]},
            "hpc_fusion": {"prefix": "/api/v1/hpc", "available": _available_modules["hpc_fusion"]},
        },
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
    }


@app.get("/health", tags=["health"])
async def health():
    """Kubernetes-style health check."""
    return {"status": "healthy", "modules": [m for m, ok in _available_modules.items() if ok]}


@app.get("/health/ready", tags=["health"])
async def readiness():
    """Readiness probe — checks if all sub-systems are responsive."""
    checks = {m: ("ok" if ok else "unavailable") for m, ok in _available_modules.items()}
    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        content={"ready": all_ok, "checks": checks},
        status_code=200 if all_ok else 503,
    )


@app.get("/metrics", tags=["metrics"])
async def metrics():
    """Prometheus metrics endpoint."""
    return PlainTextResponse(
        content=MetricsRegistry.export().decode(),
        media_type="text/plain; version=0.0.4",
    )


@app.get("/api/v1/config", tags=["config"])
async def get_config():
    """Return non-sensitive config subset."""
    cfg = Config()
    return {
        "data_infra": {
            "ingestion_batch_size": cfg.data_infra.get("ingestion", {}).get("batch_size"),
            "cleaning_mode": cfg.data_infra.get("cleaning", {}).get("validation_mode"),
        },
        "rlhf": {
            "algorithm": cfg.rlhf.get("policy", {}).get("algorithm"),
        },
        "agent_runtime": {
            "sandbox": cfg.agent_runtime.get("tools", {}).get("sandbox_type"),
            "memory_backend": cfg.agent_runtime.get("memory", {}).get("backend"),
        },
        "hpc_fusion": {
            "engine": cfg.hpc_fusion.get("scheduler", {}).get("engine"),
        },
    }


# ── Main ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
