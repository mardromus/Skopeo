"""API input/output schemas for investigations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import InvestigationStatus
from app.security.url_validation import validate_branch, validate_repository_url


class InvestigationCreate(BaseModel):
    """Primary input schema."""

    model_config = ConfigDict(extra="forbid")

    repository_url: str = Field(examples=["https://github.com/owner/repository"])
    branch: str = Field(default="main", examples=["main"])
    analysis_depth: Literal["quick", "standard", "deep"] = "standard"
    enable_github_actions: bool = False

    @field_validator("repository_url")
    @classmethod
    def _url(cls, value: str) -> str:
        return validate_repository_url(value).canonical_url

    @field_validator("branch")
    @classmethod
    def _branch(cls, value: str) -> str:
        return validate_branch(value)


class DemoInvestigationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_depth: Literal["quick", "standard", "deep"] = "standard"
    fault_injection: bool = True
    step_delay_ms: int | None = Field(default=None, ge=0, le=3000)


class InvestigationSummary(BaseModel):
    investigation_id: str
    repository: str
    repository_url: str
    branch: str
    source: str
    analysis_depth: str
    status: InvestigationStatus
    overall_risk: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None


class InvestigationDetail(InvestigationSummary):
    commit_sha: str | None = None
    repo_profile: dict[str, Any] = Field(default_factory=dict)
    plan: dict[str, Any] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)
    execution_summary: dict[str, Any] = Field(default_factory=dict)
    enable_github_actions: bool = False
    error: str | None = None
    counts: dict[str, Any] = Field(default_factory=dict)


class AgentRunOut(BaseModel):
    run_id: str
    agent: str
    task_id: str
    objective: str
    mode: str
    strategy: str
    attempt: int
    trigger: str
    round: int
    parent_request_id: str | None
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    iterations: int
    tool_calls: int
    llm_calls: int
    findings_count: int
    error_type: str | None
    error_message: str | None
    summary: str | None
    coverage: dict[str, Any]


class ExecutionEventOut(BaseModel):
    event_id: str
    investigation_id: str
    seq: int
    sender: str
    receiver: str
    event_type: str
    severity: str
    message: str
    correlation_id: str | None
    payload: dict[str, Any]
    timestamp: datetime


class InvestigationRequestOut(BaseModel):
    request_id: str
    requested_by: str
    target_agent: str | None
    objective: str
    reason: str
    required_evidence: str
    focus: dict[str, Any]
    related_finding_ids: list[str]
    status: str
    decision_reason: str | None
    assigned_task_ids: list[str]
    created_at: datetime
    resolved_at: datetime | None


class RiskOut(BaseModel):
    risk_id: str
    finding_id: str | None
    correlation_id: str | None
    kind: str
    title: str
    category: str
    severity: str
    score: float
    priority: str
    confidence: float
    impact: float
    exploitability: float
    correlation_multiplier: float
    factors: dict[str, Any]
    member_finding_ids: list[str]
    rationale: str
    created_at: datetime


class RecommendationOut(BaseModel):
    recommendation_id: str
    risk_id: str | None
    finding_ids: list[str]
    title: str
    problem: str
    affected_component: str
    why_it_matters: str
    proposed_fix: str
    estimated_risk: dict[str, Any]
    verification_status: str
    expected_benefit: str
    implementation_difficulty: str
    priority: str
    created_at: datetime


class ActionProposalOut(BaseModel):
    action_id: str
    recommendation_id: str | None
    action_type: str
    title: str
    body: str
    patch: str | None
    target_repository: str
    status: str
    requires_approval: bool
    approved_by: str | None
    decision_note: str | None
    result: dict[str, Any]
    risk_score: float | None
    created_at: datetime
    decided_at: datetime | None


class ApproveActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    decision: Literal["approve", "reject"] = "approve"
    approved_by: str = Field(min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=2000)
