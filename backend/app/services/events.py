"""Event bus: every inter-agent message and state transition is persisted as an ExecutionEvent.

The execution trace shown in the UI is read straight from this table — it is never synthesised.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from app.database import session_scope
from app.models import ExecutionEvent, utcnow
from app.observability import get_logger
from app.security.redaction import redact, redact_obj

log = get_logger("events")


class EventBus:
    def emit(
        self,
        investigation_id: str,
        sender: str,
        event_type: str,
        message: str,
        *,
        receiver: str = "blackboard",
        payload: dict[str, Any] | None = None,
        severity: str = "info",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        clean_payload = redact_obj(payload or {})
        clean_message = redact(message)[:2000]
        with session_scope(write=True) as s:
            seq = (s.scalar(select(func.max(ExecutionEvent.seq)).where(ExecutionEvent.investigation_id == investigation_id)) or 0) + 1
            event = ExecutionEvent(
                investigation_id=investigation_id,
                seq=seq,
                sender=sender,
                receiver=receiver,
                event_type=str(event_type),
                severity=severity,
                message=clean_message,
                correlation_id=correlation_id,
                payload=clean_payload,
                timestamp=utcnow(),
            )
            s.add(event)
            s.flush()
            event_id = event.id
        log.info(
            clean_message,
            extra={
                "investigation_id": investigation_id,
                "agent": sender,
                "event_type": str(event_type),
                "severity": severity,
                "correlation_id": correlation_id,
            },
        )
        return {"event_id": event_id, "seq": seq}
