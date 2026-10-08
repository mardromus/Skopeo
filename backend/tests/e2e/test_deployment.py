"""Deployment hardening: access key, public demo, rate limiting, SPA serving, security headers,
restart recovery, workspace cleanup and environment parsing."""

from __future__ import annotations

import os
import stat
import time

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.access import RateLimiter
from app.config import Settings, get_settings
from app.main import create_app
from app.services.investigation_service import InvestigationService

KEY = "test-access-key-0123456789"
VALID = {"repository_url": "https://github.com/psf/requests", "branch": "main"}


def _client(**overrides) -> TestClient:
    return TestClient(create_app(get_settings().model_copy(update=overrides)))


def test_health_reports_access_policy():
    with _client(skopeo_api_key=SecretStr(KEY), skopeo_demo_public=True) as c:
        body = c.get("/api/health").json()
        assert body["auth_required"] is True and body["demo_public"] is True


def test_write_endpoints_require_the_key():
    with _client(skopeo_api_key=SecretStr(KEY), skopeo_demo_public=False) as c:
        assert c.post("/api/investigations", json=VALID).status_code == 401
        assert c.post("/api/investigations", json=VALID, headers={"X-Skopeo-Key": "wrong"}).status_code == 401
        assert c.post("/api/demo/investigations", json={}).status_code == 401
        assert c.post("/api/investigations/x/cancel").status_code == 401
        assert c.post("/api/investigations/x/approve-action", json={"action_id": "a", "approved_by": "me"}).status_code == 401
        # with the key, the request gets past access control (and then fails validation, without starting anything)
        bad = {"repository_url": "http://not-github.example/a/b"}
        assert c.post("/api/investigations", json=bad, headers={"X-Skopeo-Key": KEY}).status_code == 422
        assert c.post("/api/investigations", json=bad, headers={"Authorization": f"Bearer {KEY}"}).status_code == 422
        # reads stay open
        assert c.get("/api/investigations").status_code == 200


def test_public_demo_and_rate_limit():
    with _client(skopeo_api_key=SecretStr(KEY), skopeo_demo_public=True, rate_limit_per_minute=1) as c:
        first = c.post("/api/demo/investigations", json={"fault_injection": False, "step_delay_ms": 0})
        assert first.status_code == 202  # no key needed for the bundled reference case
        second = c.post("/api/demo/investigations", json={})
        assert second.status_code == 429 and int(second.headers["Retry-After"]) >= 1
        iid = first.json()["investigation_id"]
        c.post(f"/api/investigations/{iid}/cancel", headers={"X-Skopeo-Key": KEY})
        deadline = time.time() + 180
        while c.get(f"/api/investigations/{iid}").json()["status"] in ("queued", "running") and time.time() < deadline:
            time.sleep(1)
        # let the background run finish its last writes before the test database is torn down
        c.app.state.investigations.wait(iid, timeout=120)


def test_rate_limiter_window():
    limiter = RateLimiter(per_minute=2, window_seconds=0.3)
    assert limiter.check("a") is None and limiter.check("a") is None
    assert limiter.check("a") is not None
    assert limiter.check("b") is None  # per client
    time.sleep(0.35)
    assert limiter.check("a") is None
    assert RateLimiter(per_minute=0).check("a") is None


def test_security_headers_on_api():
    with _client() as c:
        r = c.get("/api/health")
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"


@pytest.fixture()
def static_dir(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>Skopeo</title><div id=root></div>")
    (tmp_path / "assets" / "app.js").write_text("console.log('skopeo')")
    (tmp_path / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    (tmp_path.parent / "secret.txt").write_text("outside the static root")
    return tmp_path


def test_single_container_serves_the_spa(static_dir):
    with _client(skopeo_static_dir=static_dir) as c:
        root = c.get("/")
        assert root.status_code == 200 and "<title>Skopeo</title>" in root.text
        assert "default-src 'self'" in root.headers["Content-Security-Policy"]
        deep = c.get("/investigations/abc123?tab=trace")
        assert deep.status_code == 200 and "<div id=root>" in deep.text  # SPA deep link
        assert c.get("/assets/app.js").text == "console.log('skopeo')"
        assert c.get("/favicon.svg").status_code == 200
        assert c.get("/api/does-not-exist").status_code == 404
        assert c.get("/api/health").json()["status"] == "ok"
        escaped = c.get("/..%2Fsecret.txt")
        assert "outside the static root" not in escaped.text
        assert c.get("/docs").status_code == 200  # OpenAPI UI still reachable
        assert c.head("/").status_code == 200  # uptime monitors probe with HEAD


def test_restart_recovery_marks_interrupted_cases_failed():
    svc = InvestigationService(get_settings())
    iid = svc.store.create_investigation(repository_url="https://github.com/a/b", repository_name="a/b", status="running")
    assert svc.recover_interrupted() >= 1
    inv = svc.store.get_investigation(iid)
    assert inv.status == "failed" and "server restarted" in inv.error
    assert svc.store.list_events(iid)[-1].event_type == "investigation_failed"
    svc.shutdown()


def test_workspace_cleanup_removes_only_its_own_directory(tmp_path):
    settings = get_settings().model_copy(update={"skopeo_workspace_dir": tmp_path / "ws", "skopeo_keep_workspaces": False})
    svc = InvestigationService(settings)
    repo = tmp_path / "ws" / "case-1" / "repo" / ".git" / "objects"
    repo.mkdir(parents=True)
    locked = repo / "pack"
    locked.write_text("x")
    os.chmod(locked, stat.S_IREAD)  # like git's read-only object files
    svc.remove_workspace("case-1")
    assert not (tmp_path / "ws" / "case-1").exists()
    (tmp_path / "keep").mkdir()
    svc.remove_workspace("../keep")  # never escapes the workspace root
    assert (tmp_path / "keep").exists()
    svc.shutdown()


def test_comma_separated_cors_origins_from_environment(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
    assert Settings().cors_origins == ["https://a.example", "https://b.example"]
