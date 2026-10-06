"""Human-in-the-loop action approval.

Nothing is executed without an explicit approval. With DRY_RUN=true (default) an approval is
recorded as ``approved_dry_run`` and no external call is made. Skopeo only ever *creates* issues
or *draft* pull requests — it never merges, deploys, deletes, force-pushes or rotates credentials.
"""

from __future__ import annotations

import re

from app.config import Settings
from app.models import utcnow
from app.schemas import EventType
from app.schemas.investigation import ActionProposalOut, ApproveActionRequest
from app.services.events import EventBus
from app.services.evidence_store import EvidenceStore
from app.tools.github import GitHubClient, GitHubError


class ActionError(ValueError):
    pass


def decide_action(
    store: EvidenceStore, events: EventBus, settings: Settings, investigation_id: str, req: ApproveActionRequest
) -> ActionProposalOut:
    action = store.get_action(req.action_id)
    if action is None or not any(a.action_id == req.action_id for a in store.list_actions(investigation_id)):
        raise ActionError("action not found for this investigation")
    if action.status != "proposed":
        raise ActionError(f"action already decided ({action.status})")
    who = re.sub(r"[^\w.@ -]", "", req.approved_by)[:128]
    if req.decision == "reject":
        updated = store.update_action(action.action_id, status="rejected", approved_by=who, decision_note=req.note, decided_at=utcnow())
        events.emit(
            investigation_id,
            "human",
            EventType.ACTION_DECIDED,
            f"{who} rejected action '{action.title}'",
            receiver="orchestrator",
            payload={"action_id": action.action_id, "decision": "reject"},
        )
        return updated
    executable = bool((action.result or {}).get("executable"))
    if settings.dry_run or not executable:
        reason = "DRY_RUN=true" if settings.dry_run else "GitHub actions not enabled for this investigation / not a GitHub repository"
        updated = store.update_action(
            action.action_id,
            status="approved_dry_run",
            approved_by=who,
            decision_note=req.note,
            decided_at=utcnow(),
            result={
                **(action.result or {}),
                "dry_run": True,
                "reason": reason,
                "would_execute": f"create {action.action_type} on {action.target_repository}",
            },
        )
        events.emit(
            investigation_id,
            "human",
            EventType.ACTION_DECIDED,
            f"{who} approved '{action.title}' — recorded only ({reason}); nothing was executed",
            receiver="orchestrator",
            payload={"action_id": action.action_id, "decision": "approve", "dry_run": True},
        )
        return updated
    gh = GitHubClient(settings)
    try:
        if action.action_type == "github_issue":
            created = gh.create_issue(action.target_repository, action.title, action.body, labels=["skopeo"])
            result = {"url": created.get("html_url"), "number": created.get("number")}
        elif action.action_type == "pull_request":
            inv = store.get_investigation(investigation_id)
            files = (action.result or {}).get("files") or {}
            branch = f"skopeo/{action.action_id[:8]}"
            created = gh.create_pull_request(
                action.target_repository, inv.branch if inv else "main", branch, action.title, action.body, files
            )
            result = {"url": created.get("html_url"), "number": created.get("number"), "draft": True}
        else:
            raise ActionError(f"unsupported action type {action.action_type}")
        status = "executed"
    except (GitHubError, ActionError) as exc:
        result, status = {"error": str(exc)}, "failed"
    updated = store.update_action(
        action.action_id,
        status=status,
        approved_by=who,
        decision_note=req.note,
        decided_at=utcnow(),
        result={**(action.result or {}), **result},
    )
    events.emit(
        investigation_id,
        "human",
        EventType.ACTION_DECIDED,
        f"{who} approved '{action.title}' — {status}",
        receiver="orchestrator",
        payload={"action_id": action.action_id, "status": status, **result},
    )
    return updated
