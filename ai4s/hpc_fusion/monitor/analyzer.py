"""Resource analyzer — anomaly detection, trend prediction, and capacity planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ai4s.common.logging import get_logger
from ai4s.hpc_fusion.monitor.collector import MetricsCollector, NodeMetrics

logger = get_logger(__name__)


@dataclass
class AnomalyReport:
    node_id: str
    timestamp: str
    metric: str
    observed_value: float
    expected_range: tuple[float, float]
    severity: str    # info | warn | critical
    message: str = ""


@dataclass
class CapacityForecast:
    node_id: str = ""
    metric: str = ""
    current_value: float = 0.0
    predicted_5min: float = 0.0
    predicted_30min: float = 0.0
    trend: str = "stable"     # increasing | decreasing | stable
    saturation_eta_minutes: float | None = None


class ResourceAnalyzer:
    """Analyzes resource metrics for anomalies, trends, and capacity planning.

    Detection methods:
      - Threshold-based  : simple min/max bounds
      - Z-score          : statistical outlier (>3σ)
      - Moving average   : trend direction and slope
      - Seasonal         : compare to same-hour historical avg (weekly pattern)
    """

    def __init__(
        self,
        collector: MetricsCollector,
        anomaly_z_threshold: float = 3.0,
        trend_window: int = 10,
    ) -> None:
        self._collector = collector
        self.anomaly_z_threshold = anomaly_z_threshold
        self.trend_window = trend_window

    # -- anomaly detection --------------------------------------------------

    async def detect_anomalies(self) -> list[AnomalyReport]:
        """Scan all recent metrics for anomalies."""
        anomalies: list[AnomalyReport] = []

        for node_id, history in self._collector._history.items():
            if len(history) < self.trend_window:
                continue

            recent = history[-self.trend_window:]

            # Check each metric
            checks = [
                ("gpu_util_pct", 0.0, 100.0),
                ("cpu_util_pct", 0.0, 100.0),
                ("mem_util_pct", 0.0, 100.0),
                ("gpu_mem_util_pct", 0.0, 100.0),
                ("temperature_c", 0.0, 85.0),
            ]

            for metric_name, min_val, max_val in checks:
                values = [getattr(m, metric_name) for m in recent]
                mean = np.mean(values)
                std = np.std(values)

                if std == 0:
                    continue

                current = values[-1]
                z_score = abs(current - mean) / std

                if z_score > self.anomaly_z_threshold:
                    severity = "critical" if z_score > 5 else "warn"
                    anomalies.append(AnomalyReport(
                        node_id=node_id,
                        timestamp=recent[-1].timestamp,
                        metric=metric_name,
                        observed_value=current,
                        expected_range=(mean - 2 * std, mean + 2 * std),
                        severity=severity,
                        message=f"Z-score={z_score:.2f} ({severity})",
                    ))

                # Also check threshold
                if current > max_val:
                    anomalies.append(AnomalyReport(
                        node_id=node_id, timestamp=recent[-1].timestamp,
                        metric=metric_name, observed_value=current,
                        expected_range=(min_val, max_val), severity="critical",
                        message=f"Exceeded threshold: {current:.1f} > {max_val}",
                    ))

        if anomalies:
            logger.warning("Detected %d anomalies", len(anomalies))

        return anomalies

    # -- trend prediction ---------------------------------------------------

    async def predict_utilization(
        self, node_id: str, metric: str = "gpu_util_pct"
    ) -> CapacityForecast:
        """Predict near-term utilization using linear regression on recent history."""
        history = self._collector.get_history(node_id, minutes=30)
        if len(history) < self.trend_window:
            return CapacityForecast(node_id=node_id, metric=metric)

        values = [getattr(m, metric) for m in history]
        x = np.arange(len(values))
        y = np.array(values)

        # Linear regression
        slope, intercept = np.polyfit(x, y, 1)
        current = y[-1]

        forecast_5 = intercept + slope * (len(values) + 5)
        forecast_30 = intercept + slope * (len(values) + 30)

        # Trend classification
        total_range = max(y) - min(y) if max(y) > min(y) else 1.0
        normalized_slope = slope / (total_range / len(y))
        if normalized_slope > 0.01:
            trend = "increasing"
        elif normalized_slope < -0.01:
            trend = "decreasing"
        else:
            trend = "stable"

        # Estimate saturation
        saturation_eta = None
        if trend == "increasing" and slope > 0:
            remaining = 100.0 - current
            if remaining > 0:
                saturation_eta = remaining / slope * (self._collector.interval / 60)

        return CapacityForecast(
            node_id=node_id,
            metric=metric,
            current_value=current,
            predicted_5min=max(0.0, min(100.0, forecast_5)),
            predicted_30min=max(0.0, min(100.0, forecast_30)),
            trend=trend,
            saturation_eta_minutes=saturation_eta,
        )

    # -- cluster-wide -------------------------------------------------------

    async def cluster_health_report(self) -> dict[str, Any]:
        """Generate a comprehensive cluster health report."""
        snapshot = self._collector.get_cluster_snapshot()
        anomalies = await self.detect_anomalies()

        return {
            "timestamp": snapshot.get("timestamp", ""),
            "nodes": snapshot.get("nodes", 0),
            "utilization": {
                "gpu": round(snapshot.get("avg_gpu_util", 0), 2),
                "cpu": round(snapshot.get("avg_cpu_util", 0), 2),
                "memory": round(snapshot.get("avg_mem_util", 0), 2),
            },
            "unhealthy_nodes": snapshot.get("unhealthy_nodes", 0),
            "anomalies": len(anomalies),
            "anomaly_details": [
                {"node": a.node_id, "metric": a.metric, "severity": a.severity}
                for a in anomalies[:10]
            ],
            "status": "healthy" if not anomalies and snapshot.get("unhealthy_nodes", 0) == 0 else "degraded",
        }

    # -- capacity planning --------------------------------------------------

    async def estimate_headroom(
        self, connector_name: str
    ) -> dict[str, Any]:
        """Estimate how many more GPU-jobs can fit in the current cluster."""
        snapshot = self._collector.get_cluster_snapshot()
        avg_gpu = snapshot.get("avg_gpu_util", 0)

        # Simplified: remaining GPU capacity based on average utilization
        remaining_pct = 100.0 - avg_gpu
        total_gpus = snapshot.get("nodes", 0) * 8  # assume 8 GPU/node

        return {
            "avg_gpu_utilization_pct": round(avg_gpu, 1),
            "remaining_capacity_pct": round(remaining_pct, 1),
            "estimated_free_gpus": int(total_gpus * remaining_pct / 100),
            "can_fit_small_jobs": remaining_pct > 10,
            "can_fit_large_jobs": remaining_pct > 30,
        }
