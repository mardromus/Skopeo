"""Investigation-level entities: Investigation, AgentRun, ExecutionEvent, InvestigationRequest."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamped, UUIDPrimaryKey, utcnow


class Investigation(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "investigations"

    repository_url: Mapped[str] = mapped_column(String(512))
    repository_name: Mapped[str] = mapped_column(String(256))
    branch: Mapped[str] = mapped_column(String(256), default="main")
    analysis_depth: Mapped[str] = mapped_column(String(32), default="standard")
    source: Mapped[str] = mapped_column(String(32), default="github")  # github | demo_fixture
    enable_github_actions: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(48), default="queued", index=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    repo_profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    coverage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    execution_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    overall_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    overall_risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AgentRun(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "agent_runs"

    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(64), index=True)
    task_id: Mapped[str] = mapped_column(String(36))
    objective: Mapped[str] = mapped_column(Text, default="")
    mode: Mapped[str] = mapped_column(String(48), default="full")
    strategy: Mapped[str] = mapped_column(String(48), default="default")
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    trigger: Mapped[str] = mapped_column(String(48), default="initial_plan")
    round: Mapped[int] = mapped_column(Integer, default=1)
    parent_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    iterations: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    findings_count: Mapped[int] = mapped_column(Integer, default=0)
    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    coverage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ExecutionEvent(UUIDPrimaryKey, Base):
    __tablename__ = "execution_events"
    __table_args__ = (UniqueConstraint("investigation_id", "seq"),)

    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    sender: Mapped[str] = mapped_column(String(64), index=True)
    receiver: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info")
    message: Mapped[str] = mapped_column(Text, default="")
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class InvestigationRequest(UUIDPrimaryKey, Timestamped, Base):
    """A blackboard entry asking for further investigation (written by any agent)."""

    __tablename__ = "investigation_requests"

    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    requested_by: Mapped[str] = mapped_column(String(64))
    target_agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    objective: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, default="")
    required_evidence: Mapped[str] = mapped_column(String(64), default="analysis")
    focus: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    related_finding_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_task_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
