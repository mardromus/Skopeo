"""Shared enumerations used across schemas, agents and the API."""

from __future__ import annotations

from enum import StrEnum


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def rank(self) -> int:
        return SEVERITY_RANK[self]


SEVERITY_RANK = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
    Severity.INFO: 0,
}


def max_severity(values: list[str]) -> Severity:
    if not values:
        return Severity.INFO
    return max((Severity(v) for v in values), key=lambda s: s.rank)


class FindingStatus(StrEnum):
    PROPOSED = "proposed"
    CORRELATED = "correlated"
    CHALLENGED = "challenged"
    VERIFIED = "verified"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class Category(StrEnum):
    SECURITY = "security"
    DEPENDENCY = "dependency"
    CODE_QUALITY = "code_quality"
    API_COMPATIBILITY = "api_compatibility"
    TESTING = "testing"
    LICENSE = "license"
    MAINTENANCE = "maintenance"
    PERFORMANCE = "performance"


class SourceType(StrEnum):
    STATIC_ANALYSIS = "static_analysis"
    GIT = "git"
    GITHUB = "github"
    TEST = "test"
    DEPENDENCY = "dependency"
    LLM_ANALYSIS = "llm_analysis"
    BENCHMARK = "benchmark"


class RelationshipType(StrEnum):
    COMPOUND_RISK = "compound_risk"
    DUPLICATE = "duplicate"
    CONTRADICTION = "contradiction"
    DEPENDENCY = "dependency"
    CAUSAL = "causal"
    SHARED_ROOT_CAUSE = "shared_root_cause"


class CorrelationStatus(StrEnum):
    PROPOSED = "proposed"
    VERIFIED = "verified"
    REJECTED = "rejected"
    RESOLVED = "resolved"


class VerificationDecision(StrEnum):
    VERIFIED = "verified"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class AgentRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class InvestigationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_LIMITATIONS = "completed_with_limitations"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self not in (InvestigationStatus.QUEUED, InvestigationStatus.RUNNING)


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class EventType(StrEnum):
    INVESTIGATION_STARTED = "investigation_started"
    REPOSITORY_PREPARED = "repository_prepared"
    PLAN_CREATED = "plan_created"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    AGENT_RETRY_SCHEDULED = "agent_retry_scheduled"
    FINDING_CREATED = "finding_created"
    FINDING_UPDATED = "finding_updated"
    EVIDENCE_ADDED = "evidence_added"
    AGENT_MESSAGE = "agent_message"
    INVESTIGATION_REQUESTED = "investigation_requested"
    REQUEST_DECIDED = "request_decided"
    REPLAN = "replan"
    ORCHESTRATOR_DECISION = "orchestrator_decision"
    TOOL_EXECUTED = "tool_executed"
    CORRELATION_CREATED = "correlation_created"
    CORRELATION_UPDATED = "correlation_updated"
    VERIFICATION_STARTED = "verification_started"
    CHALLENGE = "challenge"
    VERIFICATION_COMPLETED = "verification_completed"
    FINDING_REJECTED = "finding_rejected"
    FINDING_VERIFIED = "finding_verified"
    RISK_ASSESSED = "risk_assessed"
    RECOMMENDATION_CREATED = "recommendation_created"
    GITHUB_ACTION_PROPOSED = "github_action_proposed"
    HUMAN_APPROVAL_REQUIRED = "human_approval_required"
    ACTION_DECIDED = "action_decided"
    INVESTIGATION_COMPLETED = "investigation_completed"
    INVESTIGATION_FAILED = "investigation_failed"
    INVESTIGATION_CANCELLED = "investigation_cancelled"


SPECIALIST_AGENTS = (
    "security_agent",
    "dependency_agent",
    "code_quality_agent",
    "api_compatibility_agent",
    "test_reliability_agent",
    "license_agent",
    "maintenance_agent",
    "performance_agent",
)

COORDINATION_AGENTS = (
    "orchestrator",
    "correlation_agent",
    "verification_agent",
    "risk_agent",
    "recommendation_agent",
)
