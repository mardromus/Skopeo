"""REST API."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app import __version__
from app.agents.registry import all_agent_descriptions
from app.schemas import EvidenceOut, FindingOut
from app.schemas.investigation import (
    ActionProposalOut,
    AgentRunOut,
    ApproveActionRequest,
    DemoInvestigationCreate,
    ExecutionEventOut,
    InvestigationCreate,
    InvestigationDetail,
    InvestigationRequestOut,
    InvestigationSummary,
    RecommendationOut,
    RiskOut,
)
from app.services.actions import ActionError, decide_action
from app.services.investigation_service import InvestigationService
from app.services.report import build_markdown, build_report

router = APIRouter(prefix="/api")


def _svc(request: Request) -> InvestigationService:
    return request.app.state.investigations


def _summary(inv) -> dict[str, Any]:
    duration = None
    if inv.started_at and inv.completed_at:
        duration = round((inv.completed_at - inv.started_at).total_seconds(), 2)
    return {
        "investigation_id": inv.id,
        "repository": inv.repository_name,
        "repository_url": inv.repository_url,
        "branch": inv.branch,
        "source": inv.source,
        "analysis_depth": inv.analysis_depth,
        "status": inv.status,
        "overall_risk": {"score": inv.overall_risk_score, "level": inv.overall_risk_level} if inv.overall_risk_score is not None else None,
        "created_at": inv.created_at,
        "started_at": inv.started_at,
        "completed_at": inv.completed_at,
        "duration_seconds": duration,
    }


def _get(request: Request, investigation_id: str):
    inv = _svc(request).store.get_investigation(investigation_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    return inv


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    s = request.app.state.settings
    return {
        "status": "ok",
        "version": __version__,
        "mode": s.skopeo_mode,
        "llm_provider": "mock" if s.is_mock else s.llm_provider,
        "demo_mode": s.skopeo_demo_mode,
        "dry_run": s.dry_run,
        "offline": s.skopeo_offline,
        "sandbox_execution": s.skopeo_sandbox_execution,
        "github_token_configured": s.github_token is not None,
    }


@router.get("/agents")
def agents() -> list[dict[str, str]]:
    return all_agent_descriptions()


@router.post("/investigations", status_code=202, response_model=InvestigationSummary)
def create_investigation(body: InvestigationCreate, request: Request) -> dict[str, Any]:
    svc = _svc(request)
    iid = svc.create(body)
    svc.start(iid)
    return _summary(svc.store.get_investigation(iid))


@router.post("/demo/investigations", status_code=202, response_model=InvestigationSummary)
def create_demo_investigation(request: Request, body: DemoInvestigationCreate | None = None) -> dict[str, Any]:
    if not request.app.state.settings.skopeo_demo_mode:
        raise HTTPException(status_code=403, detail="demo mode disabled (SKOPEO_DEMO_MODE=false)")
    svc = _svc(request)
    iid = svc.create_demo(body or DemoInvestigationCreate())
    svc.start(iid)
    return _summary(svc.store.get_investigation(iid))


@router.get("/investigations", response_model=list[InvestigationSummary])
def list_investigations(request: Request, limit: int = Query(25, ge=1, le=100)) -> list[dict[str, Any]]:
    return [_summary(i) for i in _svc(request).store.list_investigations(limit)]


@router.get("/investigations/{investigation_id}", response_model=InvestigationDetail)
def get_investigation(investigation_id: str, request: Request) -> dict[str, Any]:
    inv = _get(request, investigation_id)
    return _summary(inv) | {
        "commit_sha": inv.commit_sha,
        "repo_profile": inv.repo_profile,
        "plan": inv.plan,
        "coverage": inv.coverage,
        "execution_summary": inv.execution_summary,
        "enable_github_actions": inv.enable_github_actions,
        "error": inv.error,
        "counts": _svc(request).store.counts(investigation_id),
    }


@router.get("/investigations/{investigation_id}/agents", response_model=list[AgentRunOut])
def get_agents(investigation_id: str, request: Request):
    _get(request, investigation_id)
    return _svc(request).store.list_agent_runs(investigation_id)


@router.get("/investigations/{investigation_id}/findings", response_model=list[FindingOut])
def get_findings(
    investigation_id: str,
    request: Request,
    severity: str | None = None,
    category: str | None = None,
    status: str | None = None,
    agent: str | None = None,
    min_confidence: float | None = Query(None, ge=0, le=1),
    file: str | None = None,
):
    _get(request, investigation_id)
    return _svc(request).store.list_findings(
        investigation_id, severity=severity, category=category, status=status, agent=agent, min_confidence=min_confidence, file=file
    )


@router.get("/investigations/{investigation_id}/evidence", response_model=list[EvidenceOut])
def get_evidence(investigation_id: str, request: Request, finding_id: str | None = None):
    _get(request, investigation_id)
    return _svc(request).store.list_evidence(investigation_id, finding_id)


@router.get("/investigations/{investigation_id}/correlations")
def get_correlations(investigation_id: str, request: Request):
    _get(request, investigation_id)
    return _svc(request).store.list_correlations(investigation_id)


@router.get("/investigations/{investigation_id}/verifications")
def get_verifications(investigation_id: str, request: Request):
    _get(request, investigation_id)
    return _svc(request).store.list_verifications(investigation_id)


@router.get("/investigations/{investigation_id}/risks", response_model=list[RiskOut])
def get_risks(investigation_id: str, request: Request):
    _get(request, investigation_id)
    return _svc(request).store.list_risks(investigation_id)


@router.get("/investigations/{investigation_id}/recommendations", response_model=list[RecommendationOut])
def get_recommendations(investigation_id: str, request: Request):
    _get(request, investigation_id)
    return _svc(request).store.list_recommendations(investigation_id)


@router.get("/investigations/{investigation_id}/actions", response_model=list[ActionProposalOut])
def get_actions(investigation_id: str, request: Request):
    _get(request, investigation_id)
    return _svc(request).store.list_actions(investigation_id)


@router.get("/investigations/{investigation_id}/requests", response_model=list[InvestigationRequestOut])
def get_requests(investigation_id: str, request: Request):
    _get(request, investigation_id)
    return _svc(request).store.list_requests(investigation_id)


@router.get("/investigations/{investigation_id}/events", response_model=list[ExecutionEventOut])
def get_events(investigation_id: str, request: Request, after_seq: int = Query(0, ge=0), limit: int | None = Query(None, ge=1, le=5000)):
    _get(request, investigation_id)
    return _svc(request).store.list_events(investigation_id, after_seq=after_seq, limit=limit)


@router.post("/investigations/{investigation_id}/cancel")
def cancel(investigation_id: str, request: Request) -> dict[str, Any]:
    _get(request, investigation_id)
    accepted = _svc(request).cancel(investigation_id)
    return {"investigation_id": investigation_id, "cancel_requested": accepted}


@router.post("/investigations/{investigation_id}/approve-action", response_model=ActionProposalOut)
def approve_action(investigation_id: str, body: ApproveActionRequest, request: Request):
    _get(request, investigation_id)
    svc = _svc(request)
    try:
        return decide_action(svc.store, svc.events, request.app.state.settings, investigation_id, body)
    except ActionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/investigations/{investigation_id}/report")
def report(investigation_id: str, request: Request, format: Literal["json", "markdown"] = "json"):
    _get(request, investigation_id)
    store = _svc(request).store
    if format == "markdown":
        return PlainTextResponse(
            build_markdown(store, investigation_id),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="skopeo-{investigation_id[:8]}.md"'},
        )
    return build_report(store, investigation_id)
