"""SARIF export: pure mapping helpers (no investigation needed)."""

from __future__ import annotations

from types import SimpleNamespace

from app.services import sarif


def _finding(**overrides):
    base = {
        "finding_id": "f-1",
        "agent": "dependency_agent",
        "category": "dependency",
        "rule_id": "vulnerable-dependency",
        "title": "PyJWT 1.7.1 is affected by known vulnerabilities",
        "description": "The pinned version has published advisories.",
        "severity": "high",
        "confidence": 0.91234,
        "status": "verified",
        "subject": "pyjwt",
        "affected_files": ["requirements.txt"],
        "affected_components": ["authentication"],
        "recommended_action": "Upgrade to a patched release.",
        "reasoning_summary": "Advisory matches the pinned version.",
    }
    return base | overrides


def _evidence(file="requirements.txt", start=3, end=3, excerpt="PyJWT==1.7.1"):
    return SimpleNamespace(file=file, line_start=start, line_end=end, excerpt=excerpt)


def test_rule_key_is_agent_and_rule():
    assert sarif._rule_key("security_agent", "hardcoded-secret") == "security_agent/hardcoded-secret"


def test_fingerprint_ignores_ids_and_confidence():
    a = _finding()
    b = _finding(finding_id="f-2", confidence=0.2, title="a different wording of the same problem")
    assert sarif._fingerprint(a) == sarif._fingerprint(b)


def test_fingerprint_changes_with_subject_or_files():
    base = sarif._fingerprint(_finding())
    assert sarif._fingerprint(_finding(subject="requests")) != base
    assert sarif._fingerprint(_finding(affected_files=["app/auth.py"])) != base


def test_fingerprint_ignores_file_order():
    one = _finding(affected_files=["a.py", "b.py"])
    two = _finding(affected_files=["b.py", "a.py"])
    assert sarif._fingerprint(one) == sarif._fingerprint(two)


def test_level_mapping_covers_every_severity():
    assert sarif.LEVEL_BY_SEVERITY["critical"] == "error"
    assert sarif.LEVEL_BY_SEVERITY["high"] == "error"
    assert sarif.LEVEL_BY_SEVERITY["medium"] == "warning"
    assert sarif.LEVEL_BY_SEVERITY["low"] == "note"
    assert sarif.LEVEL_BY_SEVERITY["info"] == "note"
    assert set(sarif.LEVEL_BY_SEVERITY) == set(sarif.SECURITY_SEVERITY)


def test_region_is_one_based_and_optional():
    assert sarif._region(None, None, None) is None
    assert sarif._region(0, 0, "x") is None
    assert sarif._region(4, None, None) == {"startLine": 4}
    assert sarif._region(4, 9, None) == {"startLine": 4, "endLine": 9}


def test_region_ignores_inverted_range_and_carries_snippet():
    region = sarif._region(10, 2, "code")
    assert region == {"startLine": 10, "snippet": {"text": "code"}}


def test_region_truncates_long_snippets():
    region = sarif._region(1, 1, "x" * 2000)
    assert len(region["snippet"]["text"]) == 500


def test_physical_location_normalises_backslashes():
    loc = sarif._physical_location("app\\auth\\middleware.py", {"startLine": 2})
    physical = loc["physicalLocation"]
    assert physical["artifactLocation"] == {"uri": "app/auth/middleware.py", "uriBaseId": "%SRCROOT%"}
    assert physical["region"] == {"startLine": 2}


def test_locations_prefer_evidence_with_lines():
    locs = sarif._locations(_finding(), [_evidence()])
    assert len(locs) == 1
    physical = locs[0]["physicalLocation"]
    assert physical["artifactLocation"]["uri"] == "requirements.txt"
    assert physical["region"]["startLine"] == 3


def test_locations_add_affected_files_not_covered_by_evidence():
    finding = _finding(affected_files=["requirements.txt", "app/auth.py"])
    locs = sarif._locations(finding, [_evidence()])
    uris = [loc["physicalLocation"]["artifactLocation"]["uri"] for loc in locs]
    assert uris == ["requirements.txt", "app/auth.py"]
    assert "region" not in locs[1]["physicalLocation"]


def test_locations_deduplicate_identical_evidence():
    locs = sarif._locations(_finding(), [_evidence(), _evidence()])
    assert len(locs) == 1


def test_locations_fall_back_to_repository_root():
    locs = sarif._locations(_finding(affected_files=[]), [])
    assert locs[0]["physicalLocation"]["artifactLocation"]["uri"] == sarif.REPOSITORY_ROOT_URI


def test_build_rules_deduplicates_by_agent_and_rule():
    findings = [_finding(), _finding(finding_id="f-2"), _finding(finding_id="f-3", rule_id="outdated-dependency")]
    rules, index = sarif._build_rules(findings)
    assert [r["id"] for r in rules] == [
        "dependency_agent/vulnerable-dependency",
        "dependency_agent/outdated-dependency",
    ]
    assert index["dependency_agent/outdated-dependency"] == 1


def test_rule_carries_security_severity_and_tags():
    rules, _ = sarif._build_rules([_finding(severity="critical")])
    props = rules[0]["properties"]
    assert props["security-severity"] == "9.5"
    assert "skopeo" in props["tags"] and "dependency" in props["tags"]
    assert rules[0]["defaultConfiguration"]["level"] == "error"


def test_verified_result_has_no_suppression():
    _, index = sarif._build_rules([_finding()])
    result = sarif._result(_finding(), [_evidence()], None, index)
    assert "suppressions" not in result
    assert result["level"] == "error"
    assert result["ruleIndex"] == 0
    assert result["properties"]["confidence"] == 0.912
    assert result["properties"]["evidenceCount"] == 1


def test_rejected_result_is_suppressed_with_red_team_reasoning():
    finding = _finding(status="rejected", severity="medium")
    _, index = sarif._build_rules([finding])
    verification = {"reasoning_summary": "Documented placeholder value in a test fixture."}
    result = sarif._result(finding, [], verification, index)
    [suppression] = result["suppressions"]
    assert suppression["kind"] == "external"
    assert "placeholder" in suppression["justification"]
    assert result["level"] == "warning"


def test_message_prefers_verification_reasoning():
    text = sarif._message(_finding(), {"reasoning_summary": "Confirmed by import graph."})
    assert text.endswith("Confirmed by import graph.")
    assert text.startswith("PyJWT 1.7.1")


def test_message_falls_back_to_finding_reasoning():
    assert "Advisory matches" in sarif._message(_finding(), None)


def test_invocation_reports_success_only_for_finished_cases():
    done = SimpleNamespace(status="completed_with_limitations", started_at=None, completed_at=None, execution_summary={})
    failed = SimpleNamespace(status="failed", started_at=None, completed_at=None, execution_summary={})
    assert sarif._invocation(done)["executionSuccessful"] is True
    assert sarif._invocation(failed)["executionSuccessful"] is False


def test_schema_constants():
    assert sarif.SARIF_VERSION == "2.1.0"
    assert sarif.SARIF_SCHEMA.endswith("sarif-2.1.0.json")
