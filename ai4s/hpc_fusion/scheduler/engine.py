"""Scheduling engine — coordinates job scheduling across HPC and K8s backends.

Policy matrix:
  ┌──────────────┬──────────┬───────────┬──────────┐
  │              │ Slurm    │ K8s       │ Both     │
  ├──────────────┼──────────┼───────────┼──────────┤
  │ fair_share   │ default  │ Kueue     │ hybrid   │
  │ priority     │ QoS      │ Priority  │ gated    │
  │ backfill     │ built-in │ Volcano   │ adaptive │
  │ preemptive   │ signal   │ evict     │ selective│
  └──────────────┴──────────┴───────────┴──────────┘
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ai4s.common.exceptions import ResourceExhaustedError, SchedulingError
from ai4s.common.logging import get_logger
from ai4s.common.metrics import MetricsRegistry
from ai4s.hpc_fusion.connector.base import HPCConnector, HPCJob, JobState
from ai4s.hpc_fusion.scheduler.placement import ResourcePlacement
from ai4s.hpc_fusion.scheduler.priority import JobPrioritizer, PrioritizedJob

logger = get_logger(__name__)


@dataclass
class SchedulingPolicy:
    name: str = "fair_share"       # fair_share | fifo | priority | preemptive
    preemption: bool = False
    backfill: bool = True
    gang_scheduling: bool = False   # All-or-nothing for multi-node jobs
    max_jobs_per_user: int = 1000
    max_jobs_total: int = 10000
    schedule_interval_sec: float = 5.0


@dataclass
class SchedulingEvent:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: str = ""           # submit | schedule | preempt | complete | fail
    job_id: str = ""
    connector: str = ""
    detail: str = ""


class SchedulingEngine:
    """Core scheduling engine for HPC/AI workloads.

    Responsibilities:
      1. Accept job submissions
      2. Apply prioritization
      3. Find resource placement
      4. Submit to backend connector or enqueue
      5. Run periodic scheduling cycles for queued jobs
      6. Record scheduling events for auditing
    """

    def __init__(
        self,
        connectors: dict[str, HPCConnector],
        policy: SchedulingPolicy | None = None,
        prioritizer: JobPrioritizer | None = None,
        placement: ResourcePlacement | None = None,
    ) -> None:
        self._connectors = connectors
        self.policy = policy or SchedulingPolicy()
        self._prioritizer = prioritizer or JobPrioritizer()
        self._placement = placement or ResourcePlacement(connectors)

        # State
        self._pending_jobs: list[PrioritizedJob] = []
        self._running_jobs: dict[str, HPCJob] = {}
        self._job_connector_map: dict[str, str] = {}  # job_id → connector_name
        self._events: list[SchedulingEvent] = []
        self._total_submitted = 0

    # -- submit -------------------------------------------------------------

    async def submit(
        self,
        job_spec: dict[str, Any],
        connector_name: str = "slurm",
    ) -> str:
        """Submit a job: prioritize → try to schedule now or enqueue."""
        connector = self._connectors.get(connector_name)
        if not connector:
            raise SchedulingError(f"Unknown connector: {connector_name}")

        if len(self._running_jobs) >= self.policy.max_jobs_total:
            raise ResourceExhaustedError(f"Max jobs ({self.policy.max_jobs_total}) reached")

        self._total_submitted += 1
        prioritized = self._prioritizer.prioritize(job_spec)

        # Try immediate scheduling
        if await self._can_schedule_now(prioritized, connector_name):
            job_id = await self._schedule_now(prioritized, connector_name)
            self._record_event("submit", job_id, connector_name, "immediate")
            return job_id

        # Enqueue
        self._pending_jobs.append(prioritized)
        MetricsRegistry.hpc_queue_depth.labels(queue_name=connector_name).inc()
        self._record_event("submit", "", connector_name,
                           f"queued (pos={len(self._pending_jobs)})")
        logger.info("Job queued: %s (pos=%d, priority=%.3f)",
                     job_spec.get("name", "unknown"),
                     len(self._pending_jobs), prioritized.priority)
        return ""

    async def _schedule_now(self, job: PrioritizedJob, connector_name: str) -> str:
        connector = self._connectors[connector_name]
        job_id = await connector.submit_job(job.job_spec)
        job.job_id = job_id

        self._running_jobs[job_id] = HPCJob(
            job_id=job_id,
            name=job.job_spec.get("name", ""),
            state=JobState.PENDING,
            partition=job.job_spec.get("partition", ""),
            nodes=job.job_spec.get("nodes", 1),
            gpus_per_node=job.job_spec.get("gpus_per_node", 0),
            cpu_cores=job.job_spec.get("cpus", 1),
            memory_mb=job.job_spec.get("memory_mb", 0),
            wall_time_min=job.job_spec.get("wall_time_min", 0),
            submit_time=datetime.now(timezone.utc).isoformat(),
        )
        self._job_connector_map[job_id] = connector_name

        return job_id

    # -- scheduling cycle ---------------------------------------------------

    async def schedule_cycle(self) -> int:
        """Run one scheduling cycle: try to place queued jobs.

        Returns number of jobs scheduled this cycle.
        """
        if not self._pending_jobs:
            return 0

        # Sort by priority (descending), then by age
        self._pending_jobs.sort(
            key=lambda j: (j.priority, j.created_at),
            reverse=True,
        )

        remaining: list[PrioritizedJob] = []
        scheduled = 0

        for job in self._pending_jobs:
            connector_name = job.job_spec.get("connector", "slurm")
            if await self._can_schedule_now(job, connector_name):
                try:
                    job_id = await self._schedule_now(job, connector_name)
                    self._record_event("schedule", job_id, connector_name, "backfill")
                    scheduled += 1
                except Exception as exc:
                    logger.warning("Schedule attempt failed: %s", exc)
                    remaining.append(job)
            else:
                # Age-based priority boost
                job.factors["age"] = min(job.factors.get("age", 0) + 0.01, 0.5)
                job.priority = sum(job.factors.values())
                remaining.append(job)

        self._pending_jobs = remaining
        if scheduled:
            logger.info("Scheduling cycle: %d jobs placed, %d still pending",
                         scheduled, len(remaining))

        return scheduled

    async def _can_schedule_now(self, job: PrioritizedJob, connector_name: str) -> bool:
        if not self.policy.backfill and self._pending_jobs:
            return False

        gpus_needed = job.job_spec.get("gpus", 0)
        if gpus_needed == 0:
            return True

        try:
            placement = self._placement
            result = await placement.find_placement(
                connector_name=connector_name,
                gpus=job.job_spec.get("gpus", 0),
                cpus=job.job_spec.get("cpus", 1),
                memory_mb=job.job_spec.get("memory_mb", 0),
                nodes=job.job_spec.get("nodes", 1),
                prefer_partition=job.job_spec.get("partition"),
            )
            return result is not None and len(result) >= job.job_spec.get("nodes", 1)
        except Exception:
            return True  # If we can't check, allow submission

    # -- job lifecycle ------------------------------------------------------

    async def update_job_states(self) -> None:
        """Sync running job states from connectors."""
        for job_id, connector_name in list(self._job_connector_map.items()):
            connector = self._connectors.get(connector_name)
            if not connector:
                continue
            try:
                updated = await connector.get_job(job_id)
                old_state = self._running_jobs.get(job_id, HPCJob(
                    job_id="", name="", state=JobState.PENDING,
                    partition="", nodes=0, gpus_per_node=0,
                    cpu_cores=0, memory_mb=0, wall_time_min=0,
                    submit_time="",
                )).state

                self._running_jobs[job_id] = updated

                if updated.state != old_state:
                    if updated.state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED):
                        MetricsRegistry.hpc_job_duration.labels(
                            partition=updated.partition
                        ).observe(0)  # In production: compute actual duration

            except Exception as exc:
                logger.debug("Failed to update job %s: %s", job_id, exc)

    async def cancel_job(self, job_id: str) -> bool:
        connector_name = self._job_connector_map.get(job_id)
        if not connector_name:
            return False

        connector = self._connectors[connector_name]
        result = await connector.cancel_job(job_id)
        if result:
            self._running_jobs.pop(job_id, None)
            self._job_connector_map.pop(job_id, None)
            self._record_event("complete", job_id, connector_name, "cancelled")
        return result

    # -- preemption ---------------------------------------------------------

    async def preempt_job(self, job_id: str, reason: str = "preempted") -> bool:
        """Preempt a running job to free resources for higher-priority work."""
        if not self.policy.preemption:
            return False

        cancelled = await self.cancel_job(job_id)
        if cancelled:
            self._record_event("preempt", job_id, self._job_connector_map.get(job_id, ""), reason)
        return cancelled

    # -- status -------------------------------------------------------------

    async def get_status(self) -> dict[str, Any]:
        queues = {}
        for name, conn in self._connectors.items():
            try:
                queues[name] = await conn.get_queue_status()
            except Exception:
                queues[name] = {"error": "unreachable"}

        return {
            "policy": self.policy.name,
            "total_submitted": self._total_submitted,
            "pending": len(self._pending_jobs),
            "running": len(self._running_jobs),
            "queues": queues,
            "preemption_enabled": self.policy.preemption,
            "backfill_enabled": self.policy.backfill,
        }

    async def get_recent_events(self, n: int = 50) -> list[dict[str, Any]]:
        return [{
            "ts": e.timestamp, "type": e.event_type,
            "job_id": e.job_id, "connector": e.connector, "detail": e.detail,
        } for e in self._events[-n:]]

    # -- helpers ------------------------------------------------------------

    def _record_event(self, event_type: str, job_id: str, connector: str, detail: str) -> None:
        self._events.append(SchedulingEvent(
            event_type=event_type, job_id=job_id, connector=connector, detail=detail,
        ))

    @property
    def pending_jobs(self) -> list[dict[str, Any]]:
        return [{
            "spec": j.job_spec, "priority": j.priority, "factors": j.factors,
        } for j in self._pending_jobs]
