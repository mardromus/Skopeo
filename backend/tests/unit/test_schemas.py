import pytest
from pydantic import ValidationError

from app.schemas import Category, EvidenceDraft, FindingDraft, FindingOut, Severity, SourceType
from app.services.evidence_store import EvidenceStore, MissingEvidenceError

SPEC_FINDING_KEYS = {
    "finding_id",
    "agent",
    "category",
    "title",
    "description",
    "severity",
    "confidence",
    "status",
    "affected_files",
    "affected_components",
    "evidence_ids",
    "tool_results",
    "reasoning_summary",
    "recommended_action",
    "created_at",
    "updated_at",
}


def _draft(**kw):
    base = dict(
        category=Category.SECURITY,
        rule_id="security.test",
        title="Test finding",
        description="desc",
        severity=Severity.HIGH,
        affected_files=["app/x.py"],
        reasoning_summary="because",
    )
    base.update(kw)
    return FindingDraft(**base)


def _evidence(**kw):
    base = dict(
        source_type=SourceType.STATIC_ANALYSIS, source="app/x.py:1", tool="unit", file="app/x.py", line_start=1, line_end=1, excerpt="x = 1"
    )
    base.update(kw)
    return EvidenceDraft(**base)


def test_finding_out_contains_documented_contract_fields():
    assert set(FindingOut.model_fields) >= SPEC_FINDING_KEYS


@pytest.mark.parametrize("path", ["/etc/passwd", "../outside.py", "a/../../b.py"])
def test_finding_rejects_non_relative_paths(path):
    with pytest.raises(ValidationError):
        _draft(affected_files=[path])


def test_finding_rejects_unknown_severity():
    with pytest.raises(ValidationError):
        _draft(severity="catastrophic")


def test_finding_forbids_extra_fields():
    with pytest.raises(ValidationError):
        FindingDraft(**_draft().model_dump(), hidden_chain_of_thought="no")


def test_evidence_line_range_must_be_ordered():
    with pytest.raises(ValidationError):
        _evidence(line_start=10, line_end=2)


def test_evidence_rejects_traversal_file():
    with pytest.raises(ValidationError):
        _evidence(file="../secrets.txt")


def test_evidence_source_type_is_enumerated():
    with pytest.raises(ValidationError):
        _evidence(source_type="vibes")


def test_finding_without_evidence_is_refused_unless_hypothesis():
    store = EvidenceStore()
    iid = store.create_investigation(repository_url="https://github.com/a/b", repository_name="a/b", status="running")
    with pytest.raises(MissingEvidenceError):
        store.add_finding(iid, "security_agent", None, _draft(), [])
    hyp = store.add_finding(iid, "security_agent", None, _draft(is_hypothesis=True), [])
    assert hyp.is_hypothesis and hyp.confidence <= 0.4


def test_persisted_finding_round_trip_and_redaction():
    store = EvidenceStore()
    iid = store.create_investigation(repository_url="https://github.com/a/b", repository_name="a/b", status="running")
    token = "ghp_" + "A" * 36
    out = store.add_finding(iid, "security_agent", None, _draft(description=f"leaked {token}"), [_evidence(excerpt=f"TOKEN={token}")])
    assert out.status.value == "proposed"
    assert len(out.evidence_ids) == 1
    assert token not in out.description
    ev = store.list_evidence(iid, out.finding_id)[0]
    assert token not in ev.excerpt
    assert out.confidence_factors and out.confidence_factors[0]["factor"] == "evidence_strength"
