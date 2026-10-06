"""LangGraph state.

The graph state only carries *control* information (task queue, round counters, phase
bookkeeping). All investigation knowledge lives on the blackboard (Evidence Store) so that
agents never depend on hidden in-memory state.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class InvestigationState(TypedDict, total=False):
    investigation_id: str
    depth: str
    round: int
    pending_tasks: list[dict[str, Any]]
    task_results: Annotated[list[dict[str, Any]], operator.add]
    reviewed_task_ids: list[str]
    completed_task_keys: list[str]
    reviewed_finding_ids: list[str]
    escalated: list[str]
    last_correlated_version: int
    last_verified_version: int
    correlation_rounds: int
    verification_rounds: int
    next_step: str
    fatal_error: str | None
    replans: int
    started_monotonic: float


class SpecialistInput(TypedDict):
    task: dict[str, Any]
