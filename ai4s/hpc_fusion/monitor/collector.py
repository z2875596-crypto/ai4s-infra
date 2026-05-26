"""Metrics collector — periodically gathers resource metrics from all HPC/K8s nodes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ai4s.common.logging import get_logger
from ai4s.common.metrics import MetricsRegistry
from ai4s.hpc_fusion.connector.base import HPCConnector, NodeInfo

logger = get_logger(__name__)


@dataclass
class NodeMetrics:
    node_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # Utilization (0-100)
    cpu_util_pct: float = 0.0
    mem_util_pct: float = 0.0
    gpu_util_pct: float = 0.0
    gpu_mem_util_pct: float = 0.0
    # IO
    disk_read_mbps: float = 0.0
    disk_write_mbps: float = 0.0
    network_rx_mbps: float = 0.0
    network_tx_mbps: float = 0.0
    # Health
    temperature_c: float = 0.0
    power_watts: float = 0.0
    # Derived
    gpu_efficiency: float = 0.0         # GPU util / power (higher = better)

    @property
    def healthy(self) -> bool:
        return (
            self.temperature_c < 85.0
            and self.gpu_util_pct < 100.0   # Not thermal-throttling
        )


class MetricsCollector:
    """Periodic resource metrics collector.

    Feeds:
      - Prometheus gauges (ai4s_hpc_*)
      - Time-series history for analysis/alerting
      - Real-time dashboard data

    Usage::

        collector = MetricsCollector({"slurm": slurm_conn, "k8s": k8s_conn})
        await collector.start()   # runs in background
        ...
        await collector.stop()
    """

    def __init__(
        self,
        connectors: dict[str, HPCConnector],
        interval_sec: int = 10,
        history_retention_min: int = 60,
    ) -> None:
        self._connectors = connectors
        self.interval = interval_sec
        self._history: dict[str, list[NodeMetrics]] = {}
        self._history_retention = history_retention_min
        self._running = False
        self._task: asyncio.Task[None] | None = None

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Metrics collector started (interval=%ds)", self.interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Metrics collector stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.collect_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Metrics collection error: %s", exc)
            await asyncio.sleep(self.interval)

    # -- collection ---------------------------------------------------------

    async def collect_once(self) -> dict[str, list[NodeMetrics]]:
        """Collect one round of metrics from all connectors."""
        results: dict[str, list[NodeMetrics]] = {}

        for name, conn in self._connectors.items():
            try:
                nodes = await conn.get_nodes()
                metrics_list: list[NodeMetrics] = []

                for node in nodes:
                    m = self._node_info_to_metrics(node)
                    metrics_list.append(m)

                    # Update Prometheus gauges
                    MetricsRegistry.hpc_node_utilization.labels(
                        node_id=node.node_id, resource_type="gpu"
                    ).set(m.gpu_util_pct / 100.0)
                    MetricsRegistry.hpc_node_utilization.labels(
                        node_id=node.node_id, resource_type="cpu"
                    ).set(m.cpu_util_pct / 100.0)
                    MetricsRegistry.hpc_node_utilization.labels(
                        node_id=node.node_id, resource_type="memory"
                    ).set(m.mem_util_pct / 100.0)

                    # Store in history
                    self._history.setdefault(node.node_id, []).append(m)

                results[name] = metrics_list
                logger.debug("Collected metrics from %s: %d nodes", name, len(metrics_list))

            except Exception as exc:
                logger.error("Failed to collect from connector %s: %s", name, exc)

        self._trim_history()
        return results

    def _node_info_to_metrics(self, node: NodeInfo) -> NodeMetrics:
        return NodeMetrics(
            node_id=node.node_id,
            cpu_util_pct=(node.cpu_alloc / max(node.cpu_total, 1)) * 100,
            mem_util_pct=(node.mem_alloc_mb / max(node.mem_total_mb, 1)) * 100,
            gpu_util_pct=(node.gpu_alloc / max(node.gpu_total, 1)) * 100,
            gpu_mem_util_pct=0.0,  # Requires GPU-level metrics (DCGM in production)
            # In production: read from DCGM, Prometheus node_exporter, or nvidia-smi
        )

    # -- history ------------------------------------------------------------

    def get_history(self, node_id: str, minutes: int = 30) -> list[NodeMetrics]:
        entries = self._history.get(node_id, [])
        if not entries:
            return []
        cutoff = datetime.now(timezone.utc).timestamp() - minutes * 60
        return [
            e for e in entries
            if datetime.fromisoformat(e.timestamp).timestamp() >= cutoff
        ]

    def get_cluster_snapshot(self) -> dict[str, Any]:
        """Aggregated view across all nodes."""
        all_metrics: list[NodeMetrics] = []
        for entries in self._history.values():
            if entries:
                all_metrics.append(entries[-1])

        if not all_metrics:
            return {"nodes": 0}

        import statistics

        return {
            "nodes": len(all_metrics),
            "avg_gpu_util": statistics.mean(m.gpu_util_pct for m in all_metrics),
            "max_gpu_util": max(m.gpu_util_pct for m in all_metrics),
            "avg_cpu_util": statistics.mean(m.cpu_util_pct for m in all_metrics),
            "avg_mem_util": statistics.mean(m.mem_util_pct for m in all_metrics),
            "unhealthy_nodes": sum(1 for m in all_metrics if not m.healthy),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _trim_history(self) -> None:
        """Remove entries older than retention period."""
        max_entries = (self._history_retention * 60) // self.interval
        for node_id in list(self._history.keys()):
            if len(self._history[node_id]) > max_entries:
                self._history[node_id] = self._history[node_id][-max_entries:]
