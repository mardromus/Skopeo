"""Outcome entities: RiskAssessment, Recommendation, ActionProposal."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamped, UUIDPrimaryKey


class RiskAssessment(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "risks"

    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    finding_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), default="finding")  # finding | compound
    title: Mapped[str] = mapped_column(String(512))
    category: Mapped[str] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(16), index=True)
    score: Mapped[float] = mapped_column(Float)
    priority: Mapped[str] = mapped_column(String(8), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    impact: Mapped[float] = mapped_column(Float)
    exploitability: Mapped[float] = mapped_column(Float)
    correlation_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    factors: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    member_finding_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    rationale: Mapped[str] = mapped_column(Text, default="")


class Recommendation(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "recommendations"

    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    risk_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    finding_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    title: Mapped[str] = mapped_column(String(512))
    problem: Mapped[str] = mapped_column(Text)
    affected_component: Mapped[str] = mapped_column(String(512))
    why_it_matters: Mapped[str] = mapped_column(Text)
    proposed_fix: Mapped[str] = mapped_column(Text)
    estimated_risk: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    verification_status: Mapped[str] = mapped_column(String(32))
    expected_benefit: Mapped[str] = mapped_column(Text)
    implementation_difficulty: Mapped[str] = mapped_column(String(16))
    priority: Mapped[str] = mapped_column(String(8), index=True)


class ActionProposal(UUIDPrimaryKey, Timestamped, Base):
    """A GitHub action Skopeo *proposes*. Never executed without explicit human approval."""

    __tablename__ = "action_proposals"

    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    recommendation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action_type: Mapped[str] = mapped_column(String(32))  # github_issue | pull_request
    title: Mapped[str] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text)
    patch: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_repository: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
