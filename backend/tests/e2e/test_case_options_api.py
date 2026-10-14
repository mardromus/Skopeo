"""Personal dry-run default, and switching dry run for one case while it exists."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.routes import apply_user_defaults
from app.config import get_settings
from app.main import create_app
from app.models import User
from app.schemas.investigation import InvestigationCreate


def _client() -> TestClient:
    s = get_settings().model_copy(update={"watch_scheduler_enabled": False, "rate_limit_per_minute": 0})
    return TestClient(create_app(s))


def test_personal_default_round_trip():
    with _client() as c:
        assert c.put("/api/auth/preferences", json={"dry_run": False}).json() == {"dry_run": False}
        assert c.get("/api/auth/me").json()["preferences"] == {"dry_run": False}
        assert c.put("/api/auth/preferences", json={"dry_run": None}).json() == {}


def test_user_default_applies_only_when_case_does_not_choose():
    u = User(preferences={"dry_run": False})
    req = InvestigationCreate(repository_url="https://github.com/o/r")
    assert apply_user_defaults(req, u).dry_run is False
    assert apply_user_defaults(req.model_copy(update={"dry_run": True}), u).dry_run is True
    assert apply_user_defaults(req, None).dry_run is None


def test_switch_dry_run_on_a_case():
    with _client() as c:
        iid = c.post("/api/demo/investigations", json={"fault_injection": False}).json()["investigation_id"]
        r = c.patch(f"/api/investigations/{iid}/options", json={"dry_run": False})
        assert r.status_code == 200 and r.json()["options"]["dry_run"] is False
        assert c.get(f"/api/investigations/{iid}").json()["options"]["dry_run"] is False
        assert c.patch(f"/api/investigations/{iid}/options", json={"dry_run": True}).json()["options"]["dry_run"] is True
