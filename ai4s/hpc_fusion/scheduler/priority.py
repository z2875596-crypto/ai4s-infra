"""Job prioritizer — multi-factor priority scoring for fair-share scheduling."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class PrioritizedJob:
    job_spec: dict[str, Any]
    priority: float = 0.0
    job_id: str = ""
    factors: dict[str, float] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class JobPrioritizer:
    """Multi-factor job prioritization.

    Factors (all normalized to [0, 1], weighted sum):
      - queue_priority : explicit priority from user (1-10, inverted: 1=highest)
      - fairshare      : historical usage — less used → higher priority
      - resource       : smaller jobs get slight boost (backfill friendly)
      - age            : waiting time in queue (starvation prevention)
      - project        : project-level priority boost

    Final priority = Σ(factor_score × weight)

    Configurable weights allow tuning for:
      - Research cluster  : fairshare-heavy
      - Production cluster: queue_priority-heavy
      - Shared cluster    : balanced
    """

    def __init__(
        self,
        queue_weight: float = 0.35,
        fairshare_weight: float = 0.30,
        resource_weight: float = 0.15,
        age_weight: float = 0.10,
        project_weight: float = 0.10,
    ) -> None:
        self.weights = {
            "queue": queue_weight,
            "fairshare": fairshare_weight,
            "resource": resource_weight,
            "age": age_weight,
            "project": project_weight,
        }
        # Track usage per user/project for fair-share
        self._user_gpu_hours: dict[str, float] = {}
        self._project_gpu_hours: dict[str, float] = {}
        self._project_priority: dict[str, float] = {}

    # ------------------------------------------------------------------

    def prioritize(self, job_spec: dict[str, Any]) -> PrioritizedJob:
        factors: dict[str, float] = {}

        # 1. Queue priority (1=highest, 10=lowest)
        q = job_spec.get("priority", 5)
        factors["queue"] = ((10 - min(max(q, 1), 10)) / 9) * self.weights["queue"]

        # 2. Fair-share (lower historical usage → higher priority)
        user = job_spec.get("user", "unknown")
        user_used = self._user_gpu_hours.get(user, 0.0)
        # Normalize: users with <1 GPU-hour get full fairshare, >1000 get near 0
        factors["fairshare"] = max(0.0, (1.0 - min(user_used / 1000.0, 1.0))) * self.weights["fairshare"]

        # 3. Resource efficiency (smaller jobs boosted for backfill)
        gpus = job_spec.get("gpus", 0)
        factors["resource"] = (1.0 / (1.0 + gpus * 0.25)) * self.weights["resource"]

        # 4. Age (starts at 0, increases over time)
        factors["age"] = 0.0 * self.weights["age"]

        # 5. Project priority
        project = job_spec.get("project", "default")
        proj_prio = self._project_priority.get(project, 0.5)
        factors["project"] = proj_prio * self.weights["project"]

        total = sum(factors.values())
        return PrioritizedJob(
            job_spec=job_spec,
            priority=total,
            factors=factors,
        )

    # -- usage tracking -----------------------------------------------------

    def record_usage(self, user: str, gpu_hours: float, project: str | None = None) -> None:
        self._user_gpu_hours[user] = self._user_gpu_hours.get(user, 0.0) + gpu_hours
        if project:
            self._project_gpu_hours[project] = self._project_gpu_hours.get(project, 0.0) + gpu_hours

    def set_project_priority(self, project: str, priority: float) -> None:
        """Set priority for a project (0.0-1.0, default 0.5)."""
        self._project_priority[project] = max(0.0, min(1.0, priority))

    def get_user_usage(self, user: str) -> float:
        return self._user_gpu_hours.get(user, 0.0)

    def get_project_usage(self, project: str) -> float:
        return self._project_gpu_hours.get(project, 0.0)

    # -- aging (called per scheduling cycle) --------------------------------

    def apply_aging(self, pending_jobs: list[PrioritizedJob], cycle_seconds: float = 5.0) -> None:
        """Boost priority for long-waiting jobs to prevent starvation."""
        for job in pending_jobs:
            age_boost = cycle_seconds / 3600.0 * self.weights["age"]  # Per hour
            job.factors["age"] = min(job.factors.get("age", 0) + age_boost, self.weights["age"])
            job.priority = sum(job.factors.values())

    # -- reset --------------------------------------------------------------

    def reset_usage(self, user: str | None = None) -> None:
        if user:
            self._user_gpu_hours.pop(user, None)
        else:
            self._user_gpu_hours.clear()
            self._project_gpu_hours.clear()

    def decay_usage(self, half_life_days: float = 30.0) -> None:
        """Exponentially decay historical usage (daily call recommended)."""
        import math

        decay = math.exp(-math.log(2) / half_life_days)
        for k in self._user_gpu_hours:
            self._user_gpu_hours[k] *= decay
        for k in self._project_gpu_hours:
            self._project_gpu_hours[k] *= decay
