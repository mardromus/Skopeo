"""The signed-in user flow through the HTTP API: accounts, notification channels and rules,
projects with context, upstream watches with impact reports, and notifications."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.auth import UserResolver
from app.auth import FirebaseTokenVerifier
from app.config import get_settings
from app.main import create_app, spa_csp
from tests.firebase_helpers import PROJECT_ID, FakeFirebase
from tests.unit.test_accounts_and_notifications import RecordingTransport
from tests.watch_fixtures import PROJECT_FILES, UPSTREAM_URL, V1, V2, FakeSource


def _client(**overrides) -> TestClient:
    base = {"watch_scheduler_enabled": False, "notifications_dry_run": False, "rate_limit_per_minute": 0}
    return TestClient(create_app(get_settings().model_copy(update=base | overrides)))


def _wait_watch(c: TestClient, wid: str, headers: dict | None = None) -> dict:
    c.app.state.watches.wait_idle(60)
    return c.get(f"/api/watches/{wid}", headers=headers or {}).json()


def test_local_mode_full_flow(tmp_path: Path):
    with _client() as c:
        transport = RecordingTransport()
        c.app.state.notifier.transport = transport
        source = FakeSource(tmp_path)
        source.serve(UPSTREAM_URL, None, V2, "b" * 40)
        source.serve(UPSTREAM_URL, "v1.7.1", V1, "a" * 40)
        source.tags = ["v1.7.0", "v1.7.1", "v2.0.0"]
        c.app.state.watches.source = source

        cfg = c.get("/api/auth/config").json()
        assert cfg["mode"] == "local" and cfg["firebase"] is None
        me = c.get("/api/auth/me").json()
        assert me["provider"] == "local"

        # 1. connect a notification channel and choose what it receives
        catalog = c.get("/api/notifications/catalog").json()
        assert {e["event"] for e in catalog["events"]} >= {"investigation.completed", "watch.impact"}
        created = c.post(
            "/api/notifications/channels",
            json={
                "kind": "slack",
                "name": "#deps",
                "target": "https://hooks.slack.com/services/T1/B1/flowtoken",
                "events": ["watch.impact", "watch.update"],
            },
        )
        assert created.status_code == 201, created.text
        channel = created.json()["channel"]
        assert channel["verified"] and channel["events"] == ["watch.impact", "watch.update"]
        assert c.post(f"/api/notifications/channels/{channel['channel_id']}/test").json()["status"] == "sent"

        # 2. connect a project with context (uploaded files + notes)
        project = c.post(
            "/api/projects",
            json={
                "name": "payments-api",
                "notes": "We use tokenlib to verify session tokens in app/auth.py.",
                "files": [{"path": p, "content": t} for p, t in PROJECT_FILES.items()],
            },
        )
        assert project.status_code == 201, project.text
        pid = project.json()["project_id"]
        assert project.json()["file_count"] == len(PROJECT_FILES)
        bad = c.put(f"/api/projects/{pid}/files", json={"files": [{"path": "../etc/passwd", "content": "x"}]})
        assert bad.status_code == 422

        # 3. watch the upstream: the first check compares the pinned 1.7.1 tag with the latest code
        watch = c.post(f"/api/projects/{pid}/watches", json={"upstream_url": UPSTREAM_URL, "frequency": "daily"})
        assert watch.status_code == 201, watch.text
        wid = watch.json()["watch_id"]
        w = _wait_watch(c, wid)
        assert w["status"] == "ok", w
        assert w["package_name"] == "tokenlib" and w["import_names"] == ["tokenlib"] and w["last_seen_version"] == "2.0.0"
        latest = w["latest_report"]
        assert latest["kind"] == "update" and latest["base_ref"] == "v1.7.1" and latest["impact_level"] == "breaking"
        report = c.get(f"/api/watch-reports/{latest['report_id']}").json()
        decode = next(i for i in report["impacts"] if i["file"] == "app/auth.py" and i["line"] == 8)
        assert decode["level"] == "breaking"
        assert report["stats"]["pinned"]["version"] == "1.7.1"
        assert "payments-api" in report["summary"] and report["narrative"]["decided_by"] == "policy"
        assert report["commits"] and report["narrative"]["changelog"]

        # 4. the impact was pushed to Slack
        impact_msgs = [m for kind, _, m, _ in transport.sent if m.event == "watch.impact"]
        assert impact_msgs and "breaking" in impact_msgs[0].subject
        deliveries = c.get("/api/notifications/deliveries").json()
        assert any(d["event"] == "watch.impact" and d["status"] == "sent" for d in deliveries)

        # 5. the user fixes their code and re-checks: no new upstream commits, so the last changes are re-assessed
        fixed = PROJECT_FILES["app/auth.py"].replace("verify=False", "algorithms=['HS256']")
        c.put(f"/api/projects/{pid}/files", json={"files": [{"path": "app/auth.py", "content": fixed}]})
        assert c.post(f"/api/watches/{wid}/check").json()["queued"] is True
        recheck = _wait_watch(c, wid)["latest_report"]
        assert recheck["kind"] == "recheck"
        rr = c.get(f"/api/watch-reports/{recheck['report_id']}").json()
        assert not any(i["file"] == "app/auth.py" and i["line"] == 8 and i["level"] == "breaking" for i in rr["impacts"])

        # 6. the scheduler checks again later; a new upstream commit is diffed against the stored snapshot
        v3 = dict(V2)
        v3["tokenlib/api.py"] = V2["tokenlib/api.py"] + "\n\ndef rotate(key, *, days):\n    return key\n"
        source.serve(UPSTREAM_URL, None, v3, "c" * 40)
        c.patch(f"/api/watches/{wid}", json={"frequency": "hourly"})
        from app.models import utcnow

        c.app.state.accounts.update_watch(wid, next_check_at=utcnow())
        assert c.app.state.watches.tick() == 1
        latest = _wait_watch(c, wid)["latest_report"]
        assert latest["kind"] == "update" and latest["base_ref"] == "2.0.0" and latest["stats"]["changes_by_kind"] == {"added": 1}
        assert latest["impact_level"] == "none"
        assert len(c.get(f"/api/watches/{wid}/reports").json()) == 3

        # unchanged upstream on a scheduled check: no new report
        c.app.state.accounts.update_watch(wid, next_check_at=utcnow())
        c.app.state.watches.tick()
        _wait_watch(c, wid)
        assert len(c.get(f"/api/watches/{wid}/reports").json()) == 3

        # 7. a failing check is recorded and notified
        c.post(
            "/api/notifications/channels",
            json={"kind": "discord", "target": "https://discord.com/api/webhooks/9/flow", "events": ["watch.failed"]},
        )
        source.trees.pop((UPSTREAM_URL, None))
        c.post(f"/api/watches/{wid}/check")
        failed = _wait_watch(c, wid)
        assert failed["status"] == "failed" and "no such ref" in failed["last_error"]
        assert any(m.event == "watch.failed" for _, _, m, _ in transport.sent)

        # cleanup through the API
        assert c.delete(f"/api/projects/{pid}").status_code == 204
        assert c.get(f"/api/watches/{wid}").status_code == 404


def test_firebase_mode_isolates_users():
    fb = FakeFirebase()
    with _client(
        firebase_project_id=PROJECT_ID, firebase_web_api_key="AIza-test", skopeo_api_key=SecretStr("k" * 24), skopeo_demo_public=False
    ) as c:
        c.app.state.user_resolver = UserResolver(c.app.state.settings, c.app.state.accounts, FirebaseTokenVerifier(PROJECT_ID, fb.fetch))
        alice = {"Authorization": f"Bearer {fb.token('uid-alice-e2e', 'alice-e2e@example.com')}"}
        bob = {"Authorization": f"Bearer {fb.token('uid-bob-e2e', 'bob-e2e@example.com')}"}

        cfg = c.get("/api/auth/config").json()
        assert (
            cfg["mode"] == "firebase"
            and cfg["firebase"]["projectId"] == PROJECT_ID
            and cfg["firebase"]["authDomain"] == f"{PROJECT_ID}.firebaseapp.com"
        )
        assert c.get("/api/auth/me").status_code == 401
        assert c.get("/api/projects").status_code == 401
        expired = {"Authorization": f"Bearer {fb.token('uid-alice-e2e', exp=int(time.time()) - 900)}"}
        assert c.get("/api/auth/me", headers=expired).status_code == 401

        me = c.get("/api/auth/me", headers=alice).json()
        assert me["email"] == "alice-e2e@example.com" and me["provider"] == "google" and me["email_verified"]

        # your own Google address needs no code
        ch = c.post("/api/notifications/channels", headers=alice, json={"kind": "email", "target": "alice-e2e@example.com"}).json()
        assert ch["channel"]["verified"] is True
        p = c.post("/api/projects", headers=alice, json={"name": "alice-app", "files": [{"path": "a.py", "content": "import os\n"}]}).json()

        assert c.get("/api/projects", headers=bob).json() == []
        assert c.get(f"/api/projects/{p['project_id']}", headers=bob).status_code == 404
        assert c.get("/api/notifications/channels", headers=bob).json() == []
        assert c.delete(f"/api/notifications/channels/{ch['channel']['channel_id']}", headers=bob).status_code == 404

        # a signed-in user may start scans without the shared access key (validation runs after access control)
        bad_url = {"repository_url": "http://not-github.example/a/b"}
        assert c.post("/api/investigations", json=bad_url).status_code == 401
        assert c.post("/api/investigations", json=bad_url, headers=alice).status_code == 422

        # deleting the account removes everything it owns
        assert c.delete("/api/auth/me", headers=alice).status_code == 204
        assert c.app.state.accounts.get_project(me["user_id"], p["project_id"]) is None

    csp = spa_csp(get_settings().model_copy(update={"firebase_project_id": PROJECT_ID}))
    assert "https://www.gstatic.com" in csp and f"frame-src https://{PROJECT_ID}.firebaseapp.com" in csp
    assert "www.gstatic.com" not in spa_csp(get_settings())


def test_require_login_blocks_anonymous_scans():
    fb = FakeFirebase()
    with _client(firebase_project_id=PROJECT_ID, auth_require_login=True) as c:
        c.app.state.user_resolver = UserResolver(c.app.state.settings, c.app.state.accounts, FirebaseTokenVerifier(PROJECT_ID, fb.fetch))
        bad_url = {"repository_url": "http://not-github.example/a/b"}
        assert c.post("/api/investigations", json=bad_url).status_code == 401
        assert c.post("/api/investigations", json=bad_url, headers={"Authorization": f"Bearer {fb.token('uid-zed')}"}).status_code == 422


@pytest.mark.slow
def test_finished_investigation_notifies_its_owner():
    with _client() as c:
        transport = RecordingTransport()
        c.app.state.notifier.transport = transport
        c.post(
            "/api/notifications/channels",
            json={
                "kind": "webhook",
                "target": "https://ci.example.com/skopeo-flow",
                "events": ["investigation.completed", "investigation.risk"],
            },
        )
        started = c.post("/api/demo/investigations", json={"fault_injection": False, "step_delay_ms": 0})
        assert started.status_code == 202
        iid = started.json()["investigation_id"]
        c.app.state.investigations.wait(iid, timeout=240)
        mine = c.get("/api/investigations?mine=true").json()
        assert any(i["investigation_id"] == iid for i in mine)
        events = [m for _, _, m, _ in transport.sent if m.data.get("investigation_id") == iid]
        kinds = {m.event for m in events}
        assert "investigation.completed" in kinds and "investigation.risk" in kinds
        risk = next(m for m in events if m.event == "investigation.risk")
        assert risk.data["top_priority"] in ("P0", "P1") and risk.items
