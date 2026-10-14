"""Connected GitHub account: connect, list repositories, import one as an investigation or a project."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.access import account_rate_limit, rate_limit, require_login_for_scans, require_write_access
from app.api.auth import require_user
from app.api.project_routes import project_out
from app.api.routes import _summary, apply_user_defaults
from app.models import User
from app.schemas.investigation import InvestigationCreate
from app.security.url_validation import InvalidBranchName, InvalidRepositoryURL, validate_branch, validate_repository_url
from app.services.github_accounts import GitHubAccountError, GitHubAccounts

router = APIRouter(prefix="/api/github")


class ConnectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_token: str = Field(min_length=10, max_length=400)
    source: Literal["oauth", "pat"] = "oauth"


class ImportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str = Field(min_length=3, max_length=140)
    target: Literal["investigation", "project"] = "investigation"
    branch: str | None = Field(default=None, max_length=200)
    analysis_depth: Literal["quick", "standard", "deep"] = "standard"
    project_name: str | None = Field(default=None, max_length=120)
    notes: str = Field(default="", max_length=8000)
    enable_github_actions: bool = False
    dry_run: bool | None = None
    sandbox_execution: bool | None = None


def _accounts(request: Request) -> GitHubAccounts:
    return request.app.state.github_accounts


def _err(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc).strip("'"))
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/connection")
def connection(request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    out = _accounts(request).connection_out(user.id)
    return {"connected": out is not None, **(out or {}), "private_repos_enabled": request.app.state.settings.github_private_repos}


@router.post("/connect", dependencies=[Depends(account_rate_limit)])
def connect(body: ConnectBody, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    try:
        return {"connected": True, **_accounts(request).connect(user, body.access_token, body.source)}
    except GitHubAccountError as exc:
        raise _err(exc) from exc


@router.delete("/connection", status_code=204)
def disconnect(request: Request, user: User = Depends(require_user)) -> Response:
    _accounts(request).disconnect(user.id)
    return Response(status_code=204)


@router.get("/repos")
def repos(request: Request, user: User = Depends(require_user), q: str = Query("", max_length=100), page: int = Query(1, ge=1, le=20)):
    try:
        return _accounts(request).list_repos(user.id, q, page)
    except (GitHubAccountError, LookupError) as exc:
        raise _err(exc) from exc


@router.post(
    "/import",
    status_code=201,
    dependencies=[Depends(require_write_access), Depends(require_login_for_scans), Depends(rate_limit)],
)
def import_repo(body: ImportBody, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    try:
        ref = validate_repository_url(f"https://github.com/{body.full_name.strip()}")
        info = _accounts(request).repo_info(user.id, ref.full_name)
        branch = validate_branch(body.branch or info["default_branch"])
    except (InvalidRepositoryURL, InvalidBranchName, GitHubAccountError, LookupError) as exc:
        raise _err(exc) from exc
    accounts = _accounts(request)
    if info["private"]:
        row = accounts.connection(user.id)
        if row is None or not accounts.private_access(row):
            raise HTTPException(
                status_code=403,
                detail="Private repositories are not enabled on this server (GITHUB_PRIVATE_REPOS) or your GitHub sign-in lacks the `repo` permission.",
            )
    if body.target == "project":
        store = request.app.state.accounts
        p = store.add_project(
            user.id,
            name=(body.project_name or ref.name).strip()[:120],
            notes=body.notes,
            source="github",
            repository_url=ref.canonical_url,
            branch=branch,
            github_private=info["private"],
        )
        return {"target": "project", "project": project_out(request, p)}

    svc = request.app.state.investigations
    try:
        iid = svc.create(
            apply_user_defaults(
                InvestigationCreate(
                    repository_url=ref.canonical_url,
                    branch=branch,
                    analysis_depth=body.analysis_depth,
                    enable_github_actions=body.enable_github_actions,
                    dry_run=body.dry_run,
                    sandbox_execution=body.sandbox_execution,
                ),
                user,
            ),
            owner_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if info["private"]:
        inv = svc.store.get_investigation(iid)
        summary = dict(inv.execution_summary or {})
        summary["options"] = {**(summary.get("options") or {}), "github_auth_user": user.id, "private": True}
        svc.store.update_investigation(iid, execution_summary=summary)
    svc.start(iid)
    return {"target": "investigation", "investigation": _summary(svc.store.get_investigation(iid))}
