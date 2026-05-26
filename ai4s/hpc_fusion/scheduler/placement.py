"""Resource placement — selects optimal nodes via bin-packing heuristics."""

from __future__ import annotations

from typing import Any

from ai4s.common.logging import get_logger
from ai4s.hpc_fusion.connector.base import HPCConnector, NodeInfo

logger = get_logger(__name__)


class ResourcePlacement:
    """Selects optimal compute nodes for job execution.

    Strategies:
      - best_fit   : minimize wasted resources (preferred for GPU jobs)
      - first_fit  : first node with enough capacity (fastest)
      - worst_fit  : maximize remaining capacity per node (spread load)
      - affinity   : prefer nodes in same rack/switch (for MPI jobs)
      - topology   : prefer nodes with NVLink/IB connectivity
    """

    def __init__(
        self,
        connectors: dict[str, HPCConnector],
        strategy: str = "best_fit",
        topology_aware: bool = False,
    ) -> None:
        self._connectors = connectors
        self.strategy = strategy
        self.topology_aware = topology_aware

    # ------------------------------------------------------------------

    async def find_placement(
        self,
        connector_name: str,
        gpus: int,
        cpus: int = 1,
        memory_mb: int = 0,
        nodes: int = 1,
        prefer_partition: str | None = None,
        exclude_nodes: list[str] | None = None,
    ) -> list[NodeInfo] | None:
        connector = self._connectors.get(connector_name)
        if not connector:
            logger.error("Unknown connector: %s", connector_name)
            return None

        all_nodes = await connector.get_nodes()
        exclude = set(exclude_nodes or [])

        # Filter candidates
        candidates = [
            n for n in all_nodes
            if n.node_id not in exclude
            and n.state in ("idle", "ready", "IDLE")
            and (n.gpu_total - n.gpu_alloc) >= gpus
            and (n.cpu_total - n.cpu_alloc) >= cpus
            and (n.mem_total_mb - n.mem_alloc_mb) >= memory_mb
        ]

        # Filter by partition
        if prefer_partition:
            candidates = [
                n for n in candidates
                if not n.partitions or prefer_partition in n.partitions
            ]

        if len(candidates) < nodes:
            logger.info(
                "Insufficient nodes: need=%d have=%d (gpus=%d cpus=%d mem=%dMB)",
                nodes, len(candidates), gpus, cpus, memory_mb,
            )
            return None

        # Apply strategy
        if self.strategy == "best_fit":
            selected = self._best_fit(candidates, gpus, cpus, memory_mb, nodes)
        elif self.strategy == "first_fit":
            selected = candidates[:nodes]
        elif self.strategy == "worst_fit":
            selected = self._worst_fit(candidates, gpus, cpus, memory_mb, nodes)
        else:
            selected = self._best_fit(candidates, gpus, cpus, memory_mb, nodes)

        logger.info("Placement: %d nodes for %s (strategy=%s)",
                     len(selected), connector_name, self.strategy)
        return selected

    # -- strategies ---------------------------------------------------------

    @staticmethod
    def _best_fit(
        candidates: list[NodeInfo],
        gpus: int, cpus: int, memory_mb: int, nodes: int,
    ) -> list[NodeInfo]:
        """Minimize wasted resources — best for GPU jobs."""
        scored = []
        for n in candidates:
            free_gpu = n.gpu_total - n.gpu_alloc - gpus
            free_cpu = n.cpu_total - n.cpu_alloc - cpus
            free_mem = n.mem_total_mb - n.mem_alloc_mb - memory_mb
            waste = free_gpu * 1000 + free_cpu + free_mem / 1000
            scored.append((n, waste))

        scored.sort(key=lambda x: x[1])
        return [n for n, _ in scored[:nodes]]

    @staticmethod
    def _worst_fit(
        candidates: list[NodeInfo],
        gpus: int, cpus: int, memory_mb: int, nodes: int,
    ) -> list[NodeInfo]:
        """Maximize remaining capacity — spreads load."""
        scored = []
        for n in candidates:
            free_gpu = n.gpu_total - n.gpu_alloc - gpus
            scored.append((n, -free_gpu))  # Negative for descending by free space

        scored.sort(key=lambda x: x[1])  # Most free GPU first
        return [n for n, _ in scored[:nodes]]

    # -- single-node --------------------------------------------------------

    async def fit_to_single_node(
        self,
        connector_name: str,
        gpus: int,
        cpus: int = 1,
        memory_mb: int = 0,
        prefer_partition: str | None = None,
    ) -> NodeInfo | None:
        result = await self.find_placement(
            connector_name, gpus, cpus, memory_mb, nodes=1,
            prefer_partition=prefer_partition,
        )
        return result[0] if result else None

    # -- node scoring -------------------------------------------------------

    async def score_nodes(
        self,
        connector_name: str,
        gpus: int,
    ) -> dict[str, float]:
        """Return suitability score (0-1) for each node."""
        connector = self._connectors.get(connector_name)
        if not connector:
            return {}

        nodes = await connector.get_nodes()
        scores: dict[str, float] = {}
        for n in nodes:
            if n.gpu_total == 0:
                scores[n.node_id] = 0.0
                continue

            free_gpu = n.gpu_total - n.gpu_alloc
            free_ratio = free_gpu / n.gpu_total
            fits = 1.0 if free_gpu >= gpus else 0.0
            idle_bonus = 1.0 if n.state == "idle" else 0.5
            scores[n.node_id] = free_ratio * 0.5 + fits * 0.3 + idle_bonus * 0.2

        return scores
