"""GitHub sign-in / repository import, private-case isolation, and the agent-routed case chat."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth import UserResolver
from app.auth import FirebaseTokenVerifier
from app.chat import ChatService, keyword_route
from app.chat.service import ChatAnswer, RouteDecision
from app.config import get_settings
from app.database import session_scope
from app.llm.base import LLMProvider
from app.main import create_app, spa_csp
from app.models import GitHubConnection
from app.schemas.investigation import DemoInvestigationCreate
from app.security.secretbox import SecretBox
from app.services.github_accounts import GitHubAccounts
from app.services.repository_ingestion import git_auth_env
from tests.firebase_helpers import PROJECT_ID, FakeFirebase

TOKEN_ALICE = "gho_alice0000000000000000000000000000"
TOKEN_BOB = "gho_bob000000000000000000000000000000"


def _client(**overrides) -> TestClient:
    base = {"watch_scheduler_enabled": False, "rate_limit_per_minute": 0}
    return TestClient(create_app(get_settings().model_copy(update=base | overrides)))


class FakeGitHub:
    """Just enough of api.github.com: /user, /user/repos and /repos/{owner}/{name}."""

    users = {TOKEN_ALICE: (101, "alice-gh", "repo, read:user"), TOKEN_BOB: (202, "bob-gh", "read:user")}
    repos = [
        {"full_name": "alice-gh/public-app", "private": False, "description": "a public app"},
        {"full_name": "alice-gh/secret-app", "private": True, "description": "private stuff"},
    ]

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        self.calls.append((request.url.path, dict(request.url.params)))
        if token not in self.users:
            return httpx.Response(401, json={"message": "Bad credentials"})
        uid, login, scopes = self.users[token]
        path = request.url.path
        if path == "/user":
            return httpx.Response(
                200,
                json={"id": uid, "login": login, "avatar_url": "https://avatars.githubusercontent.com/u/1"},
                headers={"x-oauth-scopes": scopes},
            )
        if path == "/user/repos":
            vis = request.url.params.get("visibility")
            rows = [r for r in self.repos if vis == "all" or not r["private"]]
            return httpx.Response(
                200, json=[{**r, "html_url": f"https://github.com/{r['full_name']}", "default_branch": "main"} for r in rows]
            )
        if path.startswith("/repos/"):
            name = path.removeprefix("/repos/")
            for r in self.repos:
                if r["full_name"] == name:
                    return httpx.Response(200, json={**r, "default_branch": "main"})
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(404)


def _firebase_client(fb: FakeFirebase, gh: FakeGitHub, **overrides) -> TestClient:
    c = _client(firebase_project_id=PROJECT_ID, firebase_web_api_key="AIza-test", **overrides)
    c.__enter__()
    c.app.state.user_resolver = UserResolver(c.app.state.settings, c.app.state.accounts, FirebaseTokenVerifier(PROJECT_ID, fb.fetch))
    c.app.state.github_accounts = GitHubAccounts(c.app.state.settings, transport=httpx.MockTransport(gh.handler))
    c.app.state.investigations.start = lambda iid: None  # never clone github.com from tests
    return c


def _gh_token(fb: FakeFirebase, uid: str, email: str) -> dict:
    tok = fb.token(uid, email, firebase={"identities": {"github.com": ["1"]}, "sign_in_provider": "github.com"})
    return {"Authorization": f"Bearer {tok}"}


def test_github_sign_in_connect_list_and_import():
    fb, gh = FakeFirebase(), FakeGitHub()
    c = _firebase_client(fb, gh)
    try:
        alice = _gh_token(fb, "uid-alice-gh", "alice-gh@example.com")
        bob = _gh_token(fb, "uid-bob-gh", "bob-gh@example.com")

        cfg = c.get("/api/auth/config").json()
        assert cfg["providers"] == ["google", "github"] and cfg["github"] == {"enabled": True, "private_repos": False}
        assert c.get("/api/auth/me", headers=alice).json()["provider"] == "github"

        assert c.get("/api/github/connection", headers=alice).json()["connected"] is False
        assert c.post("/api/github/connect", headers=alice, json={"access_token": "gho_wrong00000000000000"}).status_code == 422
        r = c.post("/api/github/connect", headers=alice, json={"access_token": TOKEN_ALICE})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["login"] == "alice-gh" and body["scopes"] == ["repo", "read:user"] and body["private_repos"] is False
        assert TOKEN_ALICE not in r.text
        with session_scope() as s:
            row = s.scalars(select(GitHubConnection).where(GitHubConnection.login == "alice-gh")).one()
            assert TOKEN_ALICE not in row.token_encrypted
        assert c.app.state.github_accounts.token_for(row.user_id) == TOKEN_ALICE

        # private repositories are off by default: only public ones are listed, private import is refused
        repos = c.get("/api/github/repos", headers=alice).json()
        assert [x["full_name"] for x in repos["repos"]] == ["alice-gh/public-app"] and repos["private_repos"] is False
        assert gh.calls[-1][1]["visibility"] == "public"
        assert c.get("/api/github/repos?q=nothing-matches", headers=alice).json()["repos"] == []
        assert c.post("/api/github/import", headers=alice, json={"full_name": "alice-gh/secret-app"}).status_code == 403
        assert c.post("/api/github/import", headers=alice, json={"full_name": "alice-gh/missing"}).status_code == 404
        assert c.post("/api/github/import", headers=alice, json={"full_name": "../../etc"}).status_code == 422

        # import a public repository as an investigation and as a project
        inv = c.post("/api/github/import", headers=alice, json={"full_name": "alice-gh/public-app", "analysis_depth": "quick"})
        assert inv.status_code == 201, inv.text
        inv = inv.json()["investigation"]
        assert inv["repository_url"] == "https://github.com/alice-gh/public-app" and inv["private"] is False
        proj = c.post("/api/github/import", headers=alice, json={"full_name": "alice-gh/public-app", "target": "project"}).json()["project"]
        assert proj["repository_url"] == "https://github.com/alice-gh/public-app" and proj["source"] == "github"

        # bob is not connected and cannot see alice's connection
        assert c.get("/api/github/connection", headers=bob).json()["connected"] is False
        assert c.get("/api/github/repos", headers=bob).status_code == 404
        assert c.post("/api/github/import", headers=bob, json={"full_name": "alice-gh/public-app"}).status_code == 404
        assert c.get("/api/github/connection").status_code == 401

        assert c.delete("/api/github/connection", headers=alice).status_code == 204
        assert c.get("/api/github/connection", headers=alice).json()["connected"] is False
    finally:
        c.__exit__(None, None, None)


def test_private_repositories_are_owner_only():
    fb, gh = FakeFirebase(), FakeGitHub()
    c = _firebase_client(fb, gh, github_private_repos=True)
    try:
        alice = _gh_token(fb, "uid-alice-priv", "alice-priv@example.com")
        bob = _gh_token(fb, "uid-bob-priv", "bob-priv@example.com")
        assert c.post("/api/github/connect", headers=alice, json={"access_token": TOKEN_ALICE}).json()["private_repos"] is True
        assert c.post("/api/github/connect", headers=bob, json={"access_token": TOKEN_BOB}).json()["private_repos"] is False

        repos = c.get("/api/github/repos", headers=alice).json()
        assert {x["full_name"] for x in repos["repos"]} == {"alice-gh/public-app", "alice-gh/secret-app"}
        # bob's token lacks the `repo` scope: private import refused even if GitHub would show it
        assert c.post("/api/github/import", headers=bob, json={"full_name": "alice-gh/secret-app"}).status_code in (403, 404)

        r = c.post("/api/github/import", headers=alice, json={"full_name": "alice-gh/secret-app"})
        assert r.status_code == 201, r.text
        inv = r.json()["investigation"]
        iid = inv["investigation_id"]
        assert inv["private"] is True
        stored = c.app.state.investigations.store.get_investigation(iid)
        assert stored.execution_summary["options"]["github_auth_user"] == stored.owner_id

        assert c.get(f"/api/investigations/{iid}", headers=alice).status_code == 200
        for headers in (bob, {}):
            assert c.get(f"/api/investigations/{iid}", headers=headers).status_code == 404
            assert c.get(f"/api/investigations/{iid}/findings", headers=headers).status_code == 404
            assert c.get(f"/api/investigations/{iid}/report", headers=headers).status_code == 404
            assert iid not in {i["investigation_id"] for i in c.get("/api/investigations", headers=headers).json()}
        assert iid in {i["investigation_id"] for i in c.get("/api/investigations", headers=alice).json()}
        assert c.post(f"/api/investigations/{iid}/chat", headers=bob, json={"question": "is it secure?"}).status_code == 404

        proj = c.post("/api/github/import", headers=alice, json={"full_name": "alice-gh/secret-app", "target": "project"}).json()["project"]
        assert c.app.state.accounts.get_project(stored.owner_id, proj["project_id"]).github_private is True
    finally:
        c.__exit__(None, None, None)

    csp = spa_csp(get_settings().model_copy(update={"firebase_project_id": PROJECT_ID}))
    assert csp.count("img-src") == 1 and "avatars.githubusercontent.com" in csp


def test_clone_credentials_stay_out_of_argv_and_urls(tmp_path):
    env = git_auth_env("ghs_secret123")
    assert env["GIT_CONFIG_COUNT"] == "1" and env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    scheme, value = env["GIT_CONFIG_VALUE_0"].split(" ", 1)[1].split(" ", 1)
    assert scheme == "basic" and base64.b64decode(value).decode() == "x-access-token:ghs_secret123"
    assert env["GIT_TERMINAL_PROMPT"] == "0"

    settings = get_settings().model_copy(update={"database_url": f"sqlite:///{(tmp_path / 'x.db').as_posix()}", "skopeo_secret_key": None})
    box = SecretBox(settings)
    sealed = box.encrypt("hello-token")
    assert "hello-token" not in sealed and box.decrypt(sealed) == "hello-token"
    assert box.decrypt("garbage") is None
    from pydantic import SecretStr

    other = SecretBox(settings.model_copy(update={"skopeo_secret_key": SecretStr("a-different-server-key-1234567890")}))
    assert other.decrypt(sealed) is None


# ----------------------------------------------------------------------------- chat
def test_keyword_routing_picks_the_responsible_agent():
    cases = {
        "Is there any SQL injection or hardcoded secret?": "security_agent",
        "Which dependencies are outdated or have a CVE?": "dependency_agent",
        "Is the license compatible with GPL code?": "license_agent",
        "Which findings were rejected as false positives?": "verification_agent",
        "Do these issues compound each other, is there a root cause?": "correlation_agent",
        "Are there flaky tests or missing coverage?": "test_reliability_agent",
        "Hello there": "orchestrator",
    }
    for question, agent in cases.items():
        assert keyword_route(question)[0] == agent, question


@pytest.fixture(scope="module")
def demo_client():
    with _client() as c:
        svc = c.app.state.investigations
        iid = svc.create_demo(DemoInvestigationCreate(fault_injection=False, step_delay_ms=0))
        svc.run_sync(iid)
        yield c, iid


@pytest.mark.slow
def test_chat_answers_from_the_designated_agent(demo_client):
    c, iid = demo_client
    assert c.get(f"/api/investigations/{iid}/chat").json()["messages"] == []
    agents = {a["name"] for a in c.get("/api/chat/agents").json()}
    assert {"security_agent", "verification_agent", "orchestrator"} <= agents

    r = c.post(f"/api/investigations/{iid}/chat", json={"question": "Are there SQL injection or hardcoded secret problems?"})
    assert r.status_code == 200, r.text
    ans = r.json()["answer"]
    assert ans["agent"] == "security_agent" and ans["agent_display_name"] == "Security Agent"
    assert ans["decided_by"] == "policy" and ans["routed_by"] == "policy"
    assert "Security Agent" in ans["content"] and ans["citations"]
    findings = {f["finding_id"]: f for f in c.get(f"/api/investigations/{iid}/findings").json()}
    assert all(cit["finding_id"] in findings for cit in ans["citations"])
    assert any(findings[cit["finding_id"]]["category"] == "security" for cit in ans["citations"])
    assert len(ans["follow_ups"]) == 3

    v = c.post(f"/api/investigations/{iid}/chat", json={"question": "Which findings were rejected as false positives?"}).json()["answer"]
    assert v["agent"] == "verification_agent" and "rejected" in v["content"]

    o = c.post(f"/api/investigations/{iid}/chat", json={"question": "Give me an overview"}).json()["answer"]
    assert o["agent"] == "orchestrator" and "overall risk" in o["content"]

    direct = c.post(f"/api/investigations/{iid}/chat", json={"question": "anything?", "agent": "license_agent"}).json()["answer"]
    assert direct["agent"] == "license_agent" and direct["routed_by"] == "user"
    assert c.post(f"/api/investigations/{iid}/chat", json={"question": "x?", "agent": "nobody"}).status_code == 422
    assert c.post(f"/api/investigations/{iid}/chat", json={"question": "q" * 2001}).status_code == 422
    assert c.post("/api/investigations/does-not-exist/chat", json={"question": "hello"}).status_code == 404

    msgs = c.get(f"/api/investigations/{iid}/chat").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "agent"] * 4
    assert c.delete(f"/api/investigations/{iid}/chat").status_code == 204
    assert c.get(f"/api/investigations/{iid}/chat").json()["messages"] == []


class ScriptedLLM(LLMProvider):
    name = "scripted"

    def __init__(self, route: str, cite: list[str]) -> None:
        super().__init__(max_calls=50)
        self.route, self.cite = route, cite
        self.requests = []

    def _complete(self, request, schema):
        self.requests.append(request)
        if schema is RouteDecision:
            return RouteDecision(agent=self.route, reason="scripted"), 10, 5, "scripted-model"
        return ChatAnswer(answer="Grounded answer.", cited_finding_ids=self.cite, follow_up_questions=["Next?"]), 100, 20, "scripted-model"


@pytest.mark.slow
def test_live_chat_validates_routing_and_citations(demo_client):
    c, iid = demo_client
    settings = c.app.state.settings
    findings = c.get(f"/api/investigations/{iid}/findings").json()
    real = next(f["finding_id"] for f in findings if f["category"] == "dependency")

    llm = ScriptedLLM("dependency_agent", [real, "invented-id"])
    out = ChatService(settings, provider=llm).ask(iid, "user-x", "what should I upgrade?")["answer"]
    assert out["agent"] == "dependency_agent" and out["routed_by"] == "llm:scripted-model"
    assert out["decided_by"] == "llm:scripted-model" and out["content"] == "Grounded answer."
    assert [x["finding_id"] for x in out["citations"]] == [real]
    assert out["follow_ups"] == ["Next?"]
    answer_req = llm.requests[-1]
    assert answer_req.tier == "reasoning" and "Dependency Health Agent" in answer_req.role_instructions
    assert all(
        f["agent"] == "dependency_agent" or f["category"] == "dependency" for f in answer_req.structured_input["records"]["findings"]
    )
    assert answer_req.untrusted and json.dumps(answer_req.untrusted)  # evidence/code travels as untrusted data

    # a router that names an agent that does not exist falls back to keyword routing
    bad = ScriptedLLM("root_shell_agent", [])
    out = ChatService(settings, provider=bad).ask(iid, "user-x", "Is the license GPL compatible?")["answer"]
    assert out["agent"] == "license_agent" and out["routed_by"] == "policy-fallback"
