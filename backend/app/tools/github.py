"""GitHub REST client: metadata reads plus approval-gated issue / pull-request creation."""

from __future__ import annotations

import base64
from typing import Any

import httpx

from app.config import Settings
from app.observability import get_logger

log = get_logger("tools.github")


class GitHubError(RuntimeError):
    pass


class GitHubRateLimited(GitHubError):
    def __init__(self, reset: str | None) -> None:
        super().__init__(f"GitHub API rate limit exhausted (resets at {reset})")
        self.reset = reset


class GitHubNotFound(GitHubError):
    pass


class GitHubClient:
    def __init__(self, settings: Settings, max_calls: int = 30, offline: bool | None = None) -> None:
        self.settings = settings
        self.offline = settings.skopeo_offline if offline is None else offline
        self.base = settings.github_api_url.rstrip("/")
        self.max_calls = max_calls
        self.calls = 0
        self.authenticated = settings.github_token is not None and bool(settings.github_token.get_secret_value())

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "skopeo"}
        if self.authenticated:
            headers["Authorization"] = f"Bearer {self.settings.github_token.get_secret_value()}"  # type: ignore[union-attr]
        return headers

    def _request(self, method: str, path: str, *, params: dict | None = None, json: dict | None = None) -> Any:
        if self.offline:
            raise GitHubError("offline mode: GitHub API disabled")
        if self.calls >= self.max_calls:
            raise GitHubError("GitHub call budget exhausted for this investigation")
        self.calls += 1
        try:
            with httpx.Client(timeout=20) as client:
                resp = client.request(method, f"{self.base}{path}", params=params, json=json, headers=self._headers())
        except httpx.HTTPError as exc:
            raise GitHubError(f"GitHub API unreachable: {type(exc).__name__}") from exc
        log.info("github api", extra={"event_type": "github_api", "data": {"method": method, "path": path, "status": resp.status_code}})
        if resp.status_code in (403, 429) and resp.headers.get("X-RateLimit-Remaining") == "0":
            raise GitHubRateLimited(resp.headers.get("X-RateLimit-Reset"))
        if resp.status_code == 404:
            raise GitHubNotFound(path)
        if resp.status_code >= 400:
            raise GitHubError(f"GitHub API {resp.status_code} for {path}")
        return resp.json() if resp.content else None

    # ---------------------------------------------------------------- reads
    def get_repo(self, full_name: str) -> dict[str, Any]:
        return self._request("GET", f"/repos/{full_name}")

    def list_releases(self, full_name: str, per_page: int = 20) -> list[dict[str, Any]]:
        return self._request("GET", f"/repos/{full_name}/releases", params={"per_page": per_page}) or []

    def list_pulls(self, full_name: str, per_page: int = 30) -> list[dict[str, Any]]:
        return (
            self._request(
                "GET", f"/repos/{full_name}/pulls", params={"state": "all", "per_page": per_page, "sort": "updated", "direction": "desc"}
            )
            or []
        )

    def list_issues(self, full_name: str, per_page: int = 30) -> list[dict[str, Any]]:
        items = (
            self._request(
                "GET", f"/repos/{full_name}/issues", params={"state": "all", "per_page": per_page, "sort": "updated", "direction": "desc"}
            )
            or []
        )
        return [i for i in items if "pull_request" not in i]

    def list_branches(self, full_name: str, per_page: int = 100) -> list[dict[str, Any]]:
        return self._request("GET", f"/repos/{full_name}/branches", params={"per_page": per_page}) or []

    def list_contributors(self, full_name: str, per_page: int = 30) -> list[dict[str, Any]]:
        return self._request("GET", f"/repos/{full_name}/contributors", params={"per_page": per_page}) or []

    def dependabot_alerts(self, full_name: str) -> list[dict[str, Any]]:
        if not self.authenticated:
            raise GitHubError("Dependabot alerts require GITHUB_TOKEN with security_events scope")
        return self._request("GET", f"/repos/{full_name}/dependabot/alerts", params={"state": "open", "per_page": 50}) or []

    # ------------------------------------------------- writes (approval-gated)
    def create_issue(self, full_name: str, title: str, body: str, labels: list[str] | None = None) -> dict[str, Any]:
        if not self.authenticated:
            raise GitHubError("creating issues requires GITHUB_TOKEN")
        return self._request("POST", f"/repos/{full_name}/issues", json={"title": title, "body": body, "labels": labels or []})

    def create_pull_request(
        self, full_name: str, base: str, head_branch: str, title: str, body: str, files: dict[str, str]
    ) -> dict[str, Any]:
        """Create a *draft* PR from a new branch. Never merges, never force-pushes, never deletes."""
        if not self.authenticated:
            raise GitHubError("creating pull requests requires GITHUB_TOKEN")
        base_ref = self._request("GET", f"/repos/{full_name}/git/ref/heads/{base}")
        sha = base_ref["object"]["sha"]
        self._request("POST", f"/repos/{full_name}/git/refs", json={"ref": f"refs/heads/{head_branch}", "sha": sha})
        for path, content in files.items():
            existing = None
            try:
                existing = self._request("GET", f"/repos/{full_name}/contents/{path}", params={"ref": head_branch})
            except GitHubNotFound:
                existing = None
            payload = {
                "message": f"skopeo: {title}",
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "branch": head_branch,
            }
            if existing and isinstance(existing, dict) and existing.get("sha"):
                payload["sha"] = existing["sha"]
            self._request("PUT", f"/repos/{full_name}/contents/{path}", json=payload)
        return self._request(
            "POST",
            f"/repos/{full_name}/pulls",
            json={"title": title, "body": body, "head": head_branch, "base": base, "draft": True},
        )
