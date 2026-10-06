"""MockLLMProvider — runs the full multi-agent architecture without any external API.

In mock mode every ``decide()`` call executes the caller's deterministic policy: transparent,
rule-based reasoning over the same structured state a live model would receive. Event flow,
state transitions, replanning, verification and rejection are all genuine; only the
natural-language "reasoning engine" is replaced by auditable rules. Decisions are labelled
``decided_by="policy"`` in the trace so nobody mistakes them for model output.
"""

from __future__ import annotations

from app.llm.base import LLMProvider, LLMRequest, T


class MockLLMProvider(LLMProvider):
    name = "mock"

    @property
    def is_mock(self) -> bool:
        return True

    def _complete(self, request: LLMRequest, schema: type[T]) -> tuple[T, int, int, str]:  # pragma: no cover
        raise RuntimeError("MockLLMProvider never calls a model; decide() uses the policy directly")
