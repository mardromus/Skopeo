"""LLM provider abstraction.

Agents never call an LLM directly. They call ``LLMProvider.decide()`` with:
* a Pydantic output schema (the only shape the answer may take),
* trusted structured state, and optional untrusted repository excerpts,
* a deterministic ``policy`` — the rule-based reasoning used in mock mode and as a fallback
  when the live model fails, times out or returns invalid output.

Every call is accounted (count, tokens, latency, fallback) so cost limits can be enforced
and so the execution trace can show *who* made each decision (LLM vs deterministic policy).
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ValidationError

from app.observability import get_logger

log = get_logger("llm")

T = TypeVar("T", bound=BaseModel)
V = TypeVar("V", bound=BaseModel)
ModelTier = Literal["fast", "reasoning"]


class LLMBudgetExceeded(RuntimeError):
    pass


@dataclass
class LLMRequest:
    task_type: str
    role_instructions: str
    task: str
    structured_input: dict[str, Any]
    untrusted: dict[str, str] | None = None
    tier: ModelTier = "fast"
    max_output_tokens: int | None = None


@dataclass
class LLMDecision(Generic[V]):  # noqa: UP046
    value: V
    decided_by: str  # e.g. "llm:gpt-4o-mini" | "policy" | "policy-fallback"
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    fallback_reason: str | None = None
    cached: bool = False


@dataclass
class UsageLedger:
    calls: int = 0
    llm_calls: int = 0
    fallbacks: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    by_task: dict[str, int] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, task_type: str, decision: LLMDecision[Any]) -> None:
        with self.lock:
            self.calls += 1
            self.by_task[task_type] = self.by_task.get(task_type, 0) + 1
            if decision.decided_by.startswith("llm:"):
                self.llm_calls += 1
            if decision.fallback_reason:
                self.fallbacks += 1
            self.input_tokens += decision.input_tokens
            self.output_tokens += decision.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": self.calls,
            "llm_calls": self.llm_calls,
            "policy_fallbacks": self.fallbacks,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "by_task": dict(self.by_task),
        }


class LLMProvider(ABC):
    name: str = "abstract"

    def __init__(self, max_calls: int = 120) -> None:
        self.max_calls = max_calls
        self.usage = UsageLedger()
        self._cache: dict[str, Any] = {}
        self._cache_lock = threading.Lock()

    @property
    def is_mock(self) -> bool:
        return False

    @abstractmethod
    def _complete(self, request: LLMRequest, schema: type[T]) -> tuple[T, int, int, str]:
        """Return (parsed value, input tokens, output tokens, model name). Raise on failure."""

    def decide(
        self,
        request: LLMRequest,
        schema: type[T],
        policy: Callable[[], T],
        validate: Callable[[T], T] | None = None,
    ) -> LLMDecision[T]:
        """Ask the model for a structured decision; fall back to ``policy`` deterministically."""
        started = time.monotonic()
        if self.is_mock:
            decision = LLMDecision(value=policy(), decided_by="policy")
            self.usage.record(request.task_type, decision)
            return decision
        key = self._cache_key(request, schema)
        with self._cache_lock:
            cached = self._cache.get(key)
        if cached is not None:
            decision = LLMDecision(value=cached, decided_by="llm:cache", cached=True)
            self.usage.record(request.task_type, decision)
            return decision
        if self.usage.llm_calls >= self.max_calls:
            decision = LLMDecision(value=policy(), decided_by="policy-fallback", fallback_reason="LLM call budget exhausted")
            self.usage.record(request.task_type, decision)
            return decision
        try:
            value, tin, tout, model = self._complete(request, schema)
            if validate is not None:
                value = validate(value)
            decision = LLMDecision(
                value=value,
                decided_by=f"llm:{model}",
                latency_ms=int((time.monotonic() - started) * 1000),
                input_tokens=tin,
                output_tokens=tout,
            )
            with self._cache_lock:
                self._cache[key] = value
        except (ValidationError, ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
            log.warning(
                "llm decision failed; using deterministic policy",
                extra={
                    "event_type": "llm_fallback",
                    "data": {"task": request.task_type, "error": f"{type(exc).__name__}: {str(exc)[:200]}"},
                },
            )
            decision = LLMDecision(
                value=policy(),
                decided_by="policy-fallback",
                latency_ms=int((time.monotonic() - started) * 1000),
                fallback_reason=f"{type(exc).__name__}: {str(exc)[:160]}",
            )
        self.usage.record(request.task_type, decision)
        return decision

    @staticmethod
    def _cache_key(request: LLMRequest, schema: type[BaseModel]) -> str:
        blob = json.dumps(
            [request.task_type, request.task, request.structured_input, request.untrusted, schema.__name__],
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()
