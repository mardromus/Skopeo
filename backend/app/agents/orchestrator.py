"""Orchestrator Agent — plans the investigation, reviews the blackboard after every phase and
re-plans adaptively.

It never runs a hard-coded sequence. Each ``review()`` reads structured state (task results,
failures, open investigation requests, new findings, blackboard version, budgets) and decides
— via the LLM in live mode or a transparent policy in mock mode — which follow-ups/retries to
dispatch and which phase comes next. Guardrails validate every decision (known agents, valid
modes, budgets, deduplication) so a manipulated model cannot trigger arbitrary work.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.agents.base import Agent, AgentContext
from app.agents.common import PERFORMANCE_SENSITIVE_PACKAGES
from app.agents.registry import SPECIALIST_CLASSES
from app.schemas import AgentOutcome, AgentTask, EventType, PlanDecision, ReviewDecision, TaskResult
from app.schemas.tasks import FollowUpDecision, PlannedAgent, RequestDecision, RetryDecision, SkippedAgent

NON_RETRYABLE = {"BudgetExceeded", "InvestigationCancelled", "PermissionError", "CommandNotAllowedError"}

ROLE = (
    "You are the Orchestrator of Skopeo, an autonomous team of specialist agents that investigates software "
    "repositories. You decide which specialists to run, when to follow up on evidence, how to handle failures "
    "and when to move to correlation, verification and risk assessment. Prefer evidence over speculation."
)


@dataclass
class ReviewInput:
    round: int
    new_results: list[TaskResult]
    open_requests: list[Any]
    new_findings: list[Any]
    blackboard_version: int
    last_correlated_version: int
    last_verified_version: int
    correlation_rounds: int
    verification_rounds: int
    pending_verification: int
    completed_task_keys: set[str]
    unavailable_agents: set[str]
    deadline_reached: bool
    cancelled: bool
    escalated: set[str] = field(default_factory=set)
    verification_ran: bool = False


@dataclass
class ReviewOutcome:
    tasks: list[AgentTask]
    next_step: str
    decision: ReviewDecision
    decided_by: str
    escalated: set[str]


class OrchestratorAgent(Agent):
    name = "orchestrator"
    display_name = "Orchestrator Agent"
    description = "Plans, monitors, re-plans, handles failures and routes the investigation between phases."

    def run(self, ctx: AgentContext) -> AgentOutcome:  # pragma: no cover - orchestrator is driven by the graph
        raise NotImplementedError

    # ================================================================== PLAN
    def create_plan(self, ctx: AgentContext, depth: str) -> list[AgentTask]:
        profile = ctx.profile
        available = {name: cls.description for name, cls in SPECIALIST_CLASSES.items()}

        def policy() -> PlanDecision:
            return self._rule_plan(profile, depth)

        def validate(plan: PlanDecision) -> PlanDecision:
            seen, agents = set(), []
            for p in plan.agents:
                if p.agent in SPECIALIST_CLASSES and p.agent not in seen:
                    seen.add(p.agent)
                    agents.append(p)
            if not agents:
                raise ValueError("plan selects no known specialist agents")
            plan.agents = agents
            plan.skipped = [s for s in plan.skipped if s.agent in SPECIALIST_CLASSES and s.agent not in seen]
            return plan

        trimmed = {k: v for k, v in profile.items() if k not in ("test_files", "manifests", "entrypoints", "benchmark_scripts")}
        trimmed["manifests"] = profile.get("manifests", [])[:10]
        decision = ctx.decide(
            "orchestrator.plan",
            PlanDecision,
            policy,
            role=ROLE,
            task="Create the initial investigation plan: select the specialist agents that are relevant for this repository and justify each choice and each skip.",
            structured={"repository_profile": trimmed, "analysis_depth": depth, "available_agents": available},
            tier="reasoning",
            validate=validate,
        )
        plan = decision.value
        tasks = [
            AgentTask(agent=p.agent, objective=p.objective, priority=p.priority, rationale=p.rationale, trigger="initial_plan", round=1)
            for p in sorted(plan.agents, key=lambda p: p.priority)
        ]
        ctx.store.update_investigation(
            ctx.investigation_id,
            plan={
                "assessment": plan.repository_assessment,
                "rationale": plan.rationale,
                "decided_by": decision.decided_by,
                "initial_tasks": [t.model_dump() for t in tasks],
                "skipped": [s.model_dump() for s in plan.skipped],
                "parallel_groups": plan.parallel_groups,
                "revisions": [],
            },
        )
        ctx.message(
            "blackboard",
            plan.repository_assessment,
            payload={"profile_summary": {k: profile.get(k) for k in ("primary_language", "ecosystems", "file_count", "test_file_count")}},
        )
        ctx.emit(
            EventType.PLAN_CREATED,
            f"Plan created: {len(tasks)} specialist(s) in parallel — "
            + ", ".join(t.agent for t in tasks)
            + (f"; skipped {', '.join(s.agent for s in plan.skipped)}" if plan.skipped else ""),
            receiver="all_agents",
            payload={
                "tasks": [{"agent": t.agent, "objective": t.objective, "priority": t.priority, "rationale": t.rationale} for t in tasks],
                "skipped": [s.model_dump() for s in plan.skipped],
                "decided_by": decision.decided_by,
                "rationale": plan.rationale,
            },
        )
        return tasks

    def _rule_plan(self, profile: dict[str, Any], depth: str) -> PlanDecision:
        lang = profile.get("primary_language") or "unknown-language"
        ecos = profile.get("ecosystems") or []
        src = profile.get("source_file_count", 0)
        tests = profile.get("test_file_count", 0)
        agents: list[PlannedAgent] = []
        skipped: list[SkippedAgent] = []
        assessment = (
            f"Repository detected as {lang} project ({src} source files, {tests} test files"
            + (f", ecosystems: {', '.join(ecos)}" if ecos else ", no dependency manifests")
            + (
                f", {profile.get('git_commits_available', 0)} commit(s) of history"
                if profile.get("has_git_history")
                else ", no git history"
            )
            + ")."
        )
        if src:
            agents.append(
                PlannedAgent(
                    agent="security_agent",
                    objective="Find secrets, insecure patterns and prompt-injection content",
                    priority=1,
                    rationale=f"{src} source files must be checked for secrets and insecure patterns",
                )
            )
        if ecos:
            agents.append(
                PlannedAgent(
                    agent="dependency_agent",
                    objective=f"Assess dependency health for {', '.join(ecos)}",
                    priority=1,
                    rationale=f"Manifests found ({', '.join(profile.get('manifests', [])[:4])})",
                )
            )
        else:
            skipped.append(SkippedAgent(agent="dependency_agent", reason="no dependency manifests detected"))
        if src:
            agents.append(
                PlannedAgent(
                    agent="test_reliability_agent",
                    objective="Assess test coverage and reliability"
                    + (" (execute suite)" if profile.get("trusted_execution") else " (static only)"),
                    priority=2,
                    rationale=f"{tests} test files; execution {'permitted' if profile.get('trusted_execution') else 'not permitted for untrusted code'}",
                )
            )
            agents.append(
                PlannedAgent(
                    agent="code_quality_agent",
                    objective="Measure maintainability and code smells",
                    priority=3,
                    rationale="Deterministic AST metrics are cheap and broadly useful",
                )
            )
        if profile.get("python_packages") or "npm" in ecos or depth == "deep":
            agents.append(
                PlannedAgent(
                    agent="api_compatibility_agent",
                    objective="Review public API surface, deprecations and breaking changes",
                    priority=2,
                    rationale=f"importable package(s): {', '.join(profile.get('python_packages') or []) or 'npm package'}",
                )
            )
        else:
            skipped.append(SkippedAgent(agent="api_compatibility_agent", reason="no importable package / public API detected"))
        agents.append(
            PlannedAgent(
                agent="license_agent",
                objective="Check license and dependency license compliance",
                priority=3,
                rationale="license file present" if profile.get("has_license_file") else "no license file — compliance gap must be checked",
            )
        )
        if profile.get("has_git_history") or profile.get("github_metadata_available"):
            agents.append(
                PlannedAgent(
                    agent="maintenance_agent",
                    objective="Assess maintenance activity",
                    priority=3,
                    rationale="git history / GitHub metadata available",
                )
            )
        else:
            skipped.append(SkippedAgent(agent="maintenance_agent", reason="no git history and no GitHub metadata"))
        if profile.get("uses_database") or profile.get("uses_network_calls") or depth == "deep":
            agents.append(
                PlannedAgent(
                    agent="performance_agent",
                    objective="Find performance bottlenecks (static + benchmarks)",
                    priority=2,
                    rationale="database access and/or network calls detected" if depth != "deep" else "deep analysis requested",
                )
            )
        else:
            skipped.append(SkippedAgent(agent="performance_agent", reason="no database or network hot paths detected"))
        if depth == "quick":
            keep = {"security_agent", "dependency_agent", "test_reliability_agent"}
            skipped += [SkippedAgent(agent=a.agent, reason="analysis_depth=quick") for a in agents if a.agent not in keep]
            agents = [a for a in agents if a.agent in keep]
        return PlanDecision(
            repository_assessment=assessment,
            agents=agents,
            skipped=skipped,
            parallel_groups=[[a.agent for a in agents]],
            rationale="All selected specialists are independent and run in parallel; follow-ups are decided after reviewing their evidence.",
        )

    # ================================================================ REVIEW
    def review(self, ctx: AgentContext, inp: ReviewInput) -> ReviewOutcome:
        structured = {
            "round": inp.round,
            "max_rounds": ctx.settings.max_orchestrator_rounds,
            "task_results": [r.model_dump() for r in inp.new_results],
            "open_requests": [
                {
                    "request_id": r.request_id,
                    "requested_by": r.requested_by,
                    "target_agent": r.target_agent,
                    "required_evidence": r.required_evidence,
                    "objective": r.objective,
                    "focus": r.focus,
                }
                for r in inp.open_requests
            ],
            "new_findings": [
                {
                    "id": f.finding_id,
                    "agent": f.agent,
                    "rule": f.rule_id,
                    "severity": f.severity.value,
                    "title": f.title,
                    "package": f.attributes.get("package"),
                }
                for f in inp.new_findings[:40]
            ],
            "blackboard_version": inp.blackboard_version,
            "last_correlated_version": inp.last_correlated_version,
            "pending_verification": inp.pending_verification,
            "verification_rounds": inp.verification_rounds,
            "unavailable_agents": sorted(inp.unavailable_agents),
            "agent_modes": {n: list(c.modes) for n, c in SPECIALIST_CLASSES.items()},
        }
        policy_result: dict[str, Any] = {}

        def policy() -> ReviewDecision:
            decision, escalated = self._rule_review(ctx, inp)
            policy_result["escalated"] = escalated
            return decision

        def validate(d: ReviewDecision) -> ReviewDecision:
            ids = {r.request_id for r in inp.open_requests}
            d.follow_ups = [
                f
                for f in d.follow_ups
                if f.agent in SPECIALIST_CLASSES
                and f.mode in SPECIALIST_CLASSES[f.agent].modes
                and (f.request_id is None or f.request_id in ids)
            ]
            d.request_decisions = [r for r in d.request_decisions if r.request_id in ids]
            d.retries = [r for r in d.retries if r.task_id in {x.task_id for x in inp.new_results}]
            return d

        decision = ctx.decide(
            "orchestrator.review",
            ReviewDecision,
            policy,
            role=ROLE,
            task="Review the latest results and blackboard state. Decide retries, which investigation requests to accept, follow-up tasks, and the next phase (dispatch/correlate/verify/assess/finalize).",
            structured=structured,
            tier="reasoning",
            validate=validate,
        )
        d = decision.value
        escalated = policy_result.get("escalated", inp.escalated)
        tasks = self._materialise(ctx, inp, d)
        next_step = self._guard_next_step(ctx, inp, d.next_step, tasks)
        if next_step != d.next_step:
            ctx.message(
                "blackboard", f"Guardrail adjusted next step {d.next_step} -> {next_step}", payload={"reason": "budget/state invariant"}
            )
        ctx.emit(
            EventType.ORCHESTRATOR_DECISION,
            f"Review round {inp.round}: {d.assessment} Next: {next_step}.",
            receiver="all_agents",
            payload={
                "next_step": next_step,
                "rationale": d.rationale,
                "decided_by": decision.decided_by,
                "new_tasks": [t.agent + ":" + t.mode for t in tasks],
            },
        )
        return ReviewOutcome(tasks=tasks, next_step=next_step, decision=d, decided_by=decision.decided_by, escalated=set(escalated))

    def _rule_review(self, ctx: AgentContext, inp: ReviewInput) -> tuple[ReviewDecision, set[str]]:
        retries: list[RetryDecision] = []
        follow_ups: list[FollowUpDecision] = []
        req_decisions: list[RequestDecision] = []
        notes: list[str] = []
        escalated = set(inp.escalated)
        if inp.cancelled:
            declined = [
                RequestDecision(request_id=r.request_id, accept=False, rationale="investigation cancelled") for r in inp.open_requests
            ]
            return ReviewDecision(
                assessment="cancellation requested — stopping",
                request_decisions=declined,
                next_step="finalize",
                rationale=self._rationale("finalize", inp),
            ), escalated
        failed = [r for r in inp.new_results if r.status in ("failed", "timeout")]
        for r in failed:
            cls = SPECIALIST_CLASSES.get(r.agent)
            retryable = (
                cls is not None
                and r.retryable
                and (r.error_type or "") not in NON_RETRYABLE
                and r.attempt <= ctx.settings.agent_max_retries
            )
            if retryable:
                strategy = cls().fallback_strategy(r.error_type or "", r.strategy) or r.strategy
                retries.append(
                    RetryDecision(
                        task_id=r.task_id,
                        agent=r.agent,
                        retry=True,
                        strategy=strategy,
                        rationale=f"{r.error_type}: {r.error_message}; retry {r.attempt + 1} with strategy '{strategy}'",
                    )
                )
                notes.append(f"{r.agent} failed ({r.error_type}); retrying with '{strategy}'")
            else:
                retries.append(
                    RetryDecision(
                        task_id=r.task_id, agent=r.agent, retry=False, rationale=f"{r.error_type}: not retryable or retry budget exhausted"
                    )
                )
                notes.append(f"{r.agent} unavailable — continuing with remaining agents")
        budget_left = inp.round < ctx.settings.max_orchestrator_rounds and not inp.deadline_reached
        for req in inp.open_requests:
            if not budget_left:
                req_decisions.append(RequestDecision(request_id=req.request_id, accept=False, rationale="round/time budget exhausted"))
                continue
            plans = self._plan_for_request(req, inp)
            if not plans:
                req_decisions.append(
                    RequestDecision(
                        request_id=req.request_id,
                        accept=False,
                        rationale=f"no specialist can provide '{req.required_evidence}' or target unavailable",
                    )
                )
                continue
            fresh = [p for p in plans if self._key(p) not in inp.completed_task_keys]
            if not fresh:
                req_decisions.append(
                    RequestDecision(request_id=req.request_id, accept=False, rationale="equivalent investigation already performed")
                )
                continue
            req_decisions.append(
                RequestDecision(
                    request_id=req.request_id, accept=True, rationale=f"assigning {', '.join(p.agent + ':' + p.mode for p in fresh)}"
                )
            )
            follow_ups.extend(fresh)
            if req.focus.get("package"):
                escalated.add(f"pkg:{req.focus['package']}")
        # Proactive escalation: high-impact vulnerable dependencies nobody asked about yet.
        for f in inp.new_findings:
            pkg = f.attributes.get("package")
            if (
                budget_left
                and f.rule_id == "dependency.vulnerable"
                and f.severity.value in ("critical", "high")
                and f"pkg:{pkg}" not in escalated
            ):
                fake_req = type(
                    "R",
                    (),
                    {
                        "required_evidence": "impact_analysis",
                        "focus": {
                            "package": pkg,
                            "import_name": f.attributes.get("import_name"),
                            "current_version": f.attributes.get("version"),
                            "target_version": f.attributes.get("fixed_version"),
                            "finding_id": f.finding_id,
                        },
                        "target_agent": None,
                        "request_id": None,
                    },
                )()
                for p in self._plan_for_request(fake_req, inp):
                    if self._key(p) not in inp.completed_task_keys:
                        p.rationale = f"orchestrator escalation after {f.agent} finding '{f.title}'"
                        follow_ups.append(p)
                escalated.add(f"pkg:{pkg}")
        follow_ups = follow_ups[: ctx.settings.max_followups_per_round]
        if retries and any(r.retry for r in retries) or follow_ups:
            next_step = "dispatch"
        elif inp.cancelled:
            next_step = "finalize"
        elif inp.blackboard_version > inp.last_correlated_version and inp.correlation_rounds < ctx.settings.max_correlation_rounds:
            next_step = "correlate"
        elif inp.pending_verification and inp.verification_rounds < ctx.settings.max_verification_rounds:
            next_step = "verify"
        else:
            next_step = "assess"
        assessment = "; ".join(notes) or (
            f"{len(inp.new_results)} task(s) completed, {len(inp.new_findings)} new finding(s)" if inp.new_results else "phase complete"
        )
        if follow_ups:
            assessment += f"; {len(follow_ups)} follow-up(s) scheduled"
        return (
            ReviewDecision(
                assessment=assessment,
                retries=retries,
                request_decisions=req_decisions,
                follow_ups=follow_ups,
                next_step=next_step,
                rationale=self._rationale(next_step, inp),
            ),
            escalated,
        )

    def _plan_for_request(self, req: Any, inp: ReviewInput) -> list[FollowUpDecision]:
        focus = dict(req.focus or {})
        kind = req.required_evidence
        out: list[FollowUpDecision] = []

        def add(agent: str, mode: str, objective: str, rationale: str, trigger: str = "follow_up") -> None:
            if agent in inp.unavailable_agents:
                return
            out.append(
                FollowUpDecision(
                    agent=agent,
                    objective=objective,
                    mode=mode,
                    focus=focus,
                    trigger=trigger,
                    request_id=req.request_id,
                    rationale=rationale,
                )
            )  # type: ignore[arg-type]

        pkg = focus.get("package")
        if kind == "impact_analysis" and pkg:
            add(
                "security_agent",
                "dependency_usage",
                f"Inspect how {pkg} is used and whether it reaches security-critical code",
                f"vulnerable {pkg}: is it actually used, and where?",
            )
            if focus.get("target_version"):
                add(
                    "api_compatibility_agent",
                    "upgrade_compatibility",
                    f"Check whether upgrading {pkg} {focus.get('current_version')} -> {focus.get('target_version')} breaks APIs",
                    "the fix is an upgrade; is it drop-in?",
                )
            add(
                "test_reliability_agent",
                "dependency_coverage",
                f"Identify tests covering code that uses {pkg}",
                "an upgrade is only safe if the affected code is tested",
            )
            if pkg.lower() in PERFORMANCE_SENSITIVE_PACKAGES:
                add(
                    "performance_agent",
                    "full",
                    f"Check whether {pkg} sits on performance-sensitive paths",
                    f"{pkg} is performance-sensitive",
                )
        elif kind == "benchmark":
            add(
                "performance_agent",
                "benchmark",
                req.objective if hasattr(req, "objective") else "Run benchmark",
                "red-team requires measurement to verify the claim",
                trigger="verification_request",
            )
        elif kind == "usage_analysis" and pkg:
            add("security_agent", "dependency_usage", f"Trace usage of {pkg}", "usage analysis requested")
        elif kind == "upgrade_compatibility" and pkg:
            add("api_compatibility_agent", "upgrade_compatibility", f"Upgrade compatibility for {pkg}", "requested")
        elif kind == "test_coverage" and pkg:
            add("test_reliability_agent", "dependency_coverage", f"Coverage of {pkg} usage", "requested")
        elif getattr(req, "target_agent", None) in SPECIALIST_CLASSES:
            add(req.target_agent, "full", getattr(req, "objective", "follow-up"), "targeted request")
        return out

    @staticmethod
    def _key(f: FollowUpDecision) -> str:
        return AgentTask(agent=f.agent, objective=f.objective, mode=f.mode, strategy=f.strategy, focus=f.focus).dedup_key()

    @staticmethod
    def _rationale(step: str, inp: ReviewInput) -> str:
        return {
            "dispatch": "new evidence or failures require further specialist work before cross-agent reasoning",
            "correlate": f"blackboard changed (version {inp.last_correlated_version} -> {inp.blackboard_version}); relationships must be re-evaluated",
            "verify": f"{inp.pending_verification} finding(s) not yet challenged by the red-team",
            "assess": "all findings have been challenged (or budgets exhausted); only verified evidence enters risk assessment",
            "finalize": "investigation stopped",
        }[step]

    def _guard_next_step(self, ctx: AgentContext, inp: ReviewInput, step: str, tasks: list[AgentTask]) -> str:
        if inp.cancelled:
            return "finalize"
        if step == "dispatch" and not tasks:
            step = (
                "correlate" if inp.blackboard_version > inp.last_correlated_version else "verify" if inp.pending_verification else "assess"
            )
        if inp.deadline_reached and step in ("dispatch", "correlate"):
            return "verify" if inp.pending_verification and inp.verification_rounds < ctx.settings.max_verification_rounds else "assess"
        if step == "verify" and inp.verification_rounds >= ctx.settings.max_verification_rounds:
            return "assess"
        if step == "correlate" and inp.correlation_rounds >= ctx.settings.max_correlation_rounds:
            return "verify" if inp.pending_verification and inp.verification_rounds < ctx.settings.max_verification_rounds else "assess"
        if (
            step == "assess"
            and inp.pending_verification
            and not inp.verification_ran
            and inp.verification_rounds < ctx.settings.max_verification_rounds
        ):
            return "verify"
        return step

    def _materialise(self, ctx: AgentContext, inp: ReviewInput, d: ReviewDecision) -> list[AgentTask]:
        tasks: list[AgentTask] = []
        results = {r.task_id: r for r in inp.new_results}
        for retry in d.retries:
            r = results.get(retry.task_id)
            if not r:
                continue
            if retry.retry:
                t = AgentTask(
                    agent=r.agent,
                    objective=f"Retry: {r.agent} ({retry.strategy})",
                    mode=r.mode,
                    strategy=retry.strategy,
                    attempt=r.attempt + 1,
                    trigger="retry",
                    round=inp.round + 1,
                    rationale=retry.rationale,
                )
                tasks.append(t)
                ctx.emit(
                    EventType.AGENT_RETRY_SCHEDULED,
                    f"{r.agent} FAILED -> RETRYING (attempt {t.attempt}, strategy '{t.strategy}'): {retry.rationale}",
                    receiver=r.agent,
                    payload={"task_id": t.task_id, "previous_task_id": r.task_id, "strategy": t.strategy, "attempt": t.attempt},
                    severity="warning",
                )
            else:
                ctx.message(
                    "all_agents",
                    f"{r.agent.replace('_', ' ').title()} investigation unavailable ({r.error_type}). Continuing with the remaining agents; coverage will be reported as partial.",
                    payload={"agent": r.agent, "error": r.error_message},
                    severity="warning",
                )
        for rd in d.request_decisions:
            ctx.store.update_request(rd.request_id, status="accepted" if rd.accept else "declined", decision_reason=rd.rationale)
        by_request: dict[str, list[str]] = {}
        for f in d.follow_ups:
            t = AgentTask(
                agent=f.agent,
                objective=f.objective,
                mode=f.mode,
                strategy=f.strategy,
                focus=f.focus,
                trigger=f.trigger,
                round=inp.round + 1,
                parent_request_id=f.request_id,
                rationale=f.rationale,
            )
            if t.dedup_key() in inp.completed_task_keys:
                continue
            twin = next((x for x in tasks if x.dedup_key() == t.dedup_key()), None)
            if twin is not None:
                if f.request_id:
                    by_request.setdefault(f.request_id, []).append(twin.task_id)
                continue
            tasks.append(t)
            if f.request_id:
                by_request.setdefault(f.request_id, []).append(t.task_id)
        for rid, task_ids in by_request.items():
            ctx.store.update_request(rid, assigned_task_ids=task_ids)
        for rd in d.request_decisions:
            req = next((r for r in inp.open_requests if r.request_id == rd.request_id), None)
            if req:
                ctx.emit(
                    EventType.REQUEST_DECIDED,
                    f"{'Accepted' if rd.accept else 'Declined'} request from {req.requested_by}: {rd.rationale}",
                    receiver=req.requested_by,
                    payload={"request_id": rd.request_id, "accepted": rd.accept},
                )
        follow = [t for t in tasks if t.trigger != "retry"]
        if follow:
            inv = ctx.store.get_investigation(ctx.investigation_id)
            plan = dict(inv.plan or {}) if inv else {}
            revisions = list(plan.get("revisions", []))
            revisions.append(
                {
                    "round": inp.round + 1,
                    "at": time.time(),
                    "added": [{"agent": t.agent, "mode": t.mode, "objective": t.objective, "rationale": t.rationale} for t in follow],
                }
            )
            plan["revisions"] = revisions
            ctx.store.update_investigation(ctx.investigation_id, plan=plan)
            reasons = sorted({t.rationale for t in follow})
            perf_note = ""
            pkgs = {t.focus.get("package") for t in follow if t.focus.get("package")}
            for pkg in pkgs:
                if pkg and pkg.lower() not in PERFORMANCE_SENSITIVE_PACKAGES and any(t.mode == "dependency_usage" for t in follow):
                    perf_note = f"; performance follow-up not required ({pkg} is not on a performance-sensitive path)"
            ctx.emit(
                EventType.REPLAN,
                "Replanned: " + ", ".join(f"+{t.agent} ({t.mode})" for t in follow) + perf_note,
                receiver="all_agents",
                payload={"round": inp.round + 1, "added_tasks": [t.model_dump() for t in follow], "reasons": reasons},
            )
        return tasks
