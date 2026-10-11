"""Projects (your software, as context) and watches on the open-source repositories it depends on."""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.api.access import account_rate_limit
from app.api.auth import require_user
from app.models import Project, User
from app.schemas.accounts import ProjectCreate, ProjectFileIn, ProjectFilesPut, ProjectUpdate, WatchCreate, WatchUpdate
from app.security.paths import PathTraversalError
from app.security.url_validation import InvalidBranchName, InvalidRepositoryURL, validate_branch, validate_repository_url
from app.services.account_store import AccountStore
from app.watch import WatchError, WatchService, report_out, report_summary, watch_out

router = APIRouter(prefix="/api")

MAX_PROJECTS_PER_USER = 30


def _store(request: Request) -> AccountStore:
    return request.app.state.accounts


def _watches(request: Request) -> WatchService:
    return request.app.state.watches


def _project(request: Request, user: User, project_id: str) -> Project:
    p = _store(request).get_project(user.id, project_id)
    if p is None:
        raise HTTPException(status_code=404, detail="project not found")
    return p


def project_out(request: Request, p: Project, with_watches: bool = True) -> dict[str, Any]:
    store = _store(request)
    count, size = store.project_file_stats(p.id)
    out: dict[str, Any] = {
        "project_id": p.id,
        "name": p.name,
        "notes": p.notes,
        "source": p.source,
        "repository_url": p.repository_url,
        "branch": p.branch,
        "file_count": count,
        "total_bytes": size,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }
    if with_watches:
        out["watches"] = [watch_out(w, store.latest_report(w.id)) for w in store.list_watches(p.user_id, p.id)]
    return out


def clean_path(raw: str) -> str:
    path = raw.replace("\\", "/").strip()
    parts = [s for s in path.split("/") if s not in ("", ".")]
    if not parts or path.startswith("/") or ":" in parts[0] or "\x00" in path or ".." in parts:
        raise PathTraversalError(f"invalid file path: {raw[:80]!r}")
    return "/".join(parts)


def _file_rows(request: Request, files: list[ProjectFileIn], keep: dict[str, int] | None = None) -> list[dict[str, Any]]:
    """Validate uploaded files; ``keep`` holds files already stored ({path: size}) that stay unless overwritten."""
    s = request.app.state.settings
    rows: dict[str, dict[str, Any]] = {}
    for f in files:
        try:
            path = clean_path(f.path)
        except PathTraversalError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        data = f.content.encode("utf-8", errors="replace")
        rows[path] = {"path": path, "content": f.content, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    kept = {k: v for k, v in (keep or {}).items() if k not in rows}
    if len(kept) + len(rows) > s.project_max_files:
        raise HTTPException(status_code=413, detail=f"a project can hold at most {s.project_max_files} files")
    if sum(kept.values()) + sum(r["size"] for r in rows.values()) > s.project_max_total_bytes:
        raise HTTPException(status_code=413, detail=f"a project can hold at most {s.project_max_total_bytes // 1_000_000} MB of files")
    return list(rows.values())


def _repo_fields(source: str, url: str | None, branch: str | None) -> dict[str, Any]:
    if source != "github":
        return {"repository_url": None}
    if not url:
        raise HTTPException(status_code=422, detail="a GitHub project needs repository_url")
    try:
        return {"repository_url": validate_repository_url(url).canonical_url, "branch": validate_branch(branch or "main")}
    except (InvalidRepositoryURL, InvalidBranchName) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# -------------------------------------------------------------------- projects
@router.get("/projects")
def list_projects(request: Request, user: User = Depends(require_user)) -> list[dict[str, Any]]:
    return [project_out(request, p) for p in _store(request).list_projects(user.id)]


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    store = _store(request)
    if len(store.list_projects(user.id)) >= MAX_PROJECTS_PER_USER:
        raise HTTPException(status_code=422, detail=f"you can have at most {MAX_PROJECTS_PER_USER} projects")
    repo = _repo_fields(body.source, body.repository_url, body.branch)
    rows = _file_rows(request, body.files)
    p = store.add_project(
        user.id, name=body.name.strip(), notes=body.notes, source=body.source, branch=repo.pop("branch", body.branch), **repo
    )
    if rows:
        store.replace_project_files(p.id, rows)
    return project_out(request, p)


@router.get("/projects/{project_id}")
def get_project(project_id: str, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    return project_out(request, _project(request, user, project_id))


@router.patch("/projects/{project_id}")
def update_project(project_id: str, body: ProjectUpdate, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    p = _project(request, user, project_id)
    fields: dict[str, Any] = {}
    if body.name is not None:
        fields["name"] = body.name.strip()
    if body.notes is not None:
        fields["notes"] = body.notes
    if p.source == "github" and (body.repository_url is not None or body.branch is not None):
        fields |= _repo_fields("github", body.repository_url or p.repository_url, body.branch or p.branch)
    elif body.branch is not None:
        fields["branch"] = body.branch
    p = _store(request).update_project(p.id, **fields) if fields else p
    return project_out(request, p)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, request: Request, user: User = Depends(require_user)) -> Response:
    if not _store(request).delete_project(user.id, project_id):
        raise HTTPException(status_code=404, detail="project not found")
    return Response(status_code=204)


@router.get("/projects/{project_id}/files")
def list_files(project_id: str, request: Request, user: User = Depends(require_user)) -> list[dict[str, Any]]:
    p = _project(request, user, project_id)
    return [
        {"path": f.path, "size": f.size, "sha256": f.sha256, "created_at": f.created_at} for f in _store(request).list_project_files(p.id)
    ]


@router.put("/projects/{project_id}/files")
def put_files(project_id: str, body: ProjectFilesPut, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    p = _project(request, user, project_id)
    store = _store(request)
    if body.replace:
        store.replace_project_files(p.id, _file_rows(request, body.files))
    else:
        existing = {f.path: f.size for f in store.list_project_files(p.id)}
        store.upsert_project_files(p.id, _file_rows(request, body.files, existing))
    store.update_project(p.id, name=p.name)  # bump updated_at
    return project_out(request, store.get_project(user.id, p.id))  # type: ignore[arg-type]


@router.delete("/projects/{project_id}/files")
def delete_file(
    project_id: str, request: Request, path: str = Query(..., max_length=512), user: User = Depends(require_user)
) -> dict[str, Any]:
    p = _project(request, user, project_id)
    if not _store(request).delete_project_file(p.id, path):
        raise HTTPException(status_code=404, detail="file not found")
    return project_out(request, p)


# --------------------------------------------------------------------- watches
@router.get("/watches")
def list_watches(request: Request, user: User = Depends(require_user)) -> list[dict[str, Any]]:
    store = _store(request)
    return [watch_out(w, store.latest_report(w.id)) for w in store.list_watches(user.id)]


@router.post("/projects/{project_id}/watches", status_code=201)
def create_watch(project_id: str, body: WatchCreate, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    _project(request, user, project_id)
    svc = _watches(request)
    try:
        w = svc.create_watch(
            user,
            project_id,
            upstream_url=body.upstream_url,
            branch=body.branch,
            package_name=body.package_name,
            import_names=body.import_names,
            ecosystem=body.ecosystem,
            frequency=body.frequency,
        )
    except WatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body.check_now:
        svc.submit(w.id, trigger="manual")
    return watch_out(_store(request).get_watch(user.id, w.id))  # type: ignore[arg-type]


@router.get("/watches/{watch_id}")
def get_watch(watch_id: str, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    store = _store(request)
    w = store.get_watch(user.id, watch_id)
    if w is None:
        raise HTTPException(status_code=404, detail="watch not found")
    return watch_out(w, store.latest_report(w.id))


@router.patch("/watches/{watch_id}")
def update_watch(watch_id: str, body: WatchUpdate, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    try:
        w = _watches(request).update_watch(user, watch_id, **body.model_dump(exclude_unset=True))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="watch not found") from exc
    except WatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return watch_out(w, _store(request).latest_report(w.id))


@router.delete("/watches/{watch_id}", status_code=204)
def delete_watch(watch_id: str, request: Request, user: User = Depends(require_user)) -> Response:
    if not _store(request).delete_watch(user.id, watch_id):
        raise HTTPException(status_code=404, detail="watch not found")
    return Response(status_code=204)


@router.post("/watches/{watch_id}/check", status_code=202, dependencies=[Depends(account_rate_limit)])
def check_now(watch_id: str, request: Request, from_pinned: bool = Query(False), user: User = Depends(require_user)) -> dict[str, Any]:
    """Queue a check now. ``from_pinned=true`` compares the version your manifest pins with the latest upstream."""
    store = _store(request)
    w = store.get_watch(user.id, watch_id)
    if w is None:
        raise HTTPException(status_code=404, detail="watch not found")
    queued = _watches(request).submit(w.id, trigger="manual", from_pinned=from_pinned)
    return {"queued": queued, "watch": watch_out(store.get_watch(user.id, w.id), store.latest_report(w.id))}  # type: ignore[arg-type]


@router.get("/watches/{watch_id}/reports")
def list_reports(
    watch_id: str, request: Request, user: User = Depends(require_user), limit: int = Query(30, ge=1, le=100)
) -> list[dict[str, Any]]:
    store = _store(request)
    if store.get_watch(user.id, watch_id) is None:
        raise HTTPException(status_code=404, detail="watch not found")
    return [report_summary(r) for r in store.list_reports(user.id, watch_id, limit)]


@router.get("/watch-reports/{report_id}")
def get_report(report_id: str, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    r = _store(request).get_report(user.id, report_id)
    if r is None:
        raise HTTPException(status_code=404, detail="report not found")
    return report_out(r)
