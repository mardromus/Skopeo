"""Build notification messages from investigations and watch reports, and dispatch them."""

from __future__ import annotations

from typing import Any

from app.notifications.service import PRIORITY_RANK, NotificationService
from app.notifications.transports import Message
from app.services.evidence_store import EvidenceStore

IMPACT_SEVERITY = {"breaking": "critical", "high": "critical", "medium": "warning", "low": "info", "none": "info"}


def notify_investigation_finished(notifier: NotificationService, store: EvidenceStore, investigation_id: str) -> list[dict[str, Any]]:
    inv = store.get_investigation(investigation_id)
    if inv is None or not inv.owner_id or inv.status in ("queued", "running"):
        return []
    url = notifier.link(f"/investigations/{inv.id}")
    results: list[dict[str, Any]] = []
    if inv.status in ("failed", "cancelled"):
        msg = Message(
            event="investigation.failed",
            subject=f"Skopeo: investigation of {inv.repository_name} {inv.status}",
            text=(inv.error or f"The investigation ended with status {inv.status}.")[:1500],
            severity="warning",
            url=url,
            fields=[("Repository", inv.repository_name), ("Branch", inv.branch), ("Status", inv.status)],
            data={"investigation_id": inv.id, "status": inv.status},
        )
        return notifier.safe_dispatch(inv.owner_id, "investigation.failed", msg, {"investigation_id": inv.id})

    risks = sorted(store.list_risks(inv.id), key=lambda r: (PRIORITY_RANK.get(r.priority, 9), -r.score))
    summary = inv.execution_summary or {}
    top = risks[0].priority if risks else None
    score = f"{inv.overall_risk_score:.0f} ({inv.overall_risk_level})" if inv.overall_risk_score is not None else "n/a"
    items = [f"{r.priority} · {r.title} (score {r.score:.0f})" for r in risks[:6]]
    fields = [
        ("Repository", inv.repository_name),
        ("Status", inv.status.replace("_", " ")),
        ("Overall risk", score),
        ("Verified findings", str(summary.get("verified", "-"))),
        ("Rejected by red team", str(summary.get("rejected", "-"))),
    ]
    completed = Message(
        event="investigation.completed",
        subject=f"Skopeo: {inv.repository_name} scored {score}",
        text=(
            f"The investigation of {inv.repository_name} ({inv.branch}) finished with status {inv.status.replace('_', ' ')}. "
            + (f"The top risk is {risks[0].priority}: {risks[0].title}." if risks else "No verified risks were scored.")
        ),
        severity="critical" if top in ("P0", "P1") else "success",
        url=url,
        fields=fields,
        items=items,
        data={"investigation_id": inv.id, "overall_risk_score": inv.overall_risk_score, "top_priority": top},
    )
    context = {"investigation_id": inv.id, "top_priority": top}
    results += notifier.safe_dispatch(inv.owner_id, "investigation.completed", completed, context)
    if top is not None:
        urgent = [f"{r.priority} · {r.title}" for r in risks if PRIORITY_RANK.get(r.priority, 9) <= 2][:8]
        risk_msg = Message(
            event="investigation.risk",
            subject=f"Skopeo: {top} risk in {inv.repository_name}",
            text=f"{risks[0].title}\n\n{risks[0].rationale[:800]}",
            severity="critical" if top in ("P0", "P1") else "warning",
            url=url,
            fields=fields,
            items=urgent,
            data={
                "investigation_id": inv.id,
                "top_priority": top,
                "risks": [{"priority": r.priority, "title": r.title, "score": r.score} for r in risks[:10]],
            },
        )
        results += notifier.safe_dispatch(inv.owner_id, "investigation.risk", risk_msg, context)
    return results
