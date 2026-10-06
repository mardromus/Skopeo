"""Risk scoring.

    raw   = Severity x Confidence x Impact x Exploitability x CorrelationMultiplier
    score = 100 * (1 - exp(-2.2 * raw))          (monotonic, saturating normalisation to 0-100)

Priorities: P0 >= 80, P1 >= 60, P2 >= 35, P3 >= 12, P4 otherwise.
"""

from __future__ import annotations

import math
from typing import Any

SEVERITY_WEIGHT = {"critical": 1.0, "high": 0.75, "medium": 0.5, "low": 0.25, "info": 0.05}
PRIORITY_THRESHOLDS = [("P0", 80.0), ("P1", 60.0), ("P2", 35.0), ("P3", 12.0)]
SECURITY_CRITICAL_COMPONENTS = {"authentication", "authorization", "cryptography", "secrets", "payments", "session"}
_K = 2.2


def normalise(raw: float) -> float:
    return round(100.0 * (1.0 - math.exp(-_K * max(0.0, raw))), 1)


def priority_for(score: float) -> str:
    for name, threshold in PRIORITY_THRESHOLDS:
        if score >= threshold:
            return name
    return "P4"


def risk_level(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 35:
        return "medium"
    if score >= 12:
        return "low"
    return "minimal"


def impact_for(finding: dict[str, Any]) -> tuple[float, str]:
    components = set(finding.get("affected_components") or [])
    files = finding.get("affected_files") or []
    attrs = finding.get("attributes") or {}
    if "impact" in attrs:
        return float(attrs["impact"]), attrs.get("impact_reason", "impact supplied by specialist evidence")
    if components & SECURITY_CRITICAL_COMPONENTS:
        return 1.0, f"affects security-critical component ({', '.join(sorted(components & SECURITY_CRITICAL_COMPONENTS))})"
    if finding.get("category") == "license":
        return 0.6, "legal / distribution exposure"
    if files and all(attrs.get("test_only") or "/tests/" in f"/{f}" or f.startswith("tests/") for f in files):
        return 0.3, "affects test code only"
    if finding.get("category") in ("dependency", "security"):
        return 0.8, "affects production dependency / code"
    return 0.7, "affects production code"


def exploitability_for(finding: dict[str, Any]) -> tuple[float, str]:
    attrs = finding.get("attributes") or {}
    if "likelihood" in attrs:
        return float(attrs["likelihood"]), attrs.get("likelihood_reason", "likelihood supplied by specialist evidence")
    category = finding.get("category")
    reach = attrs.get("reachability")
    if category in ("security", "dependency"):
        if reach == "entrypoint":
            return 0.8, "reachable from request handlers / entrypoints"
        if reach == "reachable":
            return 0.65, "reachable from production code"
        if reach == "unreachable":
            return 0.25, "not reachable from production code"
        return 0.5, "reachability unknown"
    if category == "performance":
        return (0.6, "measured by benchmark") if attrs.get("measurement") == "measured" else (0.35, "static suspect only")
    if category == "testing":
        return 0.5, "likelihood that an untested/failing path ships a regression"
    if category == "license":
        return 0.6, "obligations trigger on distribution"
    return 0.5, "default likelihood"


def compute_risk(severity: str, confidence: float, impact: float, exploitability: float, multiplier: float = 1.0) -> dict[str, Any]:
    weight = SEVERITY_WEIGHT.get(severity, 0.25)
    raw = weight * confidence * impact * exploitability * multiplier
    score = normalise(raw)
    return {
        "severity_weight": weight,
        "confidence": round(confidence, 3),
        "impact": round(impact, 3),
        "exploitability": round(exploitability, 3),
        "correlation_multiplier": round(multiplier, 3),
        "raw": round(raw, 4),
        "score": score,
        "priority": priority_for(score),
    }


def overall_risk(scores: list[float]) -> dict[str, Any]:
    """Aggregate: the worst risk dominates; each further risk contributes with halving weight."""
    if not scores:
        return {"score": 0.0, "level": "minimal"}
    remaining = 1.0
    for i, s in enumerate(sorted(scores, reverse=True)[:10]):
        remaining *= 1.0 - (s / 100.0) * (0.5**i)
    score = round(100.0 * (1.0 - remaining), 1)
    return {"score": score, "level": risk_level(score)}
