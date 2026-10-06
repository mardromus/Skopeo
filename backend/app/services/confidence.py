"""Transparent confidence model.

Confidence is *computed from evidence*, never requested from an LLM. Each factor is recorded so
the UI / report can show exactly why a finding has the confidence it has.

    evidence_strength  = 1 - prod(1 - w(source_type) * evidence.confidence)     (noisy-OR, capped)
    + reproduction     (+0.10)  claim reproduced by a test run or benchmark
    + reachability     (+0.05 confirmed / -0.25 refuted)
    + corroboration    (+0.05 per independent agent, max +0.15)
    + verification     (+0.10 verified / -0.10 needs more evidence / rejected caps at 0.10)
    - contradiction    (-0.15 per contradicting finding, max -0.30)
    - static suspect   (-0.10 performance claim without measurement)
    hypothesis findings are capped at 0.40. Result clamped to [0.01, 0.99].
"""

from __future__ import annotations

from dataclasses import dataclass, field

SOURCE_WEIGHTS: dict[str, float] = {
    "benchmark": 0.92,
    "test": 0.88,
    "dependency": 0.8,
    "static_analysis": 0.65,
    "git": 0.7,
    "github": 0.7,
    "llm_analysis": 0.35,
}


@dataclass
class ConfidenceInputs:
    evidence: list[tuple[str, float]] = field(default_factory=list)  # (source_type, evidence confidence)
    reproduced: bool = False
    reachable: bool | None = None
    corroborating_agents: int = 0
    verification: str | None = None
    contradictions: int = 0
    is_hypothesis: bool = False
    static_suspect: bool = False


@dataclass
class ConfidenceResult:
    score: float
    factors: list[dict]


def compute_confidence(inp: ConfidenceInputs) -> ConfidenceResult:
    factors: list[dict] = []
    if inp.evidence:
        miss = 1.0
        for source_type, conf in inp.evidence:
            miss *= 1.0 - SOURCE_WEIGHTS.get(source_type, 0.4) * max(0.0, min(1.0, conf))
        strength = min(0.95, 1.0 - miss)
        kinds = sorted({s for s, _ in inp.evidence})
        factors.append(
            {
                "factor": "evidence_strength",
                "delta": round(strength, 3),
                "detail": f"{len(inp.evidence)} evidence item(s): {', '.join(kinds)}",
            }
        )
    else:
        strength = 0.15
        factors.append({"factor": "evidence_strength", "delta": 0.15, "detail": "no supporting evidence"})
    score = strength

    def adjust(name: str, delta: float, detail: str) -> None:
        nonlocal score
        score += delta
        factors.append({"factor": name, "delta": round(delta, 3), "detail": detail})

    if inp.reproduced:
        adjust("reproduction", 0.10, "claim reproduced by executing tests/benchmark")
    if inp.reachable is True:
        adjust("reachability", 0.05, "affected code is reachable from non-test code")
    elif inp.reachable is False:
        adjust("reachability", -0.25, "affected code is not reachable from production code")
    if inp.corroborating_agents:
        bonus = min(0.15, 0.05 * inp.corroborating_agents)
        adjust("corroboration", bonus, f"{inp.corroborating_agents} other agent(s) produced related evidence")
    if inp.static_suspect:
        adjust("static_suspect", -0.10, "performance claim not yet measured")
    if inp.contradictions:
        adjust("contradiction", -min(0.30, 0.15 * inp.contradictions), f"{inp.contradictions} contradicting finding(s)")
    if inp.verification == "verified":
        adjust("verification", 0.10, "survived red-team verification")
    elif inp.verification == "needs_more_evidence":
        adjust("verification", -0.10, "red-team requested more evidence")
    if inp.is_hypothesis:
        if score > 0.40:
            factors.append({"factor": "hypothesis_cap", "delta": round(0.40 - score, 3), "detail": "hypotheses are capped at 0.40"})
        score = min(score, 0.40)
    if inp.verification == "rejected":
        if score > 0.10:
            factors.append({"factor": "rejected_cap", "delta": round(0.10 - score, 3), "detail": "rejected by red-team; capped at 0.10"})
        score = min(score, 0.10)
    score = round(max(0.01, min(0.99, score)), 3)
    return ConfidenceResult(score=score, factors=factors)
