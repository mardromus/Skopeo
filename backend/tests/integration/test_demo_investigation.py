"""Full investigation of the bundled demo repository — the acceptance scenario.

One investigation is run (mock LLM, offline snapshot, controlled performance-agent failure)
and every acceptance criterion is asserted against the persisted Evidence Store and trace.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from app.config import get_settings
from app.schemas.investigation import ApproveActionRequest, DemoInvestigationCreate
from app.services.actions import decide_action
from app.services.investigation_service import InvestigationService
from app.services.report import build_markdown, build_report
from tests.conftest import DEMO_REPO

pytestmark = pytest.mark.slow


def _tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


@pytest.fixture(scope="module")
def demo():
    before = _tree_hash(DEMO_REPO)
    svc = InvestigationService(get_settings())
    iid = svc.create_demo(DemoInvestigationCreate(fault_injection=True, step_delay_ms=0))
    svc.run_sync(iid)
    report = build_report(svc.store, iid)
    yield {"svc": svc, "id": iid, "report": report, "fixture_hash_before": before}
    svc.shutdown()


def _events(demo, etype=None):
    return [e for e in demo["report"]["events"] if etype is None or e["event_type"] == etype]


def _finding(demo, rule, contains=""):
    return next(f for f in demo["report"]["findings"] if f["rule_id"] == rule and contains in " ".join(f["affected_files"]) + f["title"])


def test_investigation_completes_with_limitations(demo):
    assert demo["report"]["status"] == "completed_with_limitations"
    assert demo["report"]["overall_risk"]["score"] > 0


def test_orchestrator_creates_plan_with_reasoned_selection(demo):
    plan = _events(demo, "plan_created")
    assert len(plan) == 1
    planned = {t["agent"] for t in plan[0]["payload"]["tasks"]}
    assert len(planned) >= 4
    assert all(t["rationale"] for t in plan[0]["payload"]["tasks"])
    assert "Repository detected as Python project" in demo["report"]["plan"]["assessment"]


def test_specialists_run_in_parallel(demo):
    assert demo["report"]["execution_summary"]["parallelism"] >= 4
    started = {e["sender"] for e in _events(demo, "agent_started")}
    assert (
        len(
            started
            & {
                "security_agent",
                "dependency_agent",
                "test_reliability_agent",
                "code_quality_agent",
                "license_agent",
                "api_compatibility_agent",
                "maintenance_agent",
                "performance_agent",
            }
        )
        == 8
    )


def test_findings_enter_evidence_store_with_traceable_evidence(demo):
    svc, iid = demo["svc"], demo["id"]
    findings = svc.store.list_findings(iid)
    assert len(findings) >= 15
    for f in findings:
        assert f.evidence_ids or f.is_hypothesis
    ev = svc.store.list_evidence(iid)
    assert all(e.tool and e.source and e.created_by for e in ev)
    assert any(e.content_hash for e in ev)


def test_adaptive_follow_up_and_replanning(demo):
    replans = _events(demo, "replan")
    assert replans, "orchestrator never re-planned"
    first = replans[0]["payload"]["added_tasks"]
    modes = {(t["agent"], t["mode"]) for t in first}
    assert {
        ("security_agent", "dependency_usage"),
        ("api_compatibility_agent", "upgrade_compatibility"),
        ("test_reliability_agent", "dependency_coverage"),
    } <= modes
    request = next(e for e in _events(demo, "investigation_requested") if e["sender"] == "dependency_agent")
    assert request["payload"]["focus"]["package"] == "pyjwt"
    usage = _finding(demo, "security.vulnerable_dependency_usage")
    assert "shopfront/auth/middleware.py" in usage["affected_files"]
    runs = demo["svc"].store.list_agent_runs(demo["id"])
    assert sum(1 for r in runs if r.trigger == "follow_up") >= 3


def test_correlation_connects_findings_across_agents(demo):
    compound = next(
        c for c in demo["report"]["correlations"] if c["relationship_type"] == "compound_risk" and "upgrade" in c["title"].lower()
    )
    agents = {f["agent"] for f in demo["report"]["findings"] if f["finding_id"] in compound["finding_ids"]}
    assert {"dependency_agent", "security_agent", "test_reliability_agent", "api_compatibility_agent"} <= agents
    assert compound["status"] == "verified" and compound["risk_multiplier"] > 1.0


def test_verification_challenges_and_rejects_false_positive(demo):
    fixture = _finding(demo, "security.hardcoded_secret", "example_credentials.txt")
    assert fixture["status"] == "rejected"
    assert fixture["verification"]["decision"] == "rejected"
    assert "placeholder" in fixture["verification"]["reasoning_summary"].lower()
    assert any(e["event_type"] == "challenge" and e["receiver"] == "security_agent" for e in _events(demo))
    assert all(r["finding_id"] != fixture["finding_id"] for r in demo["report"]["risks"])


def test_verification_verifies_legitimate_findings(demo):
    vuln = _finding(demo, "dependency.vulnerable")
    assert vuln["status"] == "verified"
    checks = {c["check"]: c["outcome"] for c in vuln["verification"]["checks"]}
    assert checks["dependency_used"] == "pass" and checks["evidence_integrity"] == "pass"
    failing = _finding(demo, "testing.test_failure")
    assert failing["status"] == "verified"
    assert any(c["check"] == "reproduction" and c["outcome"] == "pass" for c in failing["verification"]["checks"])


def test_risk_agent_scores_only_verified_findings(demo):
    by_id = {f["finding_id"]: f for f in demo["report"]["findings"]}
    assert demo["report"]["risks"]
    for risk in demo["report"]["risks"]:
        for fid in risk["member_finding_ids"]:
            assert by_id[fid]["status"] == "verified"
        assert risk["rationale"].startswith(risk["priority"])
    compound = [r for r in demo["report"]["risks"] if r["kind"] == "compound"]
    assert compound and compound[0]["priority"] in ("P0", "P1")


def test_recommendations_are_actionable(demo):
    recs = demo["report"]["recommendations"]
    assert recs
    top = recs[0]
    for key in (
        "problem",
        "affected_component",
        "why_it_matters",
        "proposed_fix",
        "estimated_risk",
        "verification_status",
        "expected_benefit",
        "implementation_difficulty",
    ):
        assert top[key]
    assert "Upgrade" in top["proposed_fix"] and "test" in top["proposed_fix"].lower()


def test_agent_failure_is_isolated_and_retried(demo):
    runs = [r for r in demo["svc"].store.list_agent_runs(demo["id"]) if r.agent == "performance_agent"]
    assert runs[0].status == "failed" and runs[0].error_type == "ToolUnavailableError"
    assert "fault injection" in runs[0].error_message
    retry = next(r for r in runs if r.trigger == "retry")
    assert retry.status == "completed" and retry.strategy == "static_only"
    assert _events(demo, "agent_failed") and _events(demo, "agent_retry_scheduled")
    assert demo["report"]["coverage"]["agents"]["performance_agent"]["status"] == "partial"
    others = [r for r in demo["svc"].store.list_agent_runs(demo["id"]) if r.agent not in ("performance_agent",)]
    assert all(r.status == "completed" for r in others)


def test_disagreement_resolved_by_benchmark(demo):
    contradiction = next(c for c in demo["report"]["correlations"] if c["relationship_type"] == "contradiction")
    assert contradiction["status"] == "resolved"
    n1 = _finding(demo, "performance.n_plus_one")
    assert n1["status"] == "verified" and n1["attributes"]["measurement"] == "measured"
    results = n1["attributes"]["benchmark"]["results"]
    assert [r["queries"] for r in results] == [r["n"] + 1 for r in results]  # measured, not inferred
    assessment = _finding(demo, "code_quality.data_access_assessment", "orders.py")
    assert assessment["status"] == "rejected"
    bench_request = next(e for e in _events(demo, "investigation_requested") if e["payload"].get("required_evidence") == "benchmark")
    assert bench_request["sender"] == "verification_agent"


def test_unmeasurable_claim_stays_insufficient_evidence(demo):
    net = _finding(demo, "performance.network_in_loop")
    assert net["status"] == "needs_more_evidence"
    assert net["attributes"]["measurement"] == "static_suspect"
    assert all(net["finding_id"] not in r["member_finding_ids"] for r in demo["report"]["risks"])


def test_trace_is_complete_ordered_and_real(demo):
    events = demo["report"]["events"]
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    types = {e["event_type"] for e in events}
    for required in (
        "investigation_started",
        "plan_created",
        "agent_started",
        "agent_completed",
        "agent_failed",
        "finding_created",
        "evidence_added",
        "agent_message",
        "investigation_requested",
        "replan",
        "correlation_created",
        "verification_started",
        "finding_rejected",
        "finding_verified",
        "risk_assessed",
        "recommendation_created",
        "github_action_proposed",
        "human_approval_required",
        "investigation_completed",
    ):
        assert required in types, required
    tool_runs = [e for e in events if e["event_type"] == "tool_executed"]
    assert any("pytest" in e["payload"].get("command", "") and e["payload"]["exit_code"] == 1 for e in tool_runs)


def test_no_uncontrolled_repository_modification(demo):
    assert _tree_hash(DEMO_REPO) == demo["fixture_hash_before"]
    workspace = get_settings().skopeo_workspace_dir / demo["id"] / "repo"
    status = subprocess.run(
        ["git", "-c", f"safe.directory={workspace.as_posix()}", "status", "--porcelain"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout.strip() == "", status.stdout


def test_actions_require_human_approval_and_respect_dry_run(demo):
    svc = demo["svc"]
    actions = svc.store.list_actions(demo["id"])
    assert actions and all(a.status == "proposed" and a.requires_approval for a in actions)
    pr = next(a for a in actions if a.action_type == "pull_request")
    assert "-PyJWT==1.7.1" in pr.patch and "+PyJWT==" in pr.patch
    decided = decide_action(
        svc.store, svc.events, get_settings(), demo["id"], ApproveActionRequest(action_id=pr.action_id, approved_by="reviewer")
    )
    assert decided.status == "approved_dry_run" and decided.result["dry_run"] is True


def test_markdown_export_is_presentation_ready(demo):
    md = build_markdown(demo["svc"].store, demo["id"])
    for heading in (
        "# Skopeo Investigation",
        "## Agent Activity",
        "## Verified Risks",
        "## Correlations",
        "## Verification (Red-Team)",
        "## Rejected Findings",
        "## Recommendations",
        "## Agent Timeline",
    ):
        assert heading in md
    assert "AKIAIOSFODNN7EXAMPLE" not in md
