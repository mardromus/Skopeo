import pytest

from app.services.confidence import ConfidenceInputs, compute_confidence
from app.services.risk_scoring import compute_risk, exploitability_for, impact_for, normalise, overall_risk, priority_for


def conf(**kw) -> float:
    return compute_confidence(ConfidenceInputs(**kw)).score


def test_deterministic_tool_evidence_beats_llm_evidence():
    assert conf(evidence=[("static_analysis", 0.9)]) > conf(evidence=[("llm_analysis", 0.9)])


def test_more_independent_evidence_increases_confidence():
    one = conf(evidence=[("static_analysis", 0.8)])
    two = conf(evidence=[("static_analysis", 0.8), ("test", 0.9)])
    assert two > one


def test_reproduction_and_reachability_adjust_confidence():
    base = conf(evidence=[("static_analysis", 0.6)])
    assert conf(evidence=[("static_analysis", 0.6)], reproduced=True) > base
    assert conf(evidence=[("static_analysis", 0.6)], reachable=False) < base


def test_contradiction_and_static_suspect_penalties():
    base = conf(evidence=[("static_analysis", 0.75)])
    assert conf(evidence=[("static_analysis", 0.75)], contradictions=1) < base
    assert conf(evidence=[("static_analysis", 0.75)], static_suspect=True) < base


def test_rejection_caps_confidence_and_records_factor():
    result = compute_confidence(ConfidenceInputs(evidence=[("test", 0.95), ("benchmark", 0.95)], verification="rejected"))
    assert result.score <= 0.10
    assert any(f["factor"] == "rejected_cap" for f in result.factors)


def test_hypothesis_is_capped():
    assert conf(evidence=[("test", 0.99)], is_hypothesis=True) <= 0.40


def test_confidence_is_normalised():
    assert 0.0 < conf() <= 1.0
    assert conf(evidence=[("benchmark", 1.0)] * 5, reproduced=True, verification="verified", corroborating_agents=3, reachable=True) <= 0.99


def test_risk_formula_multiplies_factors():
    r = compute_risk("high", 0.8, 1.0, 0.8, 1.5)
    assert r["raw"] == pytest.approx(0.75 * 0.8 * 1.0 * 0.8 * 1.5, rel=1e-3)
    assert r["score"] == normalise(r["raw"])


def test_risk_score_is_monotonic_in_each_factor():
    assert compute_risk("critical", 0.9, 1, 0.8)["score"] > compute_risk("high", 0.9, 1, 0.8)["score"]
    assert compute_risk("high", 0.9, 1, 0.8, 1.5)["score"] > compute_risk("high", 0.9, 1, 0.8, 1.0)["score"]
    assert compute_risk("high", 0.5, 1, 0.8)["score"] < compute_risk("high", 0.9, 1, 0.8)["score"]


@pytest.mark.parametrize("score,priority", [(95, "P0"), (80, "P0"), (60, "P1"), (40, "P2"), (12, "P3"), (5, "P4")])
def test_priority_thresholds(score, priority):
    assert priority_for(score) == priority


def test_impact_prefers_security_critical_components():
    assert impact_for({"affected_components": ["authentication"], "affected_files": ["a/auth.py"]})[0] == 1.0
    assert impact_for({"affected_components": ["tests"], "affected_files": ["tests/test_x.py"], "category": "testing"})[0] < 0.5


def test_exploitability_distinguishes_measured_from_static():
    measured = exploitability_for({"category": "performance", "attributes": {"measurement": "measured"}})[0]
    static = exploitability_for({"category": "performance", "attributes": {"measurement": "static_suspect"}})[0]
    assert measured > static


def test_overall_risk_dominated_by_worst_and_bounded():
    assert overall_risk([])["score"] == 0
    o = overall_risk([90, 40, 40, 40])
    assert 90 <= o["score"] <= 100
    assert o["level"] == "critical"
