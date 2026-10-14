"""Connected GitHub accounts: verify and store a user's token (encrypted), list their repositories.

Tokens arrive from "Sign in with GitHub" (the OAuth access token Firebase hands the browser) or
from a personal access token the user pastes. They are checked against GitHub before being
stored, encrypted at rest with :class:`SecretBox`, never returned by the API, and used only for
the owner's own requests: listing repositories and cloning the private ones they import.
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import delete, select

from app.config import Settings
from app.database import session_scope
from app.models import GitHubConnection, User, utcnow
from app.security.redaction import redact, register_secrets
from app.security.secretbox import SecretBox

_TIMEOUT = 15.0


class GitHubAccountError(ValueError):
    pass


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Skopeo",
        "Authorization": f"Bearer {token}",
    }


class GitHubAccounts:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self.box = SecretBox(settings)
        self._transport = transport

    # ---------------------------------------------------------------- http
    def _get(self, token: str, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        url = f"{self.settings.github_api_url.rstrip('/')}{path}"
        try:
            with httpx.Client(timeout=_TIMEOUT, transport=self._transport, follow_redirects=False) as client:
                return client.get(url, headers=_headers(token), params=params)
        except httpx.HTTPError as exc:
            raise GitHubAccountError(f"GitHub is unreachable: {type(exc).__name__}") from exc

    # ---------------------------------------------------------- connection
    def connect(self, user: User, token: str, source: str = "oauth") -> dict[str, Any]:
        token = (token or "").strip()
        if not token or len(token) > 400 or any(c.isspace() for c in token):
            raise GitHubAccountError("that does not look like a GitHub token")
        resp = self._get(token, "/user")
        if resp.status_code == 401:
            raise GitHubAccountError("GitHub rejected the token (expired or revoked)")
        if resp.status_code != 200:
            raise GitHubAccountError(f"GitHub answered {resp.status_code}: {redact(resp.text)[:200]}")
        info = resp.json()
        scopes = [s.strip() for s in resp.headers.get("x-oauth-scopes", "").split(",") if s.strip()]
        register_secrets([token])
        with session_scope(write=True) as s:
            row = s.scalars(select(GitHubConnection).where(GitHubConnection.user_id == user.id)).first()
            fields = {
                "github_id": int(info["id"]),
                "login": str(info["login"])[:100],
                "avatar_url": info.get("avatar_url"),
                "token_encrypted": self.box.encrypt(token),
                "scopes": scopes,
                "source": source if source in ("oauth", "pat") else "oauth",
                "updated_at": utcnow(),
            }
            if row is None:
                row = GitHubConnection(user_id=user.id, **fields)
                s.add(row)
            else:
                for k, v in fields.items():
                    setattr(row, k, v)
            s.flush()
            return self._out(row)

    def connection(self, user_id: str) -> GitHubConnection | None:
        with session_scope() as s:
            return s.scalars(select(GitHubConnection).where(GitHubConnection.user_id == user_id)).first()

    def connection_out(self, user_id: str) -> dict[str, Any] | None:
        row = self.connection(user_id)
        return self._out(row) if row else None

    def disconnect(self, user_id: str) -> bool:
        with session_scope(write=True) as s:
            return bool(s.execute(delete(GitHubConnection).where(GitHubConnection.user_id == user_id)).rowcount)

    def token_for(self, user_id: str | None) -> str | None:
        if not user_id:
            return None
        row = self.connection(user_id)
        token = self.box.decrypt(row.token_encrypted) if row else None
        if token:
            register_secrets([token])
        return token

    def private_access(self, row: GitHubConnection) -> bool:
        if not self.settings.github_private_repos:
            return False
        # classic OAuth / PAT scopes; fine-grained tokens report no scopes and are judged per repository
        return "repo" in (row.scopes or []) or not row.scopes

    def _out(self, row: GitHubConnection) -> dict[str, Any]:
        return {
            "login": row.login,
            "avatar_url": row.avatar_url,
            "scopes": list(row.scopes or []),
            "source": row.source,
            "private_repos": self.private_access(row),
            "connected_at": row.updated_at or row.created_at,
        }

    # ---------------------------------------------------------------- repos
    def list_repos(self, user_id: str, query: str = "", page: int = 1) -> dict[str, Any]:
        row = self.connection(user_id)
        if row is None:
            raise LookupError("GitHub is not connected")
        token = self.box.decrypt(row.token_encrypted)
        if not token:
            raise GitHubAccountError("the stored GitHub token can no longer be read; connect GitHub again")
        private = self.private_access(row)
        params = {
            "per_page": 100,
            "page": max(1, min(page, 20)),
            "sort": "pushed",
            "affiliation": "owner,collaborator,organization_member",
            "visibility": "all" if private else "public",
        }
        resp = self._get(token, "/user/repos", params)
        if resp.status_code == 401:
            raise GitHubAccountError("GitHub rejected the stored token; connect GitHub again")
        if resp.status_code != 200:
            raise GitHubAccountError(f"GitHub answered {resp.status_code}")
        q = (query or "").strip().lower()
        repos = []
        for r in resp.json():
            if r.get("private") and not private:
                continue
            if q and q not in r["full_name"].lower() and q not in (r.get("description") or "").lower():
                continue
            repos.append(
                {
                    "full_name": r["full_name"],
                    "html_url": r["html_url"],
                    "description": (r.get("description") or "")[:300],
                    "private": bool(r.get("private")),
                    "fork": bool(r.get("fork")),
                    "archived": bool(r.get("archived")),
                    "default_branch": r.get("default_branch") or "main",
                    "language": r.get("language"),
                    "stars": r.get("stargazers_count", 0),
                    "pushed_at": r.get("pushed_at"),
                }
            )
        return {"repos": repos, "page": params["page"], "has_more": len(resp.json()) == 100, "private_repos": private}

    def repo_info(self, user_id: str, full_name: str) -> dict[str, Any]:
        token = self.token_for(user_id)
        if not token:
            raise LookupError("GitHub is not connected")
        resp = self._get(token, f"/repos/{full_name}")
        if resp.status_code == 404:
            raise LookupError("repository not found or not accessible with your GitHub account")
        if resp.status_code != 200:
            raise GitHubAccountError(f"GitHub answered {resp.status_code}")
        r = resp.json()
        return {"full_name": r["full_name"], "private": bool(r.get("private")), "default_branch": r.get("default_branch") or "main"}


def clone_token(settings: Settings, user_id: str | None) -> str | None:
    """The token to clone a private repository on behalf of ``user_id`` (None when not connected)."""
    if not user_id:
        return None
    return GitHubAccounts(settings).token_for(user_id)
