"""End-to-end through the HTTP API: repository URL -> investigation -> specialists ->
correlation -> verification -> risk -> recommendation -> execution trace.

The clone step is redirected to a local copy of the demo fixture (no network in CI), but the
investigation is treated exactly like an *untrusted* GitHub repository: tests and benchmarks
are NOT executed and that limitation must surface in the results.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.services import repository_ingestion

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def client():
    app = create_app(get_settings())
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def fake_clone(monkeypatch):
    def clone(settings, runner, investigation_id, url, branch):
        handle = repository_ingestion.prepare_demo_fixture(settings, runner, investigation_id)
        handle.source = "github"
        handle.full_name = "acme/shopfront"
        handle.url = url
        handle.trusted_execution = False
        return handle

    monkeypatch.setattr("app.graph.builder.clone_repository", clone)


def _wait(client, iid, timeout=240):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/investigations/{iid}").json()
        if body["status"] not in ("queued", "running"):
            return body
        time.sleep(1)
    raise AssertionError("investigation did not finish")


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["dry_run"] is True and body["mode"] == "mock"


@pytest.mark.parametrize("url", ["http://github.com/a/b", "https://evil.com/a/b", "https://github.com/a/b?x=1", "file:///etc/passwd"])
def test_rejects_invalid_repository_urls(client, url):
    assert client.post("/api/investigations", json={"repository_url": url}).status_code == 422


def test_full_api_flow(client, fake_clone):
    resp = client.post(
        "/api/investigations",
        json={
            "repository_url": "https://github.com/acme/shopfront",
            "branch": "main",
            "analysis_depth": "standard",
            "enable_github_actions": False,
        },
    )
    assert resp.status_code == 202
    iid = resp.json()["investigation_id"]
    detail = _wait(client, iid)
    assert detail["status"] in ("completed", "completed_with_limitations")
    assert detail["repo_profile"]["trusted_execution"] is False

    agents = client.get(f"/api/investigations/{iid}/agents").json()
    assert len({a["agent"] for a in agents}) >= 10
    findings = client.get(f"/api/investigations/{iid}/findings").json()
    assert findings
    high = client.get(f"/api/investigations/{iid}/findings", params={"severity": "high"}).json()
    assert high and all(f["severity"] == "high" for f in high)
    assert client.get(f"/api/investigations/{iid}/evidence").json()
    assert client.get(f"/api/investigations/{iid}/correlations").json()
    verifications = client.get(f"/api/investigations/{iid}/verifications").json()
    assert {v["decision"] for v in verifications} >= {"verified", "rejected"}
    risks = client.get(f"/api/investigations/{iid}/risks").json()
    assert risks
    assert client.get(f"/api/investigations/{iid}/recommendations").json()
    events = client.get(f"/api/investigations/{iid}/events").json()
    assert events[0]["event_type"] == "investigation_started" and events[-1]["event_type"] == "investigation_completed"
    later = client.get(f"/api/investigations/{iid}/events", params={"after_seq": events[-5]["seq"]}).json()
    assert len(later) == 4

    # untrusted repository: nothing executed, and the limitation is explicit
    assert not any(e["event_type"] == "tool_executed" for e in events)
    test_cov = detail["coverage"]["agents"]["test_reliability_agent"]
    assert test_cov["status"] == "partial" and any("NOT executed" in lim for lim in test_cov["limitations"])
    n1 = next(f for f in findings if f["rule_id"] == "performance.n_plus_one")
    assert n1["status"] == "needs_more_evidence" and n1["attributes"]["measurement"] == "static_suspect"

    report = client.get(f"/api/investigations/{iid}/report").json()
    assert {
        "investigation_id",
        "repository",
        "status",
        "overall_risk",
        "agent_summary",
        "findings",
        "correlations",
        "verified_findings",
        "rejected_findings",
        "risks",
        "recommendations",
        "coverage",
        "execution_summary",
    } <= set(report)
    md = client.get(f"/api/investigations/{iid}/report", params={"format": "markdown"})
    assert md.status_code == 200 and md.text.startswith("# Skopeo Investigation")

    actions = client.get(f"/api/investigations/{iid}/actions").json()
    if actions:
        a = actions[0]
        ok = client.post(
            f"/api/investigations/{iid}/approve-action", json={"action_id": a["action_id"], "approved_by": "e2e", "decision": "approve"}
        )
        assert ok.status_code == 200 and ok.json()["status"] == "approved_dry_run"
        again = client.post(f"/api/investigations/{iid}/approve-action", json={"action_id": a["action_id"], "approved_by": "e2e"})
        assert again.status_code == 409
    assert client.post(f"/api/investigations/{iid}/cancel").json()["cancel_requested"] is False


def test_demo_endpoint_and_cancel(client):
    resp = client.post("/api/demo/investigations", json={"fault_injection": True, "step_delay_ms": 200})
    assert resp.status_code == 202
    iid = resp.json()["investigation_id"]
    time.sleep(2)
    assert client.post(f"/api/investigations/{iid}/cancel").json()["cancel_requested"] in (True, False)
    detail = _wait(client, iid)
    assert detail["status"] in ("cancelled", "completed_with_limitations")


def test_unknown_investigation_404(client):
    assert client.get("/api/investigations/does-not-exist").status_code == 404
