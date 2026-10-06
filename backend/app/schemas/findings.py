"""Strict schemas for findings, evidence, correlations and verifications."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import (
    Category,
    CorrelationStatus,
    FindingStatus,
    RelationshipType,
    Severity,
    SourceType,
    VerificationDecision,
)


class EvidenceDraft(BaseModel):
    """Evidence as produced by an agent before it is persisted."""

    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    source: str = Field(min_length=1, max_length=512)
    tool: str = Field(min_length=1, max_length=128)
    file: str | None = None
    line_start: int | None = Field(default=None, ge=0)
    line_end: int | None = Field(default=None, ge=0)
    excerpt: str = Field(default="", max_length=4000)
    raw_reference: str = Field(default="", max_length=4000)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _lines(self) -> EvidenceDraft:
        if self.line_start is not None and self.line_end is not None and self.line_end < self.line_start:
            raise ValueError("line_end must be >= line_start")
        if self.file and (self.file.startswith("/") or ".." in self.file.replace("\\", "/").split("/")):
            raise ValueError("evidence file must be a repository-relative path")
        return self


class EvidenceOut(BaseModel):
    evidence_id: str
    finding_id: str | None
    source_type: SourceType
    source: str
    file: str | None
    line_start: int | None
    line_end: int | None
    excerpt: str
    tool: str
    raw_reference: str
    confidence: float
    created_by: str
    content_hash: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class FindingDraft(BaseModel):
    """A finding as proposed by a specialist agent."""

    model_config = ConfigDict(extra="forbid")

    category: Category
    rule_id: str = Field(min_length=1, max_length=96)
    title: str = Field(min_length=3, max_length=512)
    description: str = Field(min_length=1, max_length=8000)
    severity: Severity
    subject: str | None = Field(default=None, max_length=512)
    affected_files: list[str] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_summary: str = Field(min_length=1, max_length=4000)
    recommended_action: str = Field(default="", max_length=4000)
    is_hypothesis: bool = False

    @field_validator("affected_files")
    @classmethod
    def _relative_files(cls, files: list[str]) -> list[str]:
        for f in files:
            norm = f.replace("\\", "/")
            if norm.startswith("/") or ".." in norm.split("/"):
                raise ValueError(f"affected file must be repository-relative: {f!r}")
        return [f.replace("\\", "/") for f in files]


class FindingOut(BaseModel):
    """Public finding schema (matches the documented Finding contract)."""

    finding_id: str
    agent: str
    category: Category
    rule_id: str
    title: str
    description: str
    severity: Severity
    confidence: float
    confidence_factors: list[dict[str, Any]] = Field(default_factory=list)
    status: FindingStatus
    subject: str | None = None
    affected_files: list[str]
    affected_components: list[str]
    evidence_ids: list[str]
    tool_results: list[dict[str, Any]]
    attributes: dict[str, Any] = Field(default_factory=dict)
    reasoning_summary: str
    recommended_action: str
    is_hypothesis: bool = False
    agent_run_id: str | None = None
    created_at: datetime
    updated_at: datetime


class CorrelationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_ids: list[str] = Field(min_length=2)
    relationship_type: RelationshipType
    title: str
    description: str
    risk_multiplier: float = Field(default=1.0, ge=0.5, le=2.0)
    confidence: float = Field(ge=0.0, le=1.0)
    signature: str
    links: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_summary: str = ""


class CorrelationOut(BaseModel):
    correlation_id: str
    finding_ids: list[str]
    relationship_type: RelationshipType
    title: str
    description: str
    risk_multiplier: float
    confidence: float
    status: CorrelationStatus
    links: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_summary: str
    resolution: str | None = None
    signature: str = ""
    created_at: datetime
    updated_at: datetime


class VerificationCheck(BaseModel):
    """One adversarial question asked by the red-team and its outcome."""

    check: str
    question: str
    outcome: str  # pass | fail | inconclusive | not_applicable
    detail: str
    supports: str | None = None  # finding | rejection | more_evidence


class VerificationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str | None = None
    correlation_id: str | None = None
    round: int = 1
    decision: VerificationDecision
    confidence: float = Field(ge=0.0, le=1.0)
    challenge: str
    checks: list[VerificationCheck] = Field(default_factory=list)
    evidence_checked: list[str] = Field(default_factory=list)
    additional_tests: list[dict[str, Any]] = Field(default_factory=list)
    counter_evidence: list[dict[str, Any]] = Field(default_factory=list)
    adjusted_severity: Severity | None = None
    reasoning_summary: str
    decided_by: str = "rule-engine"


class VerificationOut(BaseModel):
    verification_id: str
    finding_id: str | None
    correlation_id: str | None
    round: int
    decision: VerificationDecision
    confidence: float
    challenge: str
    checks: list[dict[str, Any]]
    evidence_checked: list[str]
    additional_tests: list[dict[str, Any]]
    counter_evidence: list[dict[str, Any]]
    adjusted_severity: Severity | None
    reasoning_summary: str
    decided_by: str
    verified_at: datetime
