"""Base HPC connector interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class JobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUSPENDED = "suspended"


@dataclass
class HPCJob:
    job_id: str
    name: str
    state: JobState
    partition: str
    nodes: int
    gpus_per_node: int
    cpu_cores: int
    memory_mb: int
    wall_time_min: int
    submit_time: str
    start_time: str | None = None
    end_time: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NodeInfo:
    node_id: str
    state: str                  # idle, allocated, down, drain
    cpu_total: int
    cpu_alloc: int
    mem_total_mb: int
    mem_alloc_mb: int
    gpu_total: int
    gpu_alloc: int
    partitions: list[str] = field(default_factory=list)


class HPCConnector(ABC):
    """Abstract connector for HPC resource managers (Slurm, K8s, etc.)."""

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        self.name = name
        self.config = config

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def submit_job(self, job_spec: dict[str, Any]) -> str:
        """Submit a job, return job_id."""

    @abstractmethod
    async def cancel_job(self, job_id: str) -> bool: ...

    @abstractmethod
    async def get_job(self, job_id: str) -> HPCJob: ...

    @abstractmethod
    async def list_jobs(self, partition: str | None = None) -> list[HPCJob]: ...

    @abstractmethod
    async def get_nodes(self) -> list[NodeInfo]: ...

    @abstractmethod
    async def get_queue_status(self) -> dict[str, int]:
        """Return {partition: pending_count}."""
