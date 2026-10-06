"""Investigation report (documented output schema) and presentation-ready Markdown export."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.services.evidence_store import EvidenceStore


def _dur(inv) -> float | None:
    if inv.started_at and inv.completed_at:
        return round((inv.completed_at - inv.started_at).total_seconds(), 2)
    return None


def agent_summary(store: EvidenceStore, investigation_id: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    runs = store.list_agent_runs(investigation_id)
    grouped: dict[str, list] = defaultdict(list)
    for r in runs:
        grouped[r.agent].append(r)
    for agent, rs in grouped.items():
        last = rs[-1]
        out[agent] = {
            "runs": len(rs),
            "last_status": last.status,
            "statuses": [f"{r.status}" + (f" ({r.error_type})" if r.error_type else "") for r in rs],
            "findings": sum(r.findings_count for r in rs),
            "failures": sum(1 for r in rs if r.status in ("failed", "timeout")),
            "retries": sum(1 for r in rs if r.trigger == "retry"),
            "duration_ms": sum(r.duration_ms or 0 for r in rs),
            "tool_calls": sum(r.tool_calls for r in rs),
        }
    return out


def build_report(store: EvidenceStore, investigation_id: str, include_events: bool = True) -> dict[str, Any]:
    inv = store.get_investigation(investigation_id)
    if inv is None:
        raise KeyError(investigation_id)
    findings = [f.model_dump(mode="json") for f in store.list_findings(investigation_id)]
    verifications = [v.model_dump(mode="json") for v in store.list_verifications(investigation_id)]
    latest_verification: dict[str, dict] = {}
    for v in verifications:
        if v["finding_id"]:
            latest_verification[v["finding_id"]] = v
    for f in findings:
        f["verification"] = latest_verification.get(f["finding_id"])
    report = {
        "investigation_id": inv.id,
        "repository": inv.repository_name,
        "repository_url": inv.repository_url,
        "branch": inv.branch,
        "commit_sha": inv.commit_sha,
        "source": inv.source,
        "status": inv.status,
        "overall_risk": {"score": inv.overall_risk_score, "level": inv.overall_risk_level},
        "agent_summary": agent_summary(store, investigation_id),
        "plan": inv.plan,
        "findings": findings,
        "correlations": [c.model_dump(mode="json") for c in store.list_correlations(investigation_id)],
        "verified_findings": [f for f in findings if f["status"] == "verified"],
        "rejected_findings": [f for f in findings if f["status"] == "rejected"],
        "insufficient_evidence_findings": [f for f in findings if f["status"] == "needs_more_evidence"],
        "verifications": verifications,
        "risks": [r.model_dump(mode="json") for r in store.list_risks(investigation_id)],
        "recommendations": [r.model_dump(mode="json") for r in store.list_recommendations(investigation_id)],
        "actions": [a.model_dump(mode="json") for a in store.list_actions(investigation_id)],
        "requests": [r.model_dump(mode="json") for r in store.list_requests(investigation_id)],
        "coverage": inv.coverage,
        "execution_summary": inv.execution_summary
        | {"duration_seconds": (inv.execution_summary or {}).get("duration_seconds") or _dur(inv)},
    }
    if include_events:
        report["events"] = [e.model_dump(mode="json") for e in store.list_events(investigation_id)]
    return report


def _md_escape(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def build_markdown(store: EvidenceStore, investigation_id: str) -> str:
    r = build_report(store, investigation_id)
    s = r["execution_summary"] or {}
    lines: list[str] = [
        f"# Skopeo Investigation — {r['repository']}",
        "",
        f"- **Repository:** {r['repository_url']} (branch `{r['branch']}`, commit `{(r['commit_sha'] or '')[:10]}`)",
        f"- **Status:** `{r['status']}`",
        f"- **Overall risk:** {r['overall_risk']['score']} ({r['overall_risk']['level']})",
        f"- **Findings:** {s.get('findings', 0)} — {s.get('verified', 0)} verified, {s.get('rejected', 0)} rejected, {s.get('insufficient_evidence', 0)} insufficient evidence",
        f"- **Agent runs:** {s.get('agent_runs', 0)} ({s.get('agent_failures', 0)} failed, {s.get('retries', 0)} retries, {s.get('follow_ups', 0)} follow-ups, {s.get('replans', 0)} replans, max parallelism {s.get('parallelism', '?')})",
        f"- **Duration:** {s.get('duration_seconds')} s · LLM provider `{(s.get('llm') or {}).get('provider')}` ({(s.get('llm') or {}).get('llm_calls', 0)} model calls, {(s.get('llm') or {}).get('decisions', 0)} decisions)",
        "",
        "## Agent Activity",
        "",
        "| Agent | Runs | Statuses | Findings | Duration (ms) |",
        "| --- | --- | --- | --- | --- |",
    ]
    for agent, a in r["agent_summary"].items():
        lines.append(f"| {agent} | {a['runs']} | {', '.join(a['statuses'])} | {a['findings']} | {a['duration_ms']} |")
    cov = (r["coverage"] or {}).get("agents", {})
    if cov:
        lines += ["", "### Coverage", "", "| Specialist | Coverage | Notes |", "| --- | --- | --- |"]
        for agent, c in cov.items():
            notes = "; ".join(c.get("limitations", [])[:3]) or c.get("reason", "")
            lines.append(f"| {agent} | **{c['status'].upper()}** | {_md_escape(notes)} |")
    lines += ["", "## Verified Risks", "", "| Priority | Score | Risk | Rationale |", "| --- | --- | --- | --- |"]
    for risk in r["risks"]:
        lines.append(f"| {risk['priority']} | {risk['score']} | {_md_escape(risk['title'])} | {_md_escape(risk['rationale'])[:400]} |")
    lines += ["", "## Correlations", ""]
    for c in r["correlations"]:
        lines.append(
            f"- **[{c['relationship_type']} · {c['status']} · x{c['risk_multiplier']}]** {c['title']} — {c['description']}"
            + (f" _Resolution: {c['resolution']}_" if c.get("resolution") else "")
        )
    lines += ["", "## Verification (Red-Team)", ""]
    for f in r["findings"]:
        v = f.get("verification")
        if not v:
            continue
        lines.append(f"### {f['title']}")
        lines.append(
            f"- Proposed by `{f['agent']}` · severity {f['severity']} · final status **{f['status'].upper()}** · confidence {f['confidence']:.2f}"
        )
        lines.append(f"- Challenge: {v['challenge']}")
        for chk in v["checks"]:
            lines.append(f"  - `{chk['check']}` → {chk['outcome']}: {chk['detail']}")
        lines.append(f"- Decision: **{v['decision'].upper()}** — {v['reasoning_summary']}")
        lines.append("")
    lines += ["## Rejected Findings", ""]
    for f in r["rejected_findings"]:
        lines.append(f"- ~~{f['title']}~~ — {(f.get('verification') or {}).get('reasoning_summary', '')}")
    if not r["rejected_findings"]:
        lines.append("- none")
    lines += ["", "## Insufficient Evidence (excluded from risk)", ""]
    for f in r["insufficient_evidence_findings"]:
        lines.append(f"- {f['title']} — {(f.get('verification') or {}).get('reasoning_summary', '')}")
    if not r["insufficient_evidence_findings"]:
        lines.append("- none")
    lines += ["", "## Recommendations", ""]
    for rec in r["recommendations"]:
        lines += [
            f"### [{rec['priority']}] {rec['title']}",
            f"- **Problem:** {rec['problem']}",
            f"- **Affected component:** {rec['affected_component']}",
            f"- **Why it matters:** {rec['why_it_matters']}",
            f"- **Proposed fix:**\n\n{rec['proposed_fix']}\n",
            f"- **Estimated risk:** {rec['estimated_risk']} · **Verification:** {rec['verification_status']} · **Difficulty:** {rec['implementation_difficulty']}",
            f"- **Expected benefit:** {rec['expected_benefit']}",
            "",
        ]
    lines += ["## Proposed Actions (require human approval)", ""]
    for a in r["actions"]:
        lines.append(f"- `{a['status'].upper()}` {a['action_type']}: {a['title']}")
    lines += ["", "## Agent Timeline", "", "| # | Time (UTC) | From → To | Event | Message |", "| --- | --- | --- | --- | --- |"]
    for e in r["events"]:
        lines.append(
            f"| {e['seq']} | {e['timestamp'][11:23]} | {e['sender']} → {e['receiver']} | {e['event_type']} | {_md_escape(e['message'])[:220]} |"
        )
    lines.append("")
    lines.append("_Generated by Skopeo from persisted execution events — nothing in this report is synthesised._")
    return "\n".join(lines)
