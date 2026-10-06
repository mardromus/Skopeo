"""Structured logging.

Every record carries: timestamp, level, logger, investigation_id, agent, event_type,
severity and correlation_id (when relevant). All messages pass through secret redaction.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime

from app.security.redaction import redact, redact_obj

investigation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("investigation_id", default=None)
agent_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("agent", default=None)

_STRUCTURED_FIELDS = ("investigation_id", "agent", "event_type", "severity", "correlation_id")


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "investigation_id", None):
            record.investigation_id = investigation_id_var.get()
        if not getattr(record, "agent", None):
            record.agent = agent_var.get()
        for name in ("event_type", "severity", "correlation_id"):
            if not hasattr(record, name):
                setattr(record, name, None)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        for name in _STRUCTURED_FIELDS:
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        extra = getattr(record, "data", None)
        if extra:
            payload["data"] = redact_obj(extra)
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ctx = " ".join(f"{name}={getattr(record, name)}" for name in _STRUCTURED_FIELDS if getattr(record, name, None))
        base = f"{datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec='seconds')} {record.levelname:<7} {record.name}: {redact(record.getMessage())}"
        if ctx:
            base += f" [{ctx}]"
        if record.exc_info:
            base += "\n" + redact(self.formatException(record.exc_info))
        return base


_configured = False


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    global _configured
    root = logging.getLogger("skopeo")
    root.setLevel(level.upper())
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_output else TextFormatter())
    handler.addFilter(_ContextFilter())
    root.addHandler(handler)
    root.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"skopeo.{name}")
    return logger
