"""SARIF 2.1.0 export of an investigation.

SARIF (Static Analysis Results Interchange Format) is the format GitHub Code Scanning, VS Code's
SARIF viewer, Azure DevOps and most CI dashboards understand. Exporting a case as SARIF lets the
verified output of the agents show up next to the results of ordinary scanners.

Mapping
-------
* one SARIF ``run`` per investigation, with Skopeo as the ``tool.driver``;
* one ``reportingDescriptor`` (rule) per distinct ``agent / rule_id`` pair;
* one ``result`` per finding that the red team verified;
* findings the red team **rejected** are exported too, but carry a SARIF ``suppression`` whose
  justification is the red team's own reasoning, so downstream tools hide them by default while
  keeping the audit trail;
* findings that still lack evidence (``needs_more_evidence``) are left out, exactly as they are
  excluded from the risk score.

Locations come from the finding's evidence (file and line range) and fall back to the finding's
``affected_files``. A finding that points at no file at all is anchored on the repository root so
that it is still valid SARIF (every result needs at least one location for GitHub to accept it).

Nothing here is synthesised: every value is read from records that are already in the Evidence
Store, and the same redaction that protects reports and events has already been applied to them.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app import __version__
from app.services.evidence_store import EvidenceStore

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"
TOOL_NAME = "Skopeo"
TOOL_INFORMATION_URI = "https://github.com/mardromus/Skopeo"

#: Skopeo severity -> SARIF ``level``. SARIF has only error / warning / note / none.
LEVEL_BY_SEVERITY: dict[str, str] = {
    "critical": "error",
    "high": "error",
    "medium": "warning",
    "low": "note",
    "info": "note",
}

#: Skopeo severity -> GitHub's ``security-severity`` (CVSS-like 0-10 string, used to bucket alerts).
SECURITY_SEVERITY: dict[str, str] = {
    "critical": "9.5",
    "high": "8.0",
    "medium": "5.5",
    "low": "3.0",
    "info": "0.5",
}

#: Statuses that are exported, and how.
EXPORTED_STATUSES = ("verified", "rejected")

#: Placeholder anchor for findings that name no file (repository-wide findings).
REPOSITORY_ROOT_URI = "."


def _rule_key(agent: str, rule_id: str) -> str:
    """Stable, readable SARIF rule id, e.g. ``dependency_agent/vulnerable-dependency``."""
    return f"{agent}/{rule_id}"


def _fingerprint(finding: dict[str, Any]) -> str:
    """A fingerprint that survives re-runs: it ignores ids and timestamps.

    GitHub uses ``partialFingerprints`` to match results between uploads, so the same problem
    in two different investigations is tracked as one alert.
    """
    parts = [
        finding["agent"],
        finding["rule_id"],
        finding.get("subject") or "",
        "|".join(sorted(finding.get("affected_files") or [])),
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]


def _help_markdown(finding: dict[str, Any]) -> str:
    lines = [f"**{finding['title']}**", "", finding.get("description") or ""]
    if finding.get("recommended_action"):
        lines += ["", "**Recommended action**", "", finding["recommended_action"]]
    return "\n".join(lines).strip()


def _build_rules(findings: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """One descriptor per ``agent/rule_id``; returns the list and an index by key."""
    rules: list[dict[str, Any]] = []
    index: dict[str, int] = {}
    for f in findings:
        key = _rule_key(f["agent"], f["rule_id"])
        if key in index:
            continue
        index[key] = len(rules)
        rules.append(
            {
                "id": key,
                "name": f["rule_id"],
                "shortDescription": {"text": f["title"][:200]},
                "fullDescription": {"text": (f.get("description") or f["title"])[:1000]},
                "help": {
                    "text": f.get("recommended_action") or f["title"],
                    "markdown": _help_markdown(f),
                },
                "defaultConfiguration": {"level": LEVEL_BY_SEVERITY.get(f["severity"], "warning")},
                "properties": {
                    "category": f["category"],
                    "agent": f["agent"],
                    "tags": ["skopeo", f["category"], f["agent"]],
                    "security-severity": SECURITY_SEVERITY.get(f["severity"], "5.5"),
                },
            }
        )
    return rules, index


def _region(line_start: int | None, line_end: int | None, excerpt: str | None) -> dict[str, Any] | None:
    """SARIF regions are 1-based; Skopeo stores 0 for 'unknown'."""
    if not line_start or line_start < 1:
        return None
    region: dict[str, Any] = {"startLine": int(line_start)}
    if line_end and line_end >= line_start:
        region["endLine"] = int(line_end)
    if excerpt:
        region["snippet"] = {"text": excerpt[:500]}
    return region


def _physical_location(uri: str, region: dict[str, Any] | None) -> dict[str, Any]:
    physical: dict[str, Any] = {"artifactLocation": {"uri": uri.replace("\\", "/"), "uriBaseId": "%SRCROOT%"}}
    if region:
        physical["region"] = region
    return {"physicalLocation": physical}


def _locations(finding: dict[str, Any], evidence: list[Any]) -> list[dict[str, Any]]:
    """Evidence locations first (they carry line numbers), then the remaining affected files."""
    seen: set[tuple[str, int | None, int | None]] = set()
    locations: list[dict[str, Any]] = []
    for ev in evidence:
        if not ev.file:
            continue
        key = (ev.file, ev.line_start, ev.line_end)
        if key in seen:
            continue
        seen.add(key)
        locations.append(_physical_location(ev.file, _region(ev.line_start, ev.line_end, ev.excerpt)))
    covered = {k[0] for k in seen}
    for path in finding.get("affected_files") or []:
        if path in covered:
            continue
        covered.add(path)
        locations.append(_physical_location(path, None))
    if not locations:
        locations.append(_physical_location(REPOSITORY_ROOT_URI, None))
    return locations


def _message(finding: dict[str, Any], verification: dict[str, Any] | None) -> str:
    text = finding["title"]
    summary = (verification or {}).get("reasoning_summary") or finding.get("reasoning_summary")
    if summary:
        text = f"{text}. {summary}"
    return text[:1500]


def _suppression(verification: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Rejected findings are exported as suppressed results, justified by the red team."""
    reason = (verification or {}).get("reasoning_summary") or "Rejected by the Skopeo red team."
    return [{"kind": "external", "status": "accepted", "justification": reason[:1000]}]


def _result(
    finding: dict[str, Any],
    evidence: list[Any],
    verification: dict[str, Any] | None,
    rule_index: dict[str, int],
) -> dict[str, Any]:
    key = _rule_key(finding["agent"], finding["rule_id"])
    result: dict[str, Any] = {
        "ruleId": key,
        "ruleIndex": rule_index[key],
        "level": LEVEL_BY_SEVERITY.get(finding["severity"], "warning"),
        "message": {"text": _message(finding, verification)},
        "locations": _locations(finding, evidence),
        "partialFingerprints": {"skopeoFinding/v1": _fingerprint(finding)},
        "properties": {
            "findingId": finding["finding_id"],
            "agent": finding["agent"],
            "category": finding["category"],
            "severity": finding["severity"],
            "status": finding["status"],
            "confidence": round(float(finding["confidence"]), 3),
            "evidenceCount": len(evidence),
            "subject": finding.get("subject"),
            "components": finding.get("affected_components") or [],
            "security-severity": SECURITY_SEVERITY.get(finding["severity"], "5.5"),
        },
    }
    if finding["status"] == "rejected":
        result["suppressions"] = _suppression(verification)
    return result


def _invocation(inv: Any) -> dict[str, Any]:
    invocation: dict[str, Any] = {
        "executionSuccessful": inv.status in ("completed", "completed_with_limitations"),
        "properties": {"status": inv.status, "mode": (inv.execution_summary or {}).get("mode")},
    }
    if inv.started_at:
        invocation["startTimeUtc"] = inv.started_at.isoformat().replace("+00:00", "Z")
    if inv.completed_at:
        invocation["endTimeUtc"] = inv.completed_at.isoformat().replace("+00:00", "Z")
    return invocation


def build_sarif(store: EvidenceStore, investigation_id: str) -> dict[str, Any]:
    """Return the investigation as a SARIF 2.1.0 log (a plain dict, ready for ``json.dumps``)."""
    inv = store.get_investigation(investigation_id)
    if inv is None:
        raise KeyError(investigation_id)

    findings = [f.model_dump(mode="json") for f in store.list_findings(investigation_id, status=list(EXPORTED_STATUSES))]
    latest_verification: dict[str, dict[str, Any]] = {}
    for v in store.list_verifications(investigation_id):
        if v.finding_id:
            latest_verification[v.finding_id] = v.model_dump(mode="json")

    evidence_by_finding: dict[str, list[Any]] = {}
    for ev in store.list_evidence(investigation_id):
        if ev.finding_id:
            evidence_by_finding.setdefault(ev.finding_id, []).append(ev)

    # Verified first, then by severity, so viewers that keep the file order show what matters.
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    findings.sort(key=lambda f: (f["status"] != "verified", severity_rank.get(f["severity"], 5), f["title"]))

    rules, rule_index = _build_rules(findings)
    results = [
        _result(f, evidence_by_finding.get(f["finding_id"], []), latest_verification.get(f["finding_id"]), rule_index) for f in findings
    ]

    risks = store.list_risks(investigation_id)
    run: dict[str, Any] = {
        "tool": {
            "driver": {
                "name": TOOL_NAME,
                "version": __version__,
                "informationUri": TOOL_INFORMATION_URI,
                "semanticVersion": __version__,
                "rules": rules,
            }
        },
        "automationDetails": {"id": f"skopeo/{inv.repository_name}/{inv.id}"},
        "invocations": [_invocation(inv)],
        "originalUriBaseIds": {"%SRCROOT%": {"uri": inv.repository_url.rstrip("/") + "/"}},
        "versionControlProvenance": [
            {
                "repositoryUri": inv.repository_url,
                "revisionId": inv.commit_sha,
                "branch": inv.branch,
            }
        ],
        "results": results,
        "properties": {
            "investigationId": inv.id,
            "overallRisk": {"score": inv.overall_risk_score, "level": inv.overall_risk_level},
            "verified": sum(1 for r in results if "suppressions" not in r),
            "suppressedRejected": sum(1 for r in results if "suppressions" in r),
            "topRisks": [
                {"priority": r.priority, "score": r.score, "title": r.title, "kind": r.kind}
                for r in sorted(risks, key=lambda r: r.score, reverse=True)[:10]
            ],
        },
    }
    if not inv.commit_sha:
        run["versionControlProvenance"][0].pop("revisionId")

    return {"$schema": SARIF_SCHEMA, "version": SARIF_VERSION, "runs": [run]}
