"""Alert manager — routes alerts via Slack, PagerDuty, email, and webhooks."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from ai4s.common.logging import get_logger

logger = get_logger(__name__)


class AlertSeverity(str, Enum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


@dataclass
class Alert:
    alert_id: str
    title: str
    message: str
    severity: AlertSeverity = AlertSeverity.WARN
    source: str = "ai4s-hpc"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "title": self.title,
            "message": self.message,
            "severity": self.severity.value,
            "source": self.source,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "acknowledged": self.acknowledged,
            "resolved": self.resolved,
        }


# ---------------------------------------------------------------------------
# AlertManager
# ---------------------------------------------------------------------------


class AlertManager:
    """Routes alerts to configured notification channels.

    Supports:
      - Slack incoming webhook
      - PagerDuty Events API v2
      - Generic webhook (for custom integrations)
      - Console / log (always enabled)

    Alert deduplication: within a configurable window, identical alerts
    are suppressed (de-duplicated).
    """

    def __init__(
        self,
        channels: list[str] | None = None,
        slack_webhook_url: str | None = None,
        pagerduty_routing_key: str | None = None,
        webhook_url: str | None = None,
        dedup_window_sec: float = 300.0,    # 5 minutes
    ) -> None:
        self._channels = channels or ["slack", "log"]
        self._slack_webhook = slack_webhook_url
        self._pagerduty_key = pagerduty_routing_key
        self._webhook_url = webhook_url
        self._dedup_window = dedup_window_sec

        self._history: list[Alert] = []
        self._active_alerts: dict[str, Alert] = {}   # Unresolved alerts
        self._fired_recently: dict[str, float] = {}  # dedup key → timestamp

    # -- send alert ---------------------------------------------------------

    async def send_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity = AlertSeverity.WARN,
        metadata: dict[str, Any] | None = None,
    ) -> Alert:
        import uuid

        # Dedup check
        dedup_key = f"{severity.value}:{title}"
        now_ts = datetime.now(timezone.utc).timestamp()
        last = self._fired_recently.get(dedup_key, 0)
        if now_ts - last < self._dedup_window:
            logger.debug("Alert suppressed (dedup): %s", title)
            # Return a stub (not persisted)
            return Alert(
                alert_id="deduped", title=title, message=message,
                severity=severity, metadata=metadata or {},
            )

        self._fired_recently[dedup_key] = now_ts

        alert = Alert(
            alert_id=uuid.uuid4().hex[:12],
            title=title,
            message=message,
            severity=severity,
            metadata=metadata or {},
        )

        self._history.append(alert)
        self._active_alerts[alert.alert_id] = alert

        # Fan-out to all channels
        tasks = []
        for channel in self._channels:
            if channel == "slack" and self._slack_webhook:
                tasks.append(self._send_slack(alert))
            elif channel == "pagerduty" and self._pagerduty_key:
                tasks.append(self._send_pagerduty(alert))
            elif channel == "webhook" and self._webhook_url:
                tasks.append(self._send_webhook(alert))
            elif channel == "log":
                self._log_alert(alert)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        return alert

    # -- channel implementations --------------------------------------------

    async def _send_slack(self, alert: Alert) -> None:
        import httpx

        color = {"info": "#36a64f", "warn": "#ffcc00", "critical": "#dc3545"}[alert.severity.value]

        payload = {
            "attachments": [{
                "color": color,
                "title": f"[{alert.severity.value.upper()}] {alert.title}",
                "text": alert.message,
                "fields": [
                    {"title": "Source", "value": alert.source, "short": True},
                    {"title": "Time", "value": alert.timestamp, "short": True},
                ],
                "footer": "AI4S HPC Monitor",
            }]
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(self._slack_webhook, json=payload)
            if resp.status_code >= 400:
                logger.error("Slack alert failed: %s — %s", resp.status_code, resp.text)

    async def _send_pagerduty(self, alert: Alert) -> None:
        import httpx

        severity_map = {
            AlertSeverity.INFO: "info",
            AlertSeverity.WARN: "warning",
            AlertSeverity.CRITICAL: "critical",
        }

        payload = {
            "routing_key": self._pagerduty_key,
            "event_action": "trigger",
            "payload": {
                "summary": alert.title,
                "severity": severity_map[alert.severity],
                "source": alert.source,
                "custom_details": alert.metadata,
            },
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
            )
            if resp.status_code >= 400:
                logger.error("PagerDuty alert failed: %s", resp.status_code)

    async def _send_webhook(self, alert: Alert) -> None:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(self._webhook_url, json=alert.to_dict())
            if resp.status_code >= 400:
                logger.error("Webhook alert failed: %s", resp.status_code)

    def _log_alert(self, alert: Alert) -> None:
        log_fn = {
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARN: logger.warning,
            AlertSeverity.CRITICAL: logger.error,
        }[alert.severity]
        log_fn("[%s] %s: %s", alert.severity.value.upper(), alert.title, alert.message)

    # -- predefined alerts --------------------------------------------------

    async def send_node_down(self, node_id: str) -> Alert:
        return await self.send_alert(
            title=f"Node DOWN: {node_id}",
            message=f"Node {node_id} is unreachable or has no heartbeat.",
            severity=AlertSeverity.CRITICAL,
            metadata={"node_id": node_id, "type": "node_down"},
        )

    async def send_resource_pressure(self, resource: str, util_pct: float) -> Alert:
        sev = AlertSeverity.CRITICAL if util_pct > 95 else AlertSeverity.WARN
        return await self.send_alert(
            title=f"Resource pressure: {resource} at {util_pct:.1f}%",
            message=f"Cluster {resource} utilization has reached {util_pct:.1f}%.",
            severity=sev,
            metadata={"resource": resource, "utilization_pct": util_pct, "type": "resource_pressure"},
        )

    async def send_gpu_ecc_error(self, node_id: str, gpu_index: int, error_count: int) -> Alert:
        return await self.send_alert(
            title=f"GPU ECC errors: {node_id}:GPU{gpu_index}",
            message=f"Detected {error_count} ECC errors on GPU {gpu_index} of node {node_id}.",
            severity=AlertSeverity.CRITICAL,
            metadata={"node_id": node_id, "gpu_index": gpu_index, "error_count": error_count, "type": "gpu_ecc"},
        )

    async def send_temperature_warning(self, node_id: str, temp_c: float) -> Alert:
        return await self.send_alert(
            title=f"High temperature: {node_id} at {temp_c:.0f}C",
            message=f"GPU temperature on node {node_id} is {temp_c:.0f}C (threshold: 85C).",
            severity=AlertSeverity.CRITICAL if temp_c > 85 else AlertSeverity.WARN,
            metadata={"node_id": node_id, "temperature_c": temp_c, "type": "temperature"},
        )

    async def send_job_queue_depth(self, queue_name: str, pending: int) -> Alert:
        if pending < 100:
            return None
        sev = AlertSeverity.CRITICAL if pending > 500 else AlertSeverity.WARN
        return await self.send_alert(
            title=f"Job queue depth: {queue_name} has {pending} pending",
            message=f"Queue '{queue_name}' has {pending} pending jobs.",
            severity=sev,
            metadata={"queue": queue_name, "pending_count": pending, "type": "queue_depth"},
        )

    # -- alert lifecycle ----------------------------------------------------

    async def resolve_alert(self, alert_id: str) -> None:
        if alert_id in self._active_alerts:
            self._active_alerts[alert_id].resolved = True
            logger.info("Alert resolved: %s", alert_id)

    def get_active_alerts(self) -> list[dict[str, Any]]:
        return [
            a.to_dict() for a in self._active_alerts.values()
            if not a.resolved
        ]

    def get_alert_history(self, severity: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        results = self._history
        if severity:
            results = [a for a in results if a.severity.value == severity]
        return [a.to_dict() for a in results[-limit:]]
