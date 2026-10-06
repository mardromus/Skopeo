"""LangGraph state machine for an investigation.

    START -> prepare --(ok)--> plan --Send x N--> specialist (parallel) --> review
                     `--(fatal)--> finalize
    review --(dispatch: Send x N)--> specialist          (follow-ups, retries, benchmarks)
           --(correlate)--> correlate --> review
           --(verify)----> verify ----> review
           --(assess)----> assess --> recommend --> human_review --> finalize --> END
           --(finalize)--> finalize

Every edge out of ``review`` is conditional: the orchestrator decides the route after
inspecting the blackboard. Specialists fan out with ``Send`` and run concurrently; the next
``review`` fires once all branches of the superstep finish.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.agents.base import AgentContext, AgentServices
from app.agents.correlation import CorrelationAgent
from app.agents.orchestrator import OrchestratorAgent, ReviewInput
from app.agents.recommendation import RecommendationAgent
from app.agents.registry import create_specialist
from app.agents.risk import RiskAgent
from app.agents.verification import VerificationAgent, needs_verification
from app.graph.runtime import run_agent_isolated
from app.graph.state import InvestigationState, SpecialistInput
from app.schemas import AgentTask, EventType, TaskResult
from app.services.repository_ingestion import build_profile, clone_repository, prepare_demo_fixture
from app.tools.command_runner import SafeCommandRunner
from app.tools.repository import RepositoryTools


class InvestigationGraph:
    def __init__(self, services: AgentServices, orchestrator_run_id: str) -> None:
        self.s = services
        self.orchestrator = OrchestratorAgent()
        self.orchestrator_run_id = orchestrator_run_id
        self.runner = SafeCommandRunner(services.settings.command_timeout_seconds, services.settings.max_output_bytes)

    # ---------------------------------------------------------------- helpers
    def _octx(self, label: str = "orchestrate") -> AgentContext:
        task = AgentTask(agent="orchestrator", objective=label, trigger="initial_plan")
        return AgentContext(self.s, "orchestrator", task, self.orchestrator_run_id)

    def _emit(self, sender: str, etype: str, message: str, **kw: Any) -> None:
        self.s.events.emit(self.s.investigation_id, sender, etype, message, **kw)

    # ------------------------------------------------------------------ nodes
    async def prepare(self, state: InvestigationState) -> dict[str, Any]:
        inv = self.s.store.get_investigation(self.s.investigation_id)
        assert inv is not None
        try:
            if inv.source == "demo_fixture":
                handle = await asyncio.to_thread(prepare_demo_fixture, self.s.settings, self.runner, inv.id)
            else:
                handle = await asyncio.to_thread(clone_repository, self.s.settings, self.runner, inv.id, inv.repository_url, inv.branch)
            tools = RepositoryTools(handle, self.runner, self.s.settings)
            handle.profile = await asyncio.to_thread(build_profile, tools)
            self.s.repo, self.s.tools = handle, tools
            self.s.store.update_investigation(inv.id, commit_sha=handle.commit_sha, repo_profile=handle.profile)
            self._emit(
                "orchestrator",
                EventType.REPOSITORY_PREPARED,
                f"Repository prepared ({handle.source}) at {str(handle.commit_sha)[:10]}: {handle.profile['file_count']} files, primary language {handle.profile.get('primary_language')}",
                payload={
                    k: handle.profile.get(k)
                    for k in ("languages", "ecosystems", "manifests", "test_file_count", "git_commits_available", "trusted_execution")
                },
            )
            return {"fatal_error": None}
        except Exception as exc:  # noqa: BLE001 - ingestion failure is fatal but must be reported, not raised
            self._emit(
                "orchestrator",
                EventType.INVESTIGATION_FAILED,
                f"Repository preparation failed: {type(exc).__name__}: {exc}",
                severity="error",
            )
            return {"fatal_error": f"{type(exc).__name__}: {exc}"}

    async def plan(self, state: InvestigationState) -> dict[str, Any]:
        tasks = await asyncio.to_thread(self.orchestrator.create_plan, self._octx("plan"), state.get("depth", "standard"))
        return {"pending_tasks": [t.model_dump() for t in tasks], "round": 1}

    async def specialist(self, payload: SpecialistInput) -> dict[str, Any]:
        task = AgentTask(**payload["task"])
        agent = create_specialist(task.agent)
        result = await run_agent_isolated(self.s, agent, task)
        data = result.model_dump()
        data["dedup_key"] = task.dedup_key()
        return {"task_results": [data]}

    async def review(self, state: InvestigationState) -> dict[str, Any]:
        return await asyncio.to_thread(self._review_sync, state)

    def _review_sync(self, state: InvestigationState) -> dict[str, Any]:
        store, iid = self.s.store, self.s.investigation_id
        reviewed = set(state.get("reviewed_task_ids", []))
        all_results = state.get("task_results", [])
        new_results = [TaskResult(**{k: v for k, v in r.items() if k != "dedup_key"}) for r in all_results if r["task_id"] not in reviewed]
        completed_keys = set(state.get("completed_task_keys", [])) | {r["dedup_key"] for r in all_results if r.get("status") == "completed"}
        attempts: dict[str, list[dict]] = {}
        for r in all_results:
            attempts.setdefault(r["agent"], []).append(r)
        unavailable = {
            a
            for a, rs in attempts.items()
            if all(r["status"] != "completed" for r in rs) and any(r["attempt"] > self.s.settings.agent_max_retries for r in rs)
        }
        findings = store.list_findings(iid)
        seen_findings = set(state.get("reviewed_finding_ids", []))
        new_findings = [f for f in findings if f.finding_id not in seen_findings]
        correlations = store.list_correlations(iid)
        contested = {
            fid
            for c in correlations
            if c.relationship_type.value == "contradiction" and c.status.value == "proposed"
            for fid in c.finding_ids
        }
        pending = sum(1 for f in findings if needs_verification(f, contested))
        elapsed = time.monotonic() - state.get("started_monotonic", time.monotonic())
        inp = ReviewInput(
            round=state.get("round", 1),
            new_results=new_results,
            open_requests=store.list_requests(iid, status="open"),
            new_findings=new_findings,
            blackboard_version=store.blackboard_version(iid),
            last_correlated_version=state.get("last_correlated_version", 0),
            last_verified_version=state.get("last_verified_version", 0),
            correlation_rounds=state.get("correlation_rounds", 0),
            verification_rounds=state.get("verification_rounds", 0),
            pending_verification=pending,
            completed_task_keys=completed_keys,
            unavailable_agents=unavailable,
            deadline_reached=elapsed > self.s.settings.investigation_timeout_seconds * 0.8,
            cancelled=store.is_cancel_requested(iid) or self.s.cancel_event.is_set(),
            escalated=set(state.get("escalated", [])),
            verification_ran=state.get("verification_rounds", 0) > 0,
        )
        outcome = self.orchestrator.review(self._octx("review"), inp)
        self._fulfil_requests(all_results)
        update: dict[str, Any] = {
            "reviewed_task_ids": sorted(reviewed | {r.task_id for r in new_results}),
            "completed_task_keys": sorted(completed_keys),
            "reviewed_finding_ids": sorted(seen_findings | {f.finding_id for f in new_findings}),
            "escalated": sorted(outcome.escalated),
            "next_step": outcome.next_step,
            "pending_tasks": [t.model_dump() for t in outcome.tasks],
        }
        if outcome.tasks:
            update["round"] = inp.round + 1
            if any(t.trigger != "retry" for t in outcome.tasks):
                update["replans"] = state.get("replans", 0) + 1
        return update

    def _fulfil_requests(self, results: list[dict]) -> None:
        done = {r["task_id"] for r in results if r.get("status") == "completed"}
        for req in self.s.store.list_requests(self.s.investigation_id, status="accepted"):
            if req.assigned_task_ids and all(t in done for t in req.assigned_task_ids):
                self.s.store.update_request(req.request_id, status="fulfilled")

    async def _coordination(self, agent, label: str, focus: dict | None = None) -> None:
        task = AgentTask(agent=agent.name, objective=label, focus=focus or {}, trigger="initial_plan")
        await run_agent_isolated(self.s, agent, task)

    async def correlate(self, state: InvestigationState) -> dict[str, Any]:
        await self._coordination(CorrelationAgent(), "Correlate findings across agents")
        return {
            "last_correlated_version": self.s.store.blackboard_version(self.s.investigation_id),
            "correlation_rounds": state.get("correlation_rounds", 0) + 1,
        }

    async def verify(self, state: InvestigationState) -> dict[str, Any]:
        rnd = state.get("verification_rounds", 0) + 1
        await self._coordination(VerificationAgent(), f"Red-team verification round {rnd}", {"round": rnd})
        return {"last_verified_version": self.s.store.blackboard_version(self.s.investigation_id), "verification_rounds": rnd}

    async def assess(self, state: InvestigationState) -> dict[str, Any]:
        await self._coordination(RiskAgent(), "Assess and prioritise verified risks")
        return {}

    async def recommend(self, state: InvestigationState) -> dict[str, Any]:
        await self._coordination(RecommendationAgent(), "Generate remediation recommendations")
        return {}

    async def human_review(self, state: InvestigationState) -> dict[str, Any]:
        actions = self.s.store.list_actions(self.s.investigation_id)
        for a in actions:
            self._emit(
                "orchestrator",
                EventType.HUMAN_APPROVAL_REQUIRED,
                f"Human approval required before '{a.title}' ({a.action_type}). Status: ACTION PROPOSED{' (DRY_RUN)' if self.s.settings.dry_run else ''}.",
                receiver="human",
                payload={"action_id": a.action_id, "action_type": a.action_type, "dry_run": self.s.settings.dry_run},
            )
        return {}

    async def finalize(self, state: InvestigationState) -> dict[str, Any]:
        from app.services.coverage import finalize_investigation

        await asyncio.to_thread(finalize_investigation, self.s, state)
        return {}

    # ---------------------------------------------------------------- routing
    @staticmethod
    def _dispatch(state: InvestigationState) -> list[Send] | str:
        tasks = state.get("pending_tasks") or []
        if not tasks:
            return "review"
        return [Send("specialist", {"task": t}) for t in tasks]

    def route_after_prepare(self, state: InvestigationState) -> str:
        return "finalize" if state.get("fatal_error") else "plan"

    def route_after_review(self, state: InvestigationState) -> list[Send] | str:
        step = state.get("next_step", "assess")
        if step == "dispatch":
            return self._dispatch(state)
        return {"correlate": "correlate", "verify": "verify", "assess": "assess", "finalize": "finalize"}.get(step, "assess")

    def build(self):
        g = StateGraph(InvestigationState)
        g.add_node("prepare", self.prepare)
        g.add_node("plan", self.plan)
        g.add_node("specialist", self.specialist, input_schema=SpecialistInput)
        g.add_node("review", self.review)
        g.add_node("correlate", self.correlate)
        g.add_node("verify", self.verify)
        g.add_node("assess", self.assess)
        g.add_node("recommend", self.recommend)
        g.add_node("human_review", self.human_review)
        g.add_node("finalize", self.finalize)
        g.add_edge(START, "prepare")
        g.add_conditional_edges("prepare", self.route_after_prepare, ["plan", "finalize"])
        g.add_conditional_edges("plan", self._dispatch, ["specialist", "review"])
        g.add_edge("specialist", "review")
        g.add_conditional_edges("review", self.route_after_review, ["specialist", "correlate", "verify", "assess", "finalize"])
        g.add_edge("correlate", "review")
        g.add_edge("verify", "review")
        g.add_edge("assess", "recommend")
        g.add_edge("recommend", "human_review")
        g.add_edge("human_review", "finalize")
        g.add_edge("finalize", END)
        return g.compile()

    def mermaid(self) -> str:
        return self.build().get_graph().draw_mermaid()
