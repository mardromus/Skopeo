"""Fault-isolated agent execution.

Every agent run is wrapped so that a crash, timeout or budget overrun:
* marks its AgentRun FAILED/TIMEOUT with the (redacted) error,
* preserves everything the agent already wrote to the blackboard,
* notifies the orchestrator through an ``agent_failed`` event,
* never propagates to the graph — unrelated agents keep running.
"""

from __future__ import annotations

import asyncio
import traceback

from app.agents.base import Agent, AgentContext, AgentServices, BudgetExceeded, InvestigationCancelled
from app.observability import agent_var, get_logger, investigation_id_var
from app.schemas import AgentTask, EventType, TaskResult

log = get_logger("graph.runtime")


async def run_agent_isolated(services: AgentServices, agent: Agent, task: AgentTask) -> TaskResult:
    store, events = services.store, services.events
    run_id = store.create_agent_run(services.investigation_id, task)
    ordinal = services.next_run_ordinal(agent.name)
    ctx = AgentContext(services, agent.name, task, run_id, run_ordinal=ordinal)
    store.start_agent_run(run_id)
    events.emit(
        services.investigation_id,
        agent.name,
        EventType.AGENT_STARTED,
        f"{agent.display_name} started: {task.objective}"
        + (f" [{task.mode}]" if task.mode != "full" else "")
        + (f" (attempt {task.attempt}, strategy {task.strategy})" if task.attempt > 1 else ""),
        receiver="orchestrator",
        payload={
            "run_id": run_id,
            "task_id": task.task_id,
            "mode": task.mode,
            "strategy": task.strategy,
            "attempt": task.attempt,
            "trigger": task.trigger,
            "round": task.round,
            "rationale": task.rationale,
        },
    )

    def _run() -> object:
        investigation_id_var.set(services.investigation_id)
        agent_var.set(agent.name)
        return agent.run(ctx)

    status, error_type, error_message, outcome = "completed", None, None, None
    try:
        outcome = await asyncio.wait_for(asyncio.to_thread(_run), timeout=services.settings.agent_timeout_seconds)
    except TimeoutError:
        ctx.stop_event.set()
        status, error_type, error_message = "timeout", "TimeoutError", f"exceeded {services.settings.agent_timeout_seconds}s"
    except InvestigationCancelled as exc:
        status, error_type, error_message = "cancelled", "InvestigationCancelled", str(exc)
    except BudgetExceeded as exc:
        status, error_type, error_message = "failed", "BudgetExceeded", str(exc)
    except Exception as exc:  # noqa: BLE001 - fault isolation boundary
        status, error_type, error_message = "failed", type(exc).__name__, str(exc)[:500]
        log.warning(
            "agent failed",
            extra={
                "investigation_id": services.investigation_id,
                "agent": agent.name,
                "event_type": "agent_failed",
                "data": {"trace": traceback.format_exc()[-1500:]},
            },
        )
    summary = getattr(outcome, "summary", None)
    coverage = getattr(outcome, "coverage", None) or ctx.coverage
    coverage = dict(coverage)
    coverage.setdefault("limitations", ctx.coverage.get("limitations", []))
    run = store.finish_agent_run(
        run_id,
        status,
        iterations=ctx.iterations,
        tool_calls=ctx.tool_calls,
        llm_calls=ctx.llm_calls,
        error_type=error_type,
        error_message=error_message,
        summary=summary,
        coverage=coverage,
    )
    if status == "completed":
        events.emit(
            services.investigation_id,
            agent.name,
            EventType.AGENT_COMPLETED,
            f"{agent.display_name} completed in {run.duration_ms} ms: {summary}",
            receiver="orchestrator",
            payload={
                "run_id": run_id,
                "task_id": task.task_id,
                "duration_ms": run.duration_ms,
                "findings": run.findings_count,
                "limitations": coverage.get("limitations", [])[:6],
            },
        )
    else:
        events.emit(
            services.investigation_id,
            agent.name,
            EventType.AGENT_FAILED,
            f"{agent.display_name} {status.upper()}: {error_type}: {error_message}",
            receiver="orchestrator",
            payload={
                "run_id": run_id,
                "task_id": task.task_id,
                "error_type": error_type,
                "error": error_message,
                "findings_preserved": run.findings_count,
                "attempt": task.attempt,
            },
            severity="error",
        )
    return TaskResult(
        task_id=task.task_id,
        agent=agent.name,
        run_id=run_id,
        status=status,
        attempt=task.attempt,
        mode=task.mode,
        strategy=task.strategy,
        round=task.round,
        error_type=error_type,
        error_message=error_message,
        findings_created=run.findings_count,
        retryable=status in ("failed", "timeout") and error_type not in ("InvestigationCancelled",),
    )
