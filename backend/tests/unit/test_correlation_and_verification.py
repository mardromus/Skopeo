"""Agent-level tests: the correlation agent links findings from different agents and the
red-team agent can both reject and verify — using its own independent checks."""

from app.agents.correlation import CorrelationAgent
from app.agents.dependencies import DependencyAgent
from app.agents.security import SecurityAgent
from app.agents.test_reliability import TestReliabilityAgent
from app.agents.verification import VerificationAgent
from app.schemas import AgentTask, Category, EvidenceDraft, FindingDraft, Severity, SourceType
from tests.helpers import make_services, run_agent


def _by_rule(services, rule):
    return [f for f in services.store.list_findings(services.investigation_id) if f.rule_id == rule]


def test_red_team_rejects_documented_dummy_credential(demo_repo_copy):
    services = make_services(demo_repo_copy)
    run_agent(services, SecurityAgent())
    fixture = [f for f in _by_rule(services, "security.hardcoded_secret") if "example_credentials" in f.affected_files[0]]
    assert fixture and fixture[0].status.value == "proposed"
    run_agent(services, VerificationAgent(), AgentTask(agent="verification_agent", objective="verify", focus={"round": 1}))
    after = services.store.get_finding(fixture[0].finding_id)
    assert after.status.value == "rejected"
    assert after.confidence <= 0.10
    v = services.store.list_verifications(services.investigation_id, fixture[0].finding_id)[-1]
    checks = {c["check"]: c["outcome"] for c in v.checks}
    assert checks["placeholder"] == "fail" and checks["production_reference"] == "fail"
    assert "AKIAIOSFODNN7EXAMPLE" not in v.reasoning_summary  # masked, never echoed


def test_red_team_verifies_real_looking_secret_in_production_code(tmp_path):
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "__init__.py").write_text("")
    (repo / "app" / "main.py").write_text("from app import settings\n")
    fake_key = "AKIA" + "Q3EGRQ7RXMKV5N2P"  # made up; assembled at runtime so secret scanners ignore the repo
    (repo / "app" / "settings.py").write_text(f"AWS_KEY = '{fake_key}'\n")
    services = make_services(repo)
    run_agent(services, SecurityAgent())
    secret = _by_rule(services, "security.hardcoded_secret")[0]
    run_agent(services, VerificationAgent(), AgentTask(agent="verification_agent", objective="verify", focus={"round": 1}))
    assert services.store.get_finding(secret.finding_id).status.value == "verified"


def test_red_team_rejects_tampered_evidence(demo_repo_copy):
    services = make_services(demo_repo_copy)
    run_agent(services, SecurityAgent())
    md5 = _by_rule(services, "security.weak_password_hash")[0]
    target = demo_repo_copy / "shopfront" / "auth" / "passwords.py"
    target.write_text(target.read_text().replace("hashlib.md5", "hashlib.sha256"))
    services.tools._text_cache.clear()
    run_agent(services, VerificationAgent(), AgentTask(agent="verification_agent", objective="verify", focus={"round": 1}))
    after = services.store.get_finding(md5.finding_id)
    assert after.status.value == "rejected"
    v = services.store.list_verifications(services.investigation_id, md5.finding_id)[-1]
    assert any(c["check"] == "evidence_integrity" and c["outcome"] == "fail" for c in v.checks)


def test_static_performance_suspect_needs_more_evidence(tmp_path):
    repo = tmp_path / "repo"
    (repo / "svc").mkdir(parents=True)
    (repo / "svc" / "__init__.py").write_text("")
    (repo / "svc" / "q.py").write_text(
        "def load(conn, ids):\n    out = []\n    for i in ids:\n        out.append(conn.execute('select', (i,)).fetchall())\n    return out\n"
    )
    from app.agents.performance import PerformanceAgent

    services = make_services(repo)
    run_agent(services, PerformanceAgent(), AgentTask(agent="performance_agent", objective="perf", strategy="static_only"))
    finding = _by_rule(services, "performance.n_plus_one")[0]
    assert finding.attributes["measurement"] == "static_suspect"
    run_agent(services, VerificationAgent(), AgentTask(agent="verification_agent", objective="verify", focus={"round": 1}))
    assert services.store.get_finding(finding.finding_id).status.value == "needs_more_evidence"
    reqs = services.store.list_requests(services.investigation_id)
    assert reqs and reqs[0].required_evidence == "benchmark" and reqs[0].target_agent == "performance_agent"


def test_correlation_builds_compound_risk_from_three_agents(demo_repo_copy):
    services = make_services(demo_repo_copy)
    run_agent(services, DependencyAgent())
    dep = _by_rule(services, "dependency.vulnerable")[0]
    run_agent(
        services,
        SecurityAgent(),
        AgentTask(
            agent="security_agent",
            objective="usage",
            mode="dependency_usage",
            focus={"package": "pyjwt", "import_name": "jwt", "finding_id": dep.finding_id},
        ),
    )
    run_agent(services, TestReliabilityAgent(), AgentTask(agent="test_reliability_agent", objective="tests", strategy="default"))
    run_agent(services, CorrelationAgent())
    corrs = services.store.list_correlations(services.investigation_id)
    compound = [c for c in corrs if c.relationship_type.value == "compound_risk" and "upgrade" in c.title.lower()]
    assert compound, [c.title for c in corrs]
    members = {services.store.get_finding(i).agent for i in compound[0].finding_ids}
    assert {"dependency_agent", "security_agent", "test_reliability_agent"} <= members
    assert compound[0].risk_multiplier > 1.0
    assert any(c.relationship_type.value == "shared_root_cause" for c in corrs)


def test_correlation_detects_contradiction_between_agents(tmp_path):
    services = make_services(tmp_path)
    iid = services.store.create_investigation(repository_url="https://github.com/a/b", repository_name="a/b", status="running")
    services.investigation_id = iid
    ev = EvidenceDraft(source_type=SourceType.STATIC_ANALYSIS, source="s", tool="t", excerpt="x")
    subject = "py:svc/q.py::load"
    services.store.add_finding(
        iid,
        "performance_agent",
        None,
        FindingDraft(
            category=Category.PERFORMANCE,
            rule_id="performance.n_plus_one",
            title="N+1",
            description="d",
            severity=Severity.MEDIUM,
            subject=subject,
            attributes={"measurement": "static_suspect"},
            reasoning_summary="r",
        ),
        [ev],
    )
    services.store.add_finding(
        iid,
        "code_quality_agent",
        None,
        FindingDraft(
            category=Category.CODE_QUALITY,
            rule_id="code_quality.data_access_assessment",
            title="Assessed acceptable",
            description="d",
            severity=Severity.INFO,
            subject=subject,
            attributes={"stance": "acceptable"},
            reasoning_summary="small dataset",
        ),
        [ev],
    )
    run_agent(services, CorrelationAgent())
    corrs = services.store.list_correlations(iid)
    assert [c.relationship_type.value for c in corrs] == ["contradiction"]
    assert "insufficient evidence" in corrs[0].description.lower()
