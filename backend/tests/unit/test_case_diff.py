"""Case diff: matching, classification and trend logic on plain dictionaries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services import case_diff as cd


def _f(fid="f", agent="dependency_agent", rule="vulnerable-dependency", subject="pyjwt", files=("requirements.txt",), sev="high", conf=0.9, title="PyJWT is vulnerable"):
    return {
        "finding_id": fid,
        "agent": agent,
        "category": "dependency",
        "rule_id": rule,
        "title": title,
        "severity": sev,
        "confidence": conf,
        "subject": subject,
        "affected_files": list(files),
        "affected_components": [],
    }


def _r(rid="r", kind="finding", category="dependency", title="PyJWT risk", priority="P1", score=65.0, severity="high"):
    return {
        "risk_id": rid,
        "kind": kind,
        "category": category,
        "title": title,
        "priority": priority,
        "score": score,
        "severity": severity,
    }


# ----------------------------------------------------------------------------- fingerprints
def test_finding_key_ignores_ids_and_confidence():
    assert cd.finding_key(_f(fid="a", conf=0.2)) == cd.finding_key(_f(fid="b", conf=0.99))


def test_finding_key_is_case_insensitive_on_subject_and_order_insensitive_on_files():
    a = _f(subject="PyJWT", files=("a.py", "b.py"))
    b = _f(subject="pyjwt", files=("b.py", "a.py"))
    assert cd.finding_key(a) == cd.finding_key(b)


def test_finding_key_separates_agent_rule_subject_and_files():
    base = cd.finding_key(_f())
    assert cd.finding_key(_f(agent="security_agent")) != base
    assert cd.finding_key(_f(rule="outdated-dependency")) != base
    assert cd.finding_key(_f(subject="requests")) != base
    assert cd.finding_key(_f(files=("pyproject.toml",))) != base


def test_risk_key_uses_kind_category_and_title():
    assert cd.risk_key(_r(rid="1")) == cd.risk_key(_r(rid="2"))
    assert cd.risk_key(_r(title="Other")) != cd.risk_key(_r())
    assert cd.risk_key(_r(kind="compound")) != cd.risk_key(_r())


# ----------------------------------------------------------------------------- findings
def test_new_resolved_and_persisting_are_separated():
    baseline = [_f("1", subject="a"), _f("2", subject="b")]
    current = [_f("3", subject="b"), _f("4", subject="c")]
    result = cd.compare_findings(baseline, current)
    assert [f["subject"] for f in result["new"]] == ["c"]
    assert [f["subject"] for f in result["resolved"]] == ["a"]
    assert [p["finding"]["subject"] for p in result["persisting"]] == ["b"]
    assert result["counts"] == {
        "baseline": 2,
        "current": 2,
        "new": 1,
        "resolved": 1,
        "persisting": 1,
        "escalated": 0,
        "relaxed": 0,
    }


def test_persisting_records_the_previous_finding_id():
    result = cd.compare_findings([_f("old")], [_f("new")])
    assert result["persisting"][0]["previous_finding_id"] == "old"
    assert result["persisting"][0]["finding"]["finding_id"] == "new"


def test_identical_cases_have_no_changes():
    result = cd.compare_findings([_f("1")], [_f("2")])
    assert result["new"] == [] and result["resolved"] == []
    assert result["persisting"][0]["changed"] is False
    assert result["persisting"][0]["changes"] == {}


def test_severity_escalation_is_counted():
    result = cd.compare_findings([_f(sev="medium")], [_f(sev="critical")])
    change = result["persisting"][0]["changes"]["severity"]
    assert change == {"from": "medium", "to": "critical", "direction": "escalated"}
    assert result["counts"]["escalated"] == 1 and result["counts"]["relaxed"] == 0


def test_severity_relaxation_is_counted():
    result = cd.compare_findings([_f(sev="high")], [_f(sev="low")])
    assert result["persisting"][0]["changes"]["severity"]["direction"] == "relaxed"
    assert result["counts"]["relaxed"] == 1


def test_small_confidence_moves_are_ignored_but_large_ones_reported():
    small = cd.compare_findings([_f(conf=0.80)], [_f(conf=0.83)])
    assert "confidence" not in small["persisting"][0]["changes"]
    large = cd.compare_findings([_f(conf=0.50)], [_f(conf=0.90)])
    assert large["persisting"][0]["changes"]["confidence"]["delta"] == 0.4


def test_title_change_is_reported():
    result = cd.compare_findings([_f(title="old wording")], [_f(title="new wording")])
    assert result["persisting"][0]["changes"]["title"] == {"from": "old wording", "to": "new wording"}


def test_duplicates_collapse_to_the_most_severe_finding():
    current = [_f("1", sev="low"), _f("2", sev="critical")]
    result = cd.compare_findings([], current)
    assert len(result["new"]) == 1
    assert result["new"][0]["severity"] == "critical"
    assert result["new"][0]["occurrences"] == 2


def test_new_findings_are_sorted_most_severe_first():
    current = [_f("1", subject="a", sev="low"), _f("2", subject="b", sev="critical"), _f("3", subject="c", sev="medium")]
    result = cd.compare_findings([], current)
    assert [f["severity"] for f in result["new"]] == ["critical", "medium", "low"]


def test_changed_persisting_findings_come_first():
    baseline = [_f("1", subject="a", sev="high"), _f("2", subject="b", sev="low")]
    current = [_f("3", subject="a", sev="high"), _f("4", subject="b", sev="high")]
    result = cd.compare_findings(baseline, current)
    assert [p["finding"]["subject"] for p in result["persisting"]] == ["b", "a"]


def test_empty_inputs():
    result = cd.compare_findings([], [])
    assert result["counts"]["new"] == 0 and result["counts"]["persisting"] == 0


# ----------------------------------------------------------------------------- histograms
def test_severity_histogram_counts_unique_findings():
    findings = [_f("1", subject="a", sev="high"), _f("2", subject="a", sev="high"), _f("3", subject="b", sev="low")]
    hist = cd._severity_histogram(findings)
    assert hist["high"] == 1 and hist["low"] == 1 and hist["critical"] == 0


def test_priority_histogram_has_every_bucket():
    hist = cd._priority_histogram([_r(priority="P0"), _r(priority="P0"), _r(priority="P3")])
    assert hist == {"P0": 2, "P1": 0, "P2": 0, "P3": 1, "P4": 0}


# ----------------------------------------------------------------------------- risks
def test_risks_appear_disappear_and_change():
    baseline = [_r("1", title="gone", score=70), _r("2", title="same", score=50, priority="P2"), _r("3", title="moved", score=40, priority="P2")]
    current = [_r("4", title="same", score=50, priority="P2"), _r("5", title="moved", score=82, priority="P0"), _r("6", title="fresh", score=30, priority="P3")]
    result = cd.compare_risks(baseline, current)
    assert [r["title"] for r in result["appeared"]] == ["fresh"]
    assert [r["title"] for r in result["disappeared"]] == ["gone"]
    [moved] = result["changed"]
    assert moved["title"] == "moved"
    assert moved["priority"] == {"from": "P2", "to": "P0"}
    assert moved["score"]["delta"] == 42


def test_priority_deltas():
    result = cd.compare_risks([_r(priority="P0", title="a")], [_r(priority="P0", title="a"), _r(priority="P0", title="b")])
    assert result["priorities"]["P0"] == {"baseline": 1, "current": 2, "delta": 1}
    assert result["priorities"]["P4"] == {"baseline": 0, "current": 0, "delta": 0}


def test_compound_risks_are_distinguished_from_plain_ones():
    result = cd.compare_risks([_r(kind="finding", title="x")], [_r(kind="compound", title="x")])
    assert len(result["appeared"]) == 1 and len(result["disappeared"]) == 1


# ----------------------------------------------------------------------------- verdict
def test_verdict_improved_when_score_drops():
    assert cd.verdict(80, 40, 0, 3, 0) == "improved"


def test_verdict_regressed_when_score_rises():
    assert cd.verdict(40, 80, 2, 0, 0) == "regressed"


def test_verdict_unchanged_when_nothing_moves():
    assert cd.verdict(50, 50, 0, 0, 0) == "unchanged"
    assert cd.verdict(50, 50.4, 0, 0, 0) == "unchanged"


def test_verdict_mixed_when_fixes_and_regressions_coexist():
    assert cd.verdict(50, 50, 2, 2, 0) == "mixed"


def test_verdict_regressed_on_escalation_even_if_score_flat():
    assert cd.verdict(50, 50, 0, 0, 1) == "regressed"


def test_verdict_handles_missing_scores():
    assert cd.verdict(None, None, 0, 0, 0) == "unchanged"
    assert cd.verdict(None, 60, 1, 0, 0) == "regressed"


def test_headline_mentions_counts_and_score_movement():
    summary = {
        "verdict": "improved",
        "overall_risk": {"delta": -12.5},
        "findings": {"counts": {"new": 1, "resolved": 4, "persisting": 6, "escalated": 0}},
    }
    text = cd.headline(summary)
    assert text.startswith("Improved:")
    assert "1 new" in text and "4 resolved" in text and "-12.5" in text


def test_headline_notes_escalations_and_flat_scores():
    summary = {
        "verdict": "regressed",
        "overall_risk": {"delta": 0.0},
        "findings": {"counts": {"new": 0, "resolved": 0, "persisting": 3, "escalated": 2}},
    }
    text = cd.headline(summary)
    assert "2 escalated" in text and "no change in risk score" in text


# ----------------------------------------------------------------------------- baseline selection
NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def _inv(iid, minutes_ago, *, status="completed", url="https://github.com/acme/shop", branch="main"):
    return SimpleNamespace(id=iid, created_at=NOW - timedelta(minutes=minutes_ago), status=status, repository_url=url, branch=branch)


class _Store:
    def __init__(self, rows):
        self.rows = rows

    def list_investigations(self, limit=50, owner_id=None):
        return sorted(self.rows, key=lambda i: i.created_at, reverse=True)[:limit]


def test_baseline_is_the_newest_earlier_finished_case_of_the_same_target():
    current = _inv("now", 0)
    rows = [current, _inv("older", 60), _inv("newest-earlier", 10), _inv("other-branch", 5, branch="dev"), _inv("running", 3, status="running")]
    assert cd.find_baseline(_Store(rows), current).id == "newest-earlier"


def test_baseline_ignores_later_cases_and_itself():
    current = _inv("now", 30)
    rows = [current, _inv("later", 5)]
    assert cd.find_baseline(_Store(rows), current) is None


def test_baseline_matches_repository_url_case_insensitively():
    current = _inv("now", 0, url="https://github.com/Acme/Shop/")
    rows = [current, _inv("prev", 10, url="https://github.com/acme/shop")]
    assert cd.find_baseline(_Store(rows), current).id == "prev"


def test_baseline_respects_the_visibility_predicate():
    current = _inv("now", 0)
    rows = [current, _inv("private", 5), _inv("public", 20)]
    chosen = cd.find_baseline(_Store(rows), current, can_see=lambda inv: inv.id != "private")
    assert chosen.id == "public"


def test_baseline_accepts_completed_with_limitations():
    current = _inv("now", 0)
    rows = [current, _inv("limited", 5, status="completed_with_limitations")]
    assert cd.find_baseline(_Store(rows), current).id == "limited"


def test_diff_error_for_identical_ids():
    try:
        cd.diff_investigations(_Store([]), "same", "same")
    except cd.DiffError as exc:
        assert "itself" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected DiffError")
