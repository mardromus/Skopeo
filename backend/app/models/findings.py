"""Blackboard knowledge entities: Finding, Evidence, Correlation, Verification."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamped, UUIDPrimaryKey, utcnow


class Finding(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "findings"

    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(64), index=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    category: Mapped[str] = mapped_column(String(48), index=True)
    rule_id: Mapped[str] = mapped_column(String(96), default="generic")
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_factors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    subject: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    affected_files: Mapped[list[str]] = mapped_column(JSON, default=list)
    affected_components: Mapped[list[str]] = mapped_column(JSON, default=list)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tool_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    reasoning_summary: Mapped[str] = mapped_column(Text, default="")
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    is_hypothesis: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Evidence(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "evidence"

    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    finding_id: Mapped[str | None] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(512))
    file: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    tool: Mapped[str] = mapped_column(String(128))
    raw_reference: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Correlation(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "correlations"

    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    finding_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    relationship_type: Mapped[str] = mapped_column(String(48), index=True)
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text, default="")
    risk_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    signature: Mapped[str] = mapped_column(String(256), index=True)
    links: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    reasoning_summary: Mapped[str] = mapped_column(Text, default="")
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="correlation_agent")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Verification(UUIDPrimaryKey, Base):
    __tablename__ = "verifications"

    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    finding_id: Mapped[str | None] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(ForeignKey("correlations.id", ondelete="CASCADE"), nullable=True, index=True)
    round: Mapped[int] = mapped_column(Integer, default=1)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    challenge: Mapped[str] = mapped_column(Text, default="")
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    evidence_checked: Mapped[list[str]] = mapped_column(JSON, default=list)
    additional_tests: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    counter_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    adjusted_severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reasoning_summary: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[str] = mapped_column(String(64), default="rule-engine")
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
