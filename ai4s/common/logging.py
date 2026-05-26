"""Structured logging with OpenTelemetry trace context injection."""

from __future__ import annotations

import logging
import sys
from typing import Any


class JsonFormatter(logging.Formatter):
    """JSON-line formatter for structured log ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import datetime, timezone

        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            payload["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "__dict__", {})
        for key in ("otel_trace_id", "otel_span_id", "module", "task_id"):
            if key in extra:
                payload[key] = extra[key]
        return json.dumps(payload, default=str)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
