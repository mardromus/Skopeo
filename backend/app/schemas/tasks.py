"""Schemas for orchestration: tasks, plans, decisions and agent outcomes."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TaskTrigger = Literal["initial_plan", "follow_up", "retry", "verification_request", "correlation_request"]


class AgentTask(BaseModel):
    """A unit of work the orchestrator assigns to a specialist agent."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent: str
    objective: str
    mode: str = "full"
    strategy: str = "default"
    focus: dict[str, Any] = Field(default_factory=dict)
    priority: int = 2
    trigger: TaskTrigger = "initial_plan"
    attempt: int = 1
    round: int = 1
    parent_request_id: str | None = None
    rationale: str = ""

    def dedup_key(self) -> str:
        focus_key = ",".join(f"{k}={self.focus[k]}" for k in sorted(self.focus) if k != "reason")
        return f"{self.agent}|{self.mode}|{self.strategy}|{focus_key}"


class TaskResult(BaseModel):
    task_id: str
    agent: str
    run_id: str | None
    status: str  # completed | failed | timeout | cancelled
    attempt: int
    mode: str
    strategy: str
    round: int
    error_type: str | None = None
    error_message: str | None = None
    findings_created: int = 0
    retryable: bool = True


class PlannedAgent(BaseModel):
    """LLM / policy output for one planned specialist."""

    agent: str
    objective: str
    priority: int = Field(default=2, ge=1, le=3)
    rationale: str


class SkippedAgent(BaseModel):
    agent: str
    reason: str


class PlanDecision(BaseModel):
    """Structured output the orchestrator's planner must produce."""

    repository_assessment: str
    agents: list[PlannedAgent]
    skipped: list[SkippedAgent] = Field(default_factory=list)
    parallel_groups: list[list[str]] = Field(default_factory=list)
    rationale: str


class FollowUpDecision(BaseModel):
    agent: str
    objective: str
    mode: str = "full"
    strategy: str = "default"
    focus: dict[str, Any] = Field(default_factory=dict)
    trigger: TaskTrigger = "follow_up"
    request_id: str | None = None
    rationale: str


class RetryDecision(BaseModel):
    task_id: str
    agent: str
    retry: bool
    strategy: str = "default"
    rationale: str


class RequestDecision(BaseModel):
    request_id: str
    accept: bool
    rationale: str


class ReviewDecision(BaseModel):
    """Structured output of the orchestrator's review step (after every phase)."""

    assessment: str
    retries: list[RetryDecision] = Field(default_factory=list)
    request_decisions: list[RequestDecision] = Field(default_factory=list)
    follow_ups: list[FollowUpDecision] = Field(default_factory=list)
    next_step: Literal["dispatch", "correlate", "verify", "assess", "finalize"]
    rationale: str


class AgentOutcome(BaseModel):
    summary: str
    findings_created: int = 0
    findings_updated: int = 0
    coverage: dict[str, Any] = Field(default_factory=dict)
