"""Task router — routes tasks to agents based on capability, load, and affinity."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ai4s.common.logging import get_logger

logger = get_logger(__name__)


class RoutingStrategy(str, Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_BUSY = "least_busy"
    PRIORITY_AWARE = "priority_aware"
    AFFINITY = "affinity"                 # Sticky routing based on task tag
    RANDOM = "random"
    WEIGHTED = "weighted"                 # Weight by agent capacity


@dataclass
class AgentInfo:
    agent_id: str
    capabilities: set[str] = field(default_factory=set)
    current_load: int = 0               # Active tasks
    max_capacity: int = 10
    weight: float = 1.0
    status: str = "online"               # online | busy | draining | offline
    last_heartbeat: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class TaskRouter:
    """Routes incoming tasks to the optimal agent instance.

    Usage::

        router = TaskRouter(strategy=RoutingStrategy.LEAST_BUSY)
        router.register_agent("agent-1", ["run_simulation", "train_model"], max_capacity=10)
        router.register_agent("agent-2", ["infer", "query_db"], max_capacity=5)

        agent_id = router.route("run_simulation", available_tags=["gpu"])
    """

    def __init__(self, strategy: RoutingStrategy = RoutingStrategy.LEAST_BUSY) -> None:
        self.strategy = strategy
        self._agents: dict[str, AgentInfo] = {}
        self._rr_counters: dict[str, int] = {}

    # -- registration -------------------------------------------------------

    def register_agent(
        self,
        agent_id: str,
        capabilities: list[str],
        max_capacity: int = 10,
        weight: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._agents[agent_id] = AgentInfo(
            agent_id=agent_id,
            capabilities=set(capabilities),
            max_capacity=max_capacity,
            weight=weight,
            metadata=metadata or {},
        )
        self._rr_counters[agent_id] = 0
        logger.info("Agent registered: %s (caps=%s, capacity=%d)", agent_id, capabilities, max_capacity)

    def unregister_agent(self, agent_id: str) -> None:
        self._agents.pop(agent_id, None)
        self._rr_counters.pop(agent_id, None)
        logger.info("Agent unregistered: %s", agent_id)

    def update_load(self, agent_id: str, load: int) -> None:
        if agent_id in self._agents:
            self._agents[agent_id].current_load = load

    def heartbeat(self, agent_id: str) -> None:
        from datetime import datetime, timezone

        if agent_id in self._agents:
            self._agents[agent_id].last_heartbeat = datetime.now(timezone.utc).isoformat()
            self._agents[agent_id].status = "online"

    # -- routing ------------------------------------------------------------

    def route(
        self,
        task_action: str,
        required_tags: list[str] | None = None,
        exclude_agents: list[str] | None = None,
    ) -> str | None:
        """Select the best agent for the given action.

        Returns agent_id or None if no suitable agent is available.
        """
        exclude = set(exclude_agents or [])

        # Filter: capability match + online + not excluded
        eligible = [
            a for a in self._agents.values()
            if a.agent_id not in exclude
            and a.status in ("online", "busy")
            and task_action in a.capabilities
            and a.current_load < a.max_capacity
        ]

        # Filter by required tags in metadata
        if required_tags:
            eligible = [
                a for a in eligible
                if all(t in a.metadata.get("tags", []) for t in required_tags)
            ]

        if not eligible:
            logger.warning("No eligible agent for action=%s tags=%s", task_action, required_tags)
            return None

        # Apply routing strategy
        if self.strategy == RoutingStrategy.ROUND_ROBIN:
            return self._round_robin(eligible)
        elif self.strategy == RoutingStrategy.LEAST_BUSY:
            return self._least_busy(eligible)
        elif self.strategy == RoutingStrategy.PRIORITY_AWARE:
            return self._priority_aware(eligible)
        elif self.strategy == RoutingStrategy.AFFINITY:
            return self._affinity(eligible, task_action)
        elif self.strategy == RoutingStrategy.WEIGHTED:
            return self._weighted(eligible)
        elif self.strategy == RoutingStrategy.RANDOM:
            return random.choice(eligible).agent_id
        else:
            return eligible[0].agent_id

    # -- strategies ---------------------------------------------------------

    def _round_robin(self, agents: list[AgentInfo]) -> str:
        # Pick agent with lowest round-robin counter
        best = min(agents, key=lambda a: self._rr_counters.get(a.agent_id, 0))
        self._rr_counters[best.agent_id] += 1
        return best.agent_id

    @staticmethod
    def _least_busy(agents: list[AgentInfo]) -> str:
        # Pick agent with lowest load ratio (current / max)
        return min(agents, key=lambda a: a.current_load / max(a.max_capacity, 1)).agent_id

    @staticmethod
    def _priority_aware(agents: list[AgentInfo]) -> str:
        # Prefer agents with higher weight and lower load
        scored = sorted(
            agents,
            key=lambda a: (a.current_load / max(a.max_capacity, 1)) / max(a.weight, 0.1),
        )
        return scored[0].agent_id

    def _affinity(self, agents: list[AgentInfo], action: str) -> str:
        # Prefer agents that have recently handled similar actions
        # Simple implementation: RR on agents that have the action tag
        tagged = [a for a in agents if action in a.metadata.get("action_history", [])]
        if tagged:
            return self._round_robin(tagged)
        return self._round_robin(agents)

    def _weighted(self, agents: list[AgentInfo]) -> str:
        total_weight = sum(a.weight for a in agents)
        if total_weight == 0:
            return agents[0].agent_id
        r = random.random() * total_weight
        cumulative = 0.0
        for a in agents:
            cumulative += a.weight
            if r <= cumulative:
                return a.agent_id
        return agents[-1].agent_id

    # -- query --------------------------------------------------------------

    def list_agents(self) -> list[AgentInfo]:
        return list(self._agents.values())

    def get_agent(self, agent_id: str) -> AgentInfo | None:
        return self._agents.get(agent_id)

    def agent_summary(self) -> dict[str, Any]:
        agents = list(self._agents.values())
        return {
            "total": len(agents),
            "online": sum(1 for a in agents if a.status == "online"),
            "busy": sum(1 for a in agents if a.status == "busy"),
            "total_capacity": sum(a.max_capacity for a in agents),
            "total_load": sum(a.current_load for a in agents),
            "capability_matrix": {
                a.agent_id: list(a.capabilities) for a in agents
            },
        }
