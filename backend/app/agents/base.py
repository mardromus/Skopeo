"""Agent runtime: explicit dependencies, budgets, tool accounting and blackboard access.

Agents receive everything they need through ``AgentContext`` — there is no hidden global state.
They communicate only by writing to the Evidence Store (findings, evidence, requests) and by
emitting structured events (messages) that other agents and the orchestrator read.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

from pydantic import BaseModel

from app.config import Settings
from app.llm import LLMProvider, LLMRequest
from app.llm.base import LLMDecision
from app.observability import get_logger
from app.schemas import AgentOutcome, AgentTask, EventType, EvidenceDraft, FindingDraft, FindingOut
from app.services.events import EventBus
from app.services.evidence_store import EvidenceStore
from app.services.fault_injection import maybe_inject

if TYPE_CHECKING:
    from app.tools.advisories import AdvisoryClient, RegistryClient
    from app.tools.github import GitHubClient
    from app.tools.repository import RepositoryHandle, RepositoryTools

log = get_logger("agents")
T = TypeVar("T", bound=BaseModel)


class BudgetExceeded(RuntimeError):
    """An agent hit MAX_ITERATIONS / MAX_TOOL_CALLS / TIMEOUT."""


class InvestigationCancelled(RuntimeError):
    pass


@dataclass
class AgentServices:
    """Per-investigation dependencies shared by all agents (explicitly passed, never global)."""

    investigation_id: str
    settings: Settings
    store: EvidenceStore
    events: EventBus
    llm: LLMProvider
    advisories: AdvisoryClient
    registry: RegistryClient
    github: GitHubClient
    fault_spec: str = ""
    step_delay_ms: int = 0
    repo: RepositoryHandle | None = None
    tools: RepositoryTools | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    run_counter: dict[str, int] = field(default_factory=dict)
    run_counter_lock: threading.Lock = field(default_factory=threading.Lock)

    def next_run_ordinal(self, agent: str) -> int:
        with self.run_counter_lock:
            self.run_counter[agent] = self.run_counter.get(agent, 0) + 1
            return self.run_counter[agent]


class AgentContext:
    def __init__(self, services: AgentServices, agent: str, task: AgentTask, run_id: str, run_ordinal: int = 1) -> None:
        self.services = services
        self.agent = agent
        self.task = task
        self.run_id = run_id
        self.run_ordinal = run_ordinal
        self.settings = services.settings
        self.store = services.store
        self.events = services.events
        self.investigation_id = services.investigation_id
        self.iterations = 0
        self.tool_calls = 0
        self.llm_calls = 0
        self.findings_created = 0
        self.findings_updated = 0
        self.started = time.monotonic()
        self.deadline = self.started + self.settings.agent_timeout_seconds
        self.coverage: dict[str, Any] = {"analyzed": [], "limitations": [], "tool_results": []}
        self.stop_event = threading.Event()
        self._last_cancel_check = 0.0

    # ------------------------------------------------------------ properties
    @property
    def repo(self) -> RepositoryHandle:
        assert self.services.repo is not None, "repository not prepared"
        return self.services.repo

    @property
    def tools(self) -> RepositoryTools:
        assert self.services.tools is not None, "repository tools not prepared"
        return self.services.tools

    @property
    def profile(self) -> dict[str, Any]:
        return self.repo.profile

    # --------------------------------------------------------------- budgets
    def tick(self, label: str | None = None) -> None:
        """Called at each reasoning step. Enforces loop limits, timeout and cancellation."""
        self.iterations += 1
        if self.iterations > self.settings.agent_max_iterations:
            raise BudgetExceeded(f"MAX_ITERATIONS ({self.settings.agent_max_iterations}) exceeded")
        self._check_stop()
        if self.services.step_delay_ms:
            time.sleep(self.services.step_delay_ms / 1000.0)

    def _check_stop(self) -> None:
        if self.stop_event.is_set():
            raise BudgetExceeded("agent TIMEOUT reached")
        if time.monotonic() > self.deadline:
            raise BudgetExceeded(f"agent TIMEOUT ({self.settings.agent_timeout_seconds}s) reached")
        if self.services.cancel_event.is_set():
            raise InvestigationCancelled("investigation cancelled")
        now = time.monotonic()
        if now - self._last_cancel_check > 1.0:
            self._last_cancel_check = now
            if self.store.is_cancel_requested(self.investigation_id):
                self.services.cancel_event.set()
                raise InvestigationCancelled("investigation cancelled by user")

    def tool(self, name: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Invoke a tool with accounting (MAX_TOOL_CALLS) and structured logging."""
        self.tool_calls += 1
        if self.tool_calls > self.settings.agent_max_tool_calls:
            raise BudgetExceeded(f"MAX_TOOL_CALLS ({self.settings.agent_max_tool_calls}) exceeded")
        self._check_stop()
        started = time.monotonic()
        try:
            return fn(*args, **kwargs)
        finally:
            log.debug(
                f"tool {name}",
                extra={
                    "investigation_id": self.investigation_id,
                    "agent": self.agent,
                    "event_type": "tool_call",
                    "data": {"tool": name, "ms": int((time.monotonic() - started) * 1000)},
                },
            )

    def require_tool(self, tool_name: str) -> None:
        """Declare a dependency on an external tool (also the controlled fault-injection point)."""
        maybe_inject(self.services.fault_spec, self.agent, self.run_ordinal, tool_name)

    def record_tool_result(self, result: dict[str, Any]) -> None:
        self.coverage["tool_results"].append(result)
        self.emit(EventType.TOOL_EXECUTED, f"{self.agent} executed {result.get('command', result.get('tool', 'tool'))}", payload=result)

    # ----------------------------------------------------------- blackboard
    def publish(self, draft: FindingDraft, evidence: list[EvidenceDraft]) -> FindingOut:
        hashes = [self.tools.line_hash(e.file, e.line_start, e.line_end) if e.file else None for e in evidence]
        draft.attributes.setdefault("commit_sha", self.repo.commit_sha)
        finding = self.store.add_finding(self.investigation_id, self.agent, self.run_id, draft, evidence, hashes)
        self.findings_created += 1
        self.emit(
            EventType.FINDING_CREATED,
            f"{draft.severity.value.upper()} {draft.category.value}: {draft.title}",
            payload={
                "finding_id": finding.finding_id,
                "title": finding.title,
                "severity": finding.severity.value,
                "category": finding.category.value,
                "confidence": finding.confidence,
                "evidence_count": len(finding.evidence_ids),
                "rule_id": finding.rule_id,
                "files": finding.affected_files[:5],
            },
        )
        return finding

    def attach_evidence(self, finding_id: str, draft: EvidenceDraft, note: str, **confidence_inputs: Any) -> FindingOut:
        content_hash = self.tools.line_hash(draft.file, draft.line_start, draft.line_end) if draft.file else None
        ev = self.store.add_evidence(self.investigation_id, finding_id, self.agent, draft, content_hash)
        updated = self.store.recompute_confidence(finding_id, **confidence_inputs)
        self.findings_updated += 1
        self.emit(
            EventType.EVIDENCE_ADDED,
            note,
            payload={
                "finding_id": finding_id,
                "evidence_id": ev.evidence_id,
                "source_type": draft.source_type.value,
                "tool": draft.tool,
                "new_confidence": updated.confidence,
            },
        )
        return updated

    def request_investigation(
        self,
        objective: str,
        *,
        reason: str,
        required_evidence: str,
        target_agent: str | None = None,
        focus: dict[str, Any] | None = None,
        related_finding_ids: list[str] | None = None,
    ) -> str:
        req = self.store.add_request(
            self.investigation_id,
            self.agent,
            objective,
            reason=reason,
            target_agent=target_agent,
            required_evidence=required_evidence,
            focus=focus,
            related_finding_ids=related_finding_ids,
        )
        self.emit(
            EventType.INVESTIGATION_REQUESTED,
            f"Requests {required_evidence.replace('_', ' ')}: {objective}",
            receiver="orchestrator",
            payload={
                "request_id": req.request_id,
                "target_agent": target_agent,
                "required_evidence": required_evidence,
                "reason": reason,
                "related_finding_ids": related_finding_ids or [],
                "focus": focus or {},
            },
        )
        return req.request_id

    def message(self, receiver: str, text: str, payload: dict[str, Any] | None = None, severity: str = "info") -> None:
        self.emit(EventType.AGENT_MESSAGE, text, receiver=receiver, payload=payload, severity=severity)

    def emit(
        self,
        event_type: str,
        message: str,
        *,
        receiver: str = "blackboard",
        payload: dict[str, Any] | None = None,
        severity: str = "info",
        correlation_id: str | None = None,
    ) -> None:
        body = dict(payload or {})
        body.setdefault("run_id", self.run_id)
        self.events.emit(
            self.investigation_id,
            self.agent,
            event_type,
            message,
            receiver=receiver,
            payload=body,
            severity=severity,
            correlation_id=correlation_id,
        )

    def findings(self, **filters: Any) -> list[FindingOut]:
        return self.store.list_findings(self.investigation_id, **filters)

    def analyzed(self, text: str) -> None:
        self.coverage["analyzed"].append(text)

    def limitation(self, text: str) -> None:
        self.coverage["limitations"].append(text)

    # ------------------------------------------------------------------ LLM
    def decide(
        self,
        task_type: str,
        schema: type[T],
        policy: Callable[[], T],
        *,
        role: str,
        task: str,
        structured: dict[str, Any],
        untrusted: dict[str, str] | None = None,
        tier: str = "fast",
        validate: Callable[[T], T] | None = None,
    ) -> LLMDecision[T]:
        self.llm_calls += 1
        request = LLMRequest(
            task_type=task_type, role_instructions=role, task=task, structured_input=structured, untrusted=untrusted, tier=tier
        )  # type: ignore[arg-type]
        return self.services.llm.decide(request, schema, policy, validate)


class Agent(ABC):
    name: ClassVar[str]
    display_name: ClassVar[str]
    category: ClassVar[str | None] = None
    description: ClassVar[str] = ""
    modes: ClassVar[dict[str, str]] = {"full": "complete domain investigation"}

    @abstractmethod
    def run(self, ctx: AgentContext) -> AgentOutcome: ...

    def fallback_strategy(self, error_type: str, current_strategy: str) -> str | None:
        """Strategy to use when retrying after ``error_type``; None means 'retry unchanged'."""
        return None


Step = tuple[str, Callable[["AgentContext"], "list[Step] | None"]]


class SpecialistAgent(Agent):
    """A domain expert with its own internal plan.

    ``plan()`` produces the agent's *own* list of investigation steps from the repository profile,
    the assigned task/mode and what is already on the blackboard. Steps may enqueue further steps
    when intermediate results warrant deeper analysis (bounded by MAX_ITERATIONS).
    """

    @abstractmethod
    def plan(self, ctx: AgentContext) -> list[Step]: ...

    def summarize(self, ctx: AgentContext) -> str:
        return f"{ctx.findings_created} finding(s) published, {ctx.findings_updated} enriched"

    def run(self, ctx: AgentContext) -> AgentOutcome:
        steps = self.plan(ctx)
        ctx.message(
            "orchestrator",
            f"{self.display_name} plan ({ctx.task.mode}/{ctx.task.strategy}): " + ", ".join(label for label, _ in steps),
            payload={"steps": [label for label, _ in steps], "mode": ctx.task.mode, "strategy": ctx.task.strategy},
        )
        while steps:
            label, step = steps.pop(0)
            ctx.tick(label)
            extra = step(ctx)
            if extra:
                ctx.message(
                    "orchestrator",
                    f"{self.display_name} extended its plan after '{label}': " + ", ".join(lbl for lbl, _ in extra),
                    payload={"added_steps": [lbl for lbl, _ in extra]},
                )
                steps.extend(extra)
        return AgentOutcome(
            summary=self.summarize(ctx), findings_created=ctx.findings_created, findings_updated=ctx.findings_updated, coverage=ctx.coverage
        )
