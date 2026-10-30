"""Case diff: what changed between two investigations of the same repository.

A single investigation answers "what is wrong now". Teams also need "what did we fix, and what
did we break since last time". This module compares the *verified* findings and risks of two
cases and reports

* ``new``        findings present now that the baseline did not have;
* ``resolved``   findings the baseline had that are gone now;
* ``persisting`` findings present in both (with any change of severity or confidence);
* the movement of the overall risk score and of every priority bucket (P0 ... P4);
* verified risks (including compound risks) that appeared or disappeared.

Findings are matched by a *fingerprint* built from the agent, rule, subject and affected files.
Ids and timestamps are never used, because every investigation creates fresh ones. Only verified
findings take part: proposed, rejected or evidence-starved findings are noise that the red team
already filtered out, and diffing them would report churn instead of change.

The module is pure with respect to the store: it reads, it never writes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.services.evidence_store import EvidenceStore

SEVERITY_RANK: dict[str, int] = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
PRIORITIES: tuple[str, ...] = ("P0", "P1", "P2", "P3", "P4")

#: Statuses of a case that can serve as a baseline.
BASELINE_STATUSES = ("completed", "completed_with_limitations")

#: Confidence moves smaller than this are not reported as a change.
CONFIDENCE_EPSILON = 0.05

#: Verdict thresholds for the overall score movement.
SCORE_EPSILON = 1.0


class DiffError(ValueError):
    """Raised when two cases cannot be compared (missing, identical, unfinished)."""


@dataclass
class _Bucket:
    """Findings that share a fingerprint inside one case (normally exactly one)."""

    key: str
    findings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def lead(self) -> dict[str, Any]:
        """The most severe, most confident finding stands for the bucket."""
        return max(self.findings, key=lambda f: (SEVERITY_RANK.get(f["severity"], 0), f["confidence"]))


# ----------------------------------------------------------------------------- fingerprints
def finding_key(finding: dict[str, Any]) -> str:
    """Identity of a finding across investigations: agent, rule, subject and files, no ids."""
    files = "|".join(sorted(finding.get("affected_files") or []))
    return "\x1f".join([finding["agent"], finding["rule_id"], (finding.get("subject") or "").lower(), files])


def risk_key(risk: dict[str, Any]) -> str:
    """Identity of a risk across investigations: its kind, category and title."""
    return "\x1f".join([risk.get("kind") or "", risk.get("category") or "", (risk.get("title") or "").strip().lower()])


def _group(findings: list[dict[str, Any]]) -> dict[str, _Bucket]:
    buckets: dict[str, _Bucket] = {}
    for f in findings:
        key = finding_key(f)
        buckets.setdefault(key, _Bucket(key)).findings.append(f)
    return buckets


# ----------------------------------------------------------------------------- compact views
def finding_view(finding: dict[str, Any], *, duplicates: int = 1) -> dict[str, Any]:
    """The few fields a reader needs to recognise a finding in a diff."""
    return {
        "finding_id": finding["finding_id"],
        "agent": finding["agent"],
        "category": finding["category"],
        "rule_id": finding["rule_id"],
        "title": finding["title"],
        "severity": finding["severity"],
        "confidence": round(float(finding["confidence"]), 3),
        "subject": finding.get("subject"),
        "affected_files": finding.get("affected_files") or [],
        "affected_components": finding.get("affected_components") or [],
        "occurrences": duplicates,
    }


def risk_view(risk: dict[str, Any]) -> dict[str, Any]:
    return {
        "risk_id": risk["risk_id"],
        "kind": risk["kind"],
        "category": risk["category"],
        "title": risk["title"],
        "priority": risk["priority"],
        "score": risk["score"],
        "severity": risk["severity"],
    }


def case_view(inv: Any) -> dict[str, Any]:
    """Header describing one side of the comparison."""
    return {
        "investigation_id": inv.id,
        "repository": inv.repository_name,
        "repository_url": inv.repository_url,
        "branch": inv.branch,
        "commit_sha": inv.commit_sha,
        "status": inv.status,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "completed_at": inv.completed_at.isoformat() if inv.completed_at else None,
        "overall_risk": {"score": inv.overall_risk_score, "level": inv.overall_risk_level},
    }


# ----------------------------------------------------------------------------- comparison
def _changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """What differs for a finding that exists on both sides (empty dict = unchanged)."""
    changes: dict[str, Any] = {}
    if before["severity"] != after["severity"]:
        direction = "escalated" if SEVERITY_RANK.get(after["severity"], 0) > SEVERITY_RANK.get(before["severity"], 0) else "relaxed"
        changes["severity"] = {"from": before["severity"], "to": after["severity"], "direction": direction}
    delta = round(float(after["confidence"]) - float(before["confidence"]), 3)
    if abs(delta) >= CONFIDENCE_EPSILON:
        changes["confidence"] = {"from": round(float(before["confidence"]), 3), "to": round(float(after["confidence"]), 3), "delta": delta}
    if before["title"] != after["title"]:
        changes["title"] = {"from": before["title"], "to": after["title"]}
    return changes


def compare_findings(baseline: list[dict[str, Any]], current: list[dict[str, Any]]) -> dict[str, Any]:
    """Split two lists of findings into new / resolved / persisting."""
    old, new = _group(baseline), _group(current)
    added = sorted(new.keys() - old.keys())
    removed = sorted(old.keys() - new.keys())
    kept = sorted(new.keys() & old.keys())

    persisting: list[dict[str, Any]] = []
    escalated = relaxed = 0
    for key in kept:
        before, after = old[key].lead, new[key].lead
        changes = _changes(before, after)
        if "severity" in changes:
            if changes["severity"]["direction"] == "escalated":
                escalated += 1
            else:
                relaxed += 1
        persisting.append(
            {
                "finding": finding_view(after, duplicates=len(new[key].findings)),
                "previous_finding_id": before["finding_id"],
                "changes": changes,
                "changed": bool(changes),
            }
        )

    by_severity = sorted(
        (finding_view(new[k].lead, duplicates=len(new[k].findings)) for k in added),
        key=lambda f: (-SEVERITY_RANK.get(f["severity"], 0), f["title"]),
    )
    resolved = sorted(
        (finding_view(old[k].lead, duplicates=len(old[k].findings)) for k in removed),
        key=lambda f: (-SEVERITY_RANK.get(f["severity"], 0), f["title"]),
    )
    persisting.sort(key=lambda p: (not p["changed"], -SEVERITY_RANK.get(p["finding"]["severity"], 0), p["finding"]["title"]))

    return {
        "new": by_severity,
        "resolved": resolved,
        "persisting": persisting,
        "counts": {
            "baseline": len(old),
            "current": len(new),
            "new": len(added),
            "resolved": len(removed),
            "persisting": len(kept),
            "escalated": escalated,
            "relaxed": relaxed,
        },
    }


def _severity_histogram(findings: list[dict[str, Any]]) -> dict[str, int]:
    hist = {name: 0 for name in SEVERITY_RANK}
    for bucket in _group(findings).values():
        hist[bucket.lead["severity"]] = hist.get(bucket.lead["severity"], 0) + 1
    return hist


def _priority_histogram(risks: list[dict[str, Any]]) -> dict[str, int]:
    hist = dict.fromkeys(PRIORITIES, 0)
    for r in risks:
        hist[r["priority"]] = hist.get(r["priority"], 0) + 1
    return hist


def compare_risks(baseline: list[dict[str, Any]], current: list[dict[str, Any]]) -> dict[str, Any]:
    """Which verified risks appeared, disappeared or changed priority."""
    old = {risk_key(r): r for r in baseline}
    new = {risk_key(r): r for r in current}
    appeared = [risk_view(new[k]) for k in sorted(new.keys() - old.keys())]
    disappeared = [risk_view(old[k]) for k in sorted(old.keys() - new.keys())]

    moved: list[dict[str, Any]] = []
    for key in sorted(new.keys() & old.keys()):
        before, after = old[key], new[key]
        if before["priority"] != after["priority"] or abs(before["score"] - after["score"]) >= SCORE_EPSILON:
            moved.append(
                {
                    "title": after["title"],
                    "kind": after["kind"],
                    "priority": {"from": before["priority"], "to": after["priority"]},
                    "score": {"from": before["score"], "to": after["score"], "delta": round(after["score"] - before["score"], 1)},
                }
            )
    appeared.sort(key=lambda r: -r["score"])
    disappeared.sort(key=lambda r: -r["score"])
    moved.sort(key=lambda m: -abs(m["score"]["delta"]))

    before_hist, after_hist = _priority_histogram(baseline), _priority_histogram(current)
    return {
        "appeared": appeared,
        "disappeared": disappeared,
        "changed": moved,
        "priorities": {
            p: {"baseline": before_hist[p], "current": after_hist[p], "delta": after_hist[p] - before_hist[p]} for p in PRIORITIES
        },
    }


def verdict(score_before: float | None, score_after: float | None, new_count: int, resolved_count: int, escalated: int) -> str:
    """One word for the trend: improved, regressed, mixed or unchanged."""
    delta = (score_after or 0.0) - (score_before or 0.0)
    worse = delta >= SCORE_EPSILON or (new_count > 0 and delta > -SCORE_EPSILON) or escalated > 0
    better = delta <= -SCORE_EPSILON or (resolved_count > 0 and delta < SCORE_EPSILON)
    if worse and better:
        return "mixed"
    if worse:
        return "regressed"
    if better:
        return "improved"
    return "unchanged"


def headline(summary: dict[str, Any]) -> str:
    """A sentence for dashboards and notifications."""
    c = summary["findings"]["counts"]
    score = summary["overall_risk"]
    parts = [f"{c['new']} new", f"{c['resolved']} resolved", f"{c['persisting']} unchanged-or-persisting"]
    if c["escalated"]:
        parts.append(f"{c['escalated']} escalated")
    delta = score["delta"]
    movement = "no change in risk score" if delta is None or abs(delta) < SCORE_EPSILON else f"risk score {delta:+.1f}"
    return f"{summary['verdict'].capitalize()}: " + ", ".join(parts) + f"; {movement}."


# ----------------------------------------------------------------------------- store access
def _verified_findings(store: EvidenceStore, investigation_id: str) -> list[dict[str, Any]]:
    return [f.model_dump(mode="json") for f in store.list_findings(investigation_id, status="verified")]


def _risks(store: EvidenceStore, investigation_id: str) -> list[dict[str, Any]]:
    return [r.model_dump(mode="json") for r in store.list_risks(investigation_id)]


def _same_target(a: Any, b: Any) -> bool:
    return a.repository_url.rstrip("/").lower() == b.repository_url.rstrip("/").lower() and a.branch == b.branch


def find_baseline(store: EvidenceStore, current: Any, *, can_see: Any = None, search_limit: int = 100) -> Any | None:
    """The most recent finished case of the same repository and branch created before ``current``.

    ``can_see`` is an optional predicate (the API passes its privacy check) so a private case is
    never offered as a baseline to someone who may not read it.
    """
    candidates = [
        inv
        for inv in store.list_investigations(search_limit)  # newest first
        if inv.id != current.id
        and inv.status in BASELINE_STATUSES
        and inv.created_at < current.created_at
        and _same_target(inv, current)
        and (can_see is None or can_see(inv))
    ]
    return candidates[0] if candidates else None


def diff_investigations(store: EvidenceStore, baseline_id: str, current_id: str) -> dict[str, Any]:
    """Compare ``baseline_id`` (older) with ``current_id`` (newer)."""
    if baseline_id == current_id:
        raise DiffError("a case cannot be compared with itself")
    baseline = store.get_investigation(baseline_id)
    current = store.get_investigation(current_id)
    if baseline is None or current is None:
        raise KeyError(baseline_id if baseline is None else current_id)
    for inv in (baseline, current):
        if inv.status not in BASELINE_STATUSES:
            raise DiffError(f"investigation {inv.id[:8]} is {inv.status}; only finished cases can be compared")

    old_findings = _verified_findings(store, baseline_id)
    new_findings = _verified_findings(store, current_id)
    findings = compare_findings(old_findings, new_findings)
    risks = compare_risks(_risks(store, baseline_id), _risks(store, current_id))

    score_before, score_after = baseline.overall_risk_score, current.overall_risk_score
    delta = None if score_before is None or score_after is None else round(score_after - score_before, 1)
    counts = findings["counts"]

    by_agent: dict[str, dict[str, int]] = defaultdict(lambda: {"new": 0, "resolved": 0})
    for f in findings["new"]:
        by_agent[f["agent"]]["new"] += 1
    for f in findings["resolved"]:
        by_agent[f["agent"]]["resolved"] += 1

    summary: dict[str, Any] = {
        "baseline": case_view(baseline),
        "current": case_view(current),
        "same_repository": _same_target(baseline, current),
        "same_commit": bool(baseline.commit_sha) and baseline.commit_sha == current.commit_sha,
        "overall_risk": {
            "baseline": {"score": score_before, "level": baseline.overall_risk_level},
            "current": {"score": score_after, "level": current.overall_risk_level},
            "delta": delta,
        },
        "findings": findings,
        "severity": {
            "baseline": _severity_histogram(old_findings),
            "current": _severity_histogram(new_findings),
        },
        "by_agent": dict(sorted(by_agent.items())),
        "risks": risks,
    }
    summary["verdict"] = verdict(score_before, score_after, counts["new"], counts["resolved"], counts["escalated"])
    summary["headline"] = headline(summary)
    return summary
