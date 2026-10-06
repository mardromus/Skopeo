"""Investigation finalisation: per-agent coverage, overall status and execution summary.

Coverage is derived from the persisted AgentRun records — partial coverage (failures,
degraded strategies, tool limitations, INSUFFICIENT EVIDENCE) is always reported explicitly.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.agents.base import AgentServices
from app.models import utcnow
from app.schemas import SPECIALIST_AGENTS, EventType


def compute_coverage(services: AgentServices) -> dict[str, Any]:
    store, iid = services.store, services.investigation_id
    inv = store.get_investigation(iid)
    runs = store.list_agent_runs(iid)
    plan = (inv.plan if inv else {}) or {}
    skipped = {s["agent"]: s["reason"] for s in plan.get("skipped", [])}
    coverage: dict[str, Any] = {"agents": {}, "summary": {}}
    for agent in SPECIALIST_AGENTS:
        agent_runs = [r for r in runs if r.agent == agent]
        if not agent_runs:
            coverage["agents"][agent] = {
                "status": "skipped",
                "reason": skipped.get(agent, "not selected by the orchestrator"),
                "runs": 0,
                "limitations": [],
            }
            continue
        completed = [r for r in agent_runs if r.status == "completed"]
        failed = [r for r in agent_runs if r.status in ("failed", "timeout")]
        limitations: list[str] = []
        for r in agent_runs:
            for lim in (r.coverage or {}).get("limitations", []):
                if lim not in limitations:
                    limitations.append(lim)
        for r in failed:
            limitations.insert(0, f"attempt {r.attempt} ({r.mode}/{r.strategy}) {r.status.upper()}: {r.error_type}: {r.error_message}")
        if not completed:
            status = "unavailable"
        elif failed or limitations or any(r.strategy == "static_only" for r in completed):
            status = "partial"
        else:
            status = "complete"
        coverage["agents"][agent] = {
            "status": status,
            "runs": len(agent_runs),
            "failures": len(failed),
            "findings": sum(r.findings_count for r in agent_runs),
            "analyzed": [a for r in completed for a in (r.coverage or {}).get("analyzed", [])][:12],
            "limitations": limitations[:12],
        }
    counts = Counter(v["status"] for v in coverage["agents"].values())
    coverage["summary"] = dict(counts)
    coordination = {}
    for agent in ("correlation_agent", "verification_agent", "risk_agent", "recommendation_agent"):
        agent_runs = [r for r in runs if r.agent == agent]
        coordination[agent] = {
            "runs": len(agent_runs),
            "status": "not_run" if not agent_runs else ("complete" if all(r.status == "completed" for r in agent_runs) else "partial"),
        }
    coverage["coordination"] = coordination
    return coverage


def finalize_investigation(services: AgentServices, state: dict[str, Any]) -> None:
    store, iid, events = services.store, services.investigation_id, services.events
    inv = store.get_investigation(iid)
    assert inv is not None
    coverage = compute_coverage(services)
    runs = store.list_agent_runs(iid)
    findings = store.list_findings(iid)
    correlations = store.list_correlations(iid)
    risks = store.list_risks(iid)
    requests = store.list_requests(iid)
    status_counts = Counter(f.status.value for f in findings)
    cancelled = store.is_cancel_requested(iid) or services.cancel_event.is_set()
    fatal = state.get("fatal_error")
    limited = any(v["status"] in ("partial", "unavailable") for v in coverage["agents"].values()) or any(
        r.status in ("failed", "timeout") for r in runs
    )
    if fatal:
        status = "failed"
    elif cancelled:
        status = "cancelled"
    elif limited or any(v["status"] != "complete" for v in coverage["coordination"].values() if v["status"] != "not_run"):
        status = "completed_with_limitations"
    else:
        status = "completed"
    started = inv.started_at
    now = utcnow()
    duration = (now - (started if started.tzinfo else started.replace(tzinfo=now.tzinfo))).total_seconds() if started else None
    summary = {
        "options": (inv.execution_summary or {}).get("options", {}),
        "rounds": state.get("round", 0),
        "replans": state.get("replans", 0),
        "agent_runs": len(runs),
        "agent_failures": sum(1 for r in runs if r.status in ("failed", "timeout")),
        "retries": sum(1 for r in runs if r.trigger == "retry"),
        "follow_ups": sum(1 for r in runs if r.trigger in ("follow_up", "verification_request")),
        "correlation_rounds": state.get("correlation_rounds", 0),
        "verification_rounds": state.get("verification_rounds", 0),
        "findings": len(findings),
        "verified": status_counts.get("verified", 0),
        "rejected": status_counts.get("rejected", 0),
        "insufficient_evidence": status_counts.get("needs_more_evidence", 0),
        "unchallenged": sum(1 for f in findings if f.status.value in ("proposed", "correlated", "challenged")),
        "correlations": dict(Counter(c.status.value for c in correlations)),
        "risks_by_priority": dict(Counter(r.priority for r in risks)),
        "requests": dict(Counter(r.status for r in requests)),
        "tool_calls": sum(r.tool_calls for r in runs),
        "llm": services.llm.usage.to_dict() | {"provider": services.llm.name},
        "duration_seconds": round(duration, 2) if duration is not None else None,
        "parallelism": _max_parallel(runs),
    }
    store.update_investigation(iid, status=status, completed_at=now, coverage=coverage, execution_summary=summary, error=fatal)
    orch_runs = [r for r in runs if r.agent == "orchestrator" and r.status == "running"]
    for r in orch_runs:
        store.finish_agent_run(r.run_id, "completed", summary=f"investigation {status}", llm_calls=services.llm.usage.calls)
    etype = {"failed": EventType.INVESTIGATION_FAILED, "cancelled": EventType.INVESTIGATION_CANCELLED}.get(
        status, EventType.INVESTIGATION_COMPLETED
    )
    partial = [a for a, v in coverage["agents"].items() if v["status"] in ("partial", "unavailable")]
    events.emit(
        iid,
        "orchestrator",
        etype,
        f"Investigation {status.upper()}: {summary['verified']} verified, {summary['rejected']} rejected, {summary['insufficient_evidence']} insufficient evidence; "
        f"overall risk {inv.overall_risk_score if inv.overall_risk_score is not None else 'n/a'} ({inv.overall_risk_level or 'n/a'})"
        + (f"; partial coverage: {', '.join(partial)}" if partial else ""),
        receiver="human",
        payload={"status": status, "summary": summary, "coverage_summary": coverage["summary"]},
        severity="error" if status == "failed" else "info",
    )


def _max_parallel(runs: list) -> int:
    points = []
    for r in runs:
        if r.started_at and r.completed_at and r.agent != "orchestrator":
            points.append((r.started_at, 1))
            points.append((r.completed_at, -1))
    points.sort(key=lambda p: (p[0], p[1]))
    cur = best = 0
    for _, delta in points:
        cur += delta
        best = max(best, cur)
    return best
