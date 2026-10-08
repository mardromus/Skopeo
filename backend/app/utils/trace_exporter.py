"""Execution Trace Exporter for Exam Studio CA3 Artifact Submission.

Extracts execution events and agent handoffs from the Evidence Store and converts them
into Markdown or JSON format required by Exam Studio evaluations.
"""

from __future__ import annotations

import json
from typing import Any

from app.services.evidence_store import EvidenceStore


class TraceExporter:
    def __init__(self, store: EvidenceStore) -> None:
        self.store = store

    def export_markdown(self, investigation_id: str) -> str:
        inv = self.store.get_investigation(investigation_id)
        if not inv:
            raise ValueError(f"Investigation {investigation_id} not found")

        events = self.store.list_events(investigation_id, limit=5000)
        agent_runs = self.store.list_agent_runs(investigation_id)
        findings = self.store.list_findings(investigation_id)
        verifications = self.store.list_verifications(investigation_id)
        risks = self.store.list_risks(investigation_id)

        lines: list[str] = []
        lines.append(f"# Skopeo Multi-Agent Execution Trace")
        lines.append(f"**Investigation ID**: `{investigation_id}`")
        lines.append(f"**Target Repository**: `{inv.repository_url}` (`{inv.commit_sha or inv.branch}`)")
        lines.append(f"**Status**: `{inv.status}`")
        lines.append(f"**Overall Risk Score**: `{inv.overall_risk_score or 0}` / 100")
        lines.append("")
        lines.append("## 1. Active Agents Summary")
        lines.append("| Agent Name | Mode | Status | Findings | Duration (ms) |")
        lines.append("| --- | --- | --- | --- | --- |")

        for run in agent_runs:
            count = sum(1 for f in findings if f.agent == run.agent)
            lines.append(f"| {run.agent} | {run.mode} | {run.status} | {count} | {run.duration_ms or 0} |")

        lines.append("")
        lines.append("## 2. Real-Time Inter-Agent Execution Chronology")
        lines.append("")

        for ev in events:
            sender = ev.sender
            receiver = ev.receiver or "orchestrator"
            event_type = ev.event_type
            summary = ev.message
            lines.append(f"- **[{ev.seq:03d}] `{sender}` $\\rightarrow$ `{receiver}`** (`{event_type}`): {summary}")

        lines.append("")
        lines.append("## 3. Red Team Verification Rulings")
        for v in verifications:
            lines.append(f"- **Finding `{v.finding_id[:8]}`**: Ruling = `{v.ruling}`, Verdict = {v.reasoning}")

        lines.append("")
        lines.append("## 4. Calculated Compound Risks")
        for r in risks:
            lines.append(f"- **{r.title}** (Score: `{r.risk_score}`): {r.summary}")

        return "\n".join(lines)

    def export_json(self, investigation_id: str) -> dict[str, Any]:
        inv = self.store.get_investigation(investigation_id)
        if not inv:
            raise ValueError(f"Investigation {investigation_id} not found")

        events = self.store.list_events(investigation_id, limit=5000)
        agent_runs = self.store.list_agent_runs(investigation_id)

        return {
            "investigation_id": investigation_id,
            "repository_url": inv.repository_url,
            "status": inv.status,
            "risk_score": inv.overall_risk_score,
            "agent_runs": [
                {
                    "agent": r.agent,
                    "mode": r.mode,
                    "status": r.status,
                    "duration_ms": r.duration_ms,
                }
                for r in agent_runs
            ],
            "events": [
                {
                    "seq": ev.seq,
                    "sender": ev.sender,
                    "receiver": ev.receiver,
                    "event_type": ev.event_type,
                    "summary": ev.message,
                    "payload": ev.payload,
                }
                for ev in events
            ],
        }
