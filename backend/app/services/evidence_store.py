"""The Evidence Store — Skopeo's shared blackboard.

All agents read and write investigation knowledge exclusively through this class. It is backed
by the relational database (not in-memory dicts), returns detached Pydantic DTOs, and serialises
writes so parallel agents can safely publish at the same time.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.database import session_scope
from app.models import (
    ActionProposal,
    AgentRun,
    Correlation,
    Evidence,
    ExecutionEvent,
    Finding,
    Investigation,
    InvestigationRequest,
    Recommendation,
    RiskAssessment,
    Verification,
    utcnow,
)
from app.schemas import (
    AgentTask,
    CorrelationDraft,
    CorrelationOut,
    EvidenceDraft,
    EvidenceOut,
    FindingDraft,
    FindingOut,
    VerificationDraft,
    VerificationOut,
)
from app.schemas.investigation import (
    ActionProposalOut,
    AgentRunOut,
    ExecutionEventOut,
    InvestigationRequestOut,
    RecommendationOut,
    RiskOut,
)
from app.security.redaction import redact, redact_obj
from app.services.confidence import ConfidenceInputs, compute_confidence


class MissingEvidenceError(ValueError):
    """Raised when an agent tries to publish a non-hypothesis finding without evidence."""


# ---------------------------------------------------------------- serializers
def _evidence_out(e: Evidence) -> EvidenceOut:
    return EvidenceOut(
        evidence_id=e.id,
        finding_id=e.finding_id,
        source_type=e.source_type,
        source=e.source,
        file=e.file,
        line_start=e.line_start,
        line_end=e.line_end,
        excerpt=e.excerpt,
        tool=e.tool,
        raw_reference=e.raw_reference,
        confidence=e.confidence,
        created_by=e.created_by,
        content_hash=e.content_hash,
        data=e.data or {},
        created_at=e.created_at,
    )


def _finding_out(f: Finding, evidence_ids: list[str]) -> FindingOut:
    return FindingOut(
        finding_id=f.id,
        agent=f.agent,
        category=f.category,
        rule_id=f.rule_id,
        title=f.title,
        description=f.description,
        severity=f.severity,
        confidence=f.confidence,
        confidence_factors=f.confidence_factors or [],
        status=f.status,
        subject=f.subject,
        affected_files=f.affected_files or [],
        affected_components=f.affected_components or [],
        evidence_ids=evidence_ids,
        tool_results=f.tool_results or [],
        attributes=f.attributes or {},
        reasoning_summary=f.reasoning_summary,
        recommended_action=f.recommended_action,
        is_hypothesis=f.is_hypothesis,
        agent_run_id=f.agent_run_id,
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


def _correlation_out(c: Correlation) -> CorrelationOut:
    return CorrelationOut(
        correlation_id=c.id,
        finding_ids=c.finding_ids or [],
        relationship_type=c.relationship_type,
        title=c.title,
        description=c.description,
        risk_multiplier=c.risk_multiplier,
        confidence=c.confidence,
        status=c.status,
        links=c.links or [],
        reasoning_summary=c.reasoning_summary,
        resolution=c.resolution,
        signature=c.signature,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _verification_out(v: Verification) -> VerificationOut:
    return VerificationOut(
        verification_id=v.id,
        finding_id=v.finding_id,
        correlation_id=v.correlation_id,
        round=v.round,
        decision=v.decision,
        confidence=v.confidence,
        challenge=v.challenge,
        checks=v.checks or [],
        evidence_checked=v.evidence_checked or [],
        additional_tests=v.additional_tests or [],
        counter_evidence=v.counter_evidence or [],
        adjusted_severity=v.adjusted_severity,
        reasoning_summary=v.reasoning_summary,
        decided_by=v.decided_by,
        verified_at=v.verified_at,
    )


def _run_out(r: AgentRun) -> AgentRunOut:
    return AgentRunOut(
        run_id=r.id,
        agent=r.agent,
        task_id=r.task_id,
        objective=r.objective,
        mode=r.mode,
        strategy=r.strategy,
        attempt=r.attempt,
        trigger=r.trigger,
        round=r.round,
        parent_request_id=r.parent_request_id,
        status=r.status,
        started_at=r.started_at,
        completed_at=r.completed_at,
        duration_ms=r.duration_ms,
        iterations=r.iterations,
        tool_calls=r.tool_calls,
        llm_calls=r.llm_calls,
        findings_count=r.findings_count,
        error_type=r.error_type,
        error_message=r.error_message,
        summary=r.summary,
        coverage=r.coverage or {},
    )


def _request_out(r: InvestigationRequest) -> InvestigationRequestOut:
    return InvestigationRequestOut(
        request_id=r.id,
        requested_by=r.requested_by,
        target_agent=r.target_agent,
        objective=r.objective,
        reason=r.reason,
        required_evidence=r.required_evidence,
        focus=r.focus or {},
        related_finding_ids=r.related_finding_ids or [],
        status=r.status,
        decision_reason=r.decision_reason,
        assigned_task_ids=r.assigned_task_ids or [],
        created_at=r.created_at,
        resolved_at=r.resolved_at,
    )


def _risk_out(r: RiskAssessment) -> RiskOut:
    return RiskOut(
        risk_id=r.id,
        finding_id=r.finding_id,
        correlation_id=r.correlation_id,
        kind=r.kind,
        title=r.title,
        category=r.category,
        severity=r.severity,
        score=r.score,
        priority=r.priority,
        confidence=r.confidence,
        impact=r.impact,
        exploitability=r.exploitability,
        correlation_multiplier=r.correlation_multiplier,
        factors=r.factors or {},
        member_finding_ids=r.member_finding_ids or [],
        rationale=r.rationale,
        created_at=r.created_at,
    )


def _recommendation_out(r: Recommendation) -> RecommendationOut:
    return RecommendationOut(
        recommendation_id=r.id,
        risk_id=r.risk_id,
        finding_ids=r.finding_ids or [],
        title=r.title,
        problem=r.problem,
        affected_component=r.affected_component,
        why_it_matters=r.why_it_matters,
        proposed_fix=r.proposed_fix,
        estimated_risk=r.estimated_risk or {},
        verification_status=r.verification_status,
        expected_benefit=r.expected_benefit,
        implementation_difficulty=r.implementation_difficulty,
        priority=r.priority,
        created_at=r.created_at,
    )


def _action_out(a: ActionProposal) -> ActionProposalOut:
    return ActionProposalOut(
        action_id=a.id,
        recommendation_id=a.recommendation_id,
        action_type=a.action_type,
        title=a.title,
        body=a.body,
        patch=a.patch,
        target_repository=a.target_repository,
        status=a.status,
        requires_approval=a.requires_approval,
        approved_by=a.approved_by,
        decision_note=a.decision_note,
        result=a.result or {},
        risk_score=a.risk_score,
        created_at=a.created_at,
        decided_at=a.decided_at,
    )


def _event_out(e: ExecutionEvent) -> ExecutionEventOut:
    return ExecutionEventOut(
        event_id=e.id,
        investigation_id=e.investigation_id,
        seq=e.seq,
        sender=e.sender,
        receiver=e.receiver,
        event_type=e.event_type,
        severity=e.severity,
        message=e.message,
        correlation_id=e.correlation_id,
        payload=e.payload or {},
        timestamp=e.timestamp,
    )


class EvidenceStore:
    # ----------------------------------------------------------- investigations
    def create_investigation(self, **fields: Any) -> str:
        with session_scope(write=True) as s:
            inv = Investigation(**fields)
            s.add(inv)
            s.flush()
            return inv.id

    def get_investigation(self, investigation_id: str) -> Investigation | None:
        with session_scope() as s:
            inv = s.get(Investigation, investigation_id)
            if inv is not None:
                s.expunge(inv)
            return inv

    def list_investigations(self, limit: int = 50) -> list[Investigation]:
        with session_scope() as s:
            rows = list(s.scalars(select(Investigation).order_by(Investigation.created_at.desc()).limit(limit)))
            for r in rows:
                s.expunge(r)
            return rows

    def update_investigation(self, investigation_id: str, **fields: Any) -> None:
        with session_scope(write=True) as s:
            inv = s.get(Investigation, investigation_id)
            if inv is None:
                raise KeyError(investigation_id)
            for k, v in fields.items():
                setattr(inv, k, v)

    def is_cancel_requested(self, investigation_id: str) -> bool:
        with session_scope() as s:
            return bool(s.scalar(select(Investigation.cancel_requested).where(Investigation.id == investigation_id)))

    # --------------------------------------------------------------- agent runs
    def create_agent_run(self, investigation_id: str, task: AgentTask) -> str:
        with session_scope(write=True) as s:
            run = AgentRun(
                investigation_id=investigation_id,
                agent=task.agent,
                task_id=task.task_id,
                objective=task.objective,
                mode=task.mode,
                strategy=task.strategy,
                attempt=task.attempt,
                trigger=task.trigger,
                round=task.round,
                parent_request_id=task.parent_request_id,
                status="pending",
            )
            s.add(run)
            s.flush()
            return run.id

    def start_agent_run(self, run_id: str) -> None:
        with session_scope(write=True) as s:
            run = s.get(AgentRun, run_id)
            run.status = "running"
            run.started_at = utcnow()

    def finish_agent_run(self, run_id: str, status: str, **fields: Any) -> AgentRunOut:
        with session_scope(write=True) as s:
            run = s.get(AgentRun, run_id)
            run.status = status
            run.completed_at = utcnow()
            if run.started_at:
                started = run.started_at if run.started_at.tzinfo else run.started_at.replace(tzinfo=run.completed_at.tzinfo)
                run.duration_ms = int((run.completed_at - started).total_seconds() * 1000)
            for k, v in fields.items():
                setattr(run, k, redact(v) if isinstance(v, str) else v)
            s.flush()
            return _run_out(run)

    def list_agent_runs(self, investigation_id: str) -> list[AgentRunOut]:
        with session_scope() as s:
            rows = s.scalars(select(AgentRun).where(AgentRun.investigation_id == investigation_id).order_by(AgentRun.created_at))
            return [_run_out(r) for r in rows]

    def increment_run_findings(self, run_id: str | None) -> None:
        if not run_id:
            return
        with session_scope(write=True) as s:
            run = s.get(AgentRun, run_id)
            if run:
                run.findings_count = (run.findings_count or 0) + 1

    # ------------------------------------------------------------------ findings
    def add_finding(
        self,
        investigation_id: str,
        agent: str,
        run_id: str | None,
        draft: FindingDraft,
        evidence: list[EvidenceDraft],
        content_hashes: list[str | None] | None = None,
    ) -> FindingOut:
        if not evidence and not draft.is_hypothesis:
            raise MissingEvidenceError(f"finding '{draft.title}' has no evidence and is not marked as a hypothesis")
        attrs = dict(draft.attributes)
        conf_inputs = attrs.setdefault("confidence_inputs", {})
        if draft.category == "performance" and attrs.get("measurement") == "static_suspect":
            conf_inputs["static_suspect"] = True
        result = compute_confidence(
            ConfidenceInputs(
                evidence=[(e.source_type.value, e.confidence) for e in evidence],
                is_hypothesis=draft.is_hypothesis,
                **{k: v for k, v in conf_inputs.items() if k in ConfidenceInputs.__dataclass_fields__ and k != "evidence"},
            )
        )
        with session_scope(write=True) as s:
            f = Finding(
                investigation_id=investigation_id,
                agent=agent,
                agent_run_id=run_id,
                category=draft.category.value,
                rule_id=draft.rule_id,
                title=redact(draft.title),
                description=redact(draft.description),
                severity=draft.severity.value,
                confidence=result.score,
                confidence_factors=result.factors,
                status="proposed",
                subject=draft.subject,
                affected_files=draft.affected_files,
                affected_components=draft.affected_components,
                attributes=redact_obj(attrs),
                tool_results=redact_obj(draft.tool_results),
                reasoning_summary=redact(draft.reasoning_summary),
                recommended_action=redact(draft.recommended_action),
                is_hypothesis=draft.is_hypothesis,
            )
            s.add(f)
            s.flush()
            ids = []
            for i, ev in enumerate(evidence):
                row = self._evidence_row(investigation_id, f.id, agent, ev, (content_hashes or [None] * len(evidence))[i])
                s.add(row)
                s.flush()
                ids.append(row.id)
            out = _finding_out(f, ids)
        self.increment_run_findings(run_id)
        return out

    @staticmethod
    def _evidence_row(
        investigation_id: str, finding_id: str | None, created_by: str, ev: EvidenceDraft, content_hash: str | None
    ) -> Evidence:
        return Evidence(
            investigation_id=investigation_id,
            finding_id=finding_id,
            created_by=created_by,
            source_type=ev.source_type.value,
            source=redact(ev.source),
            file=ev.file,
            line_start=ev.line_start,
            line_end=ev.line_end,
            excerpt=redact(ev.excerpt),
            tool=ev.tool,
            raw_reference=redact(ev.raw_reference),
            content_hash=content_hash,
            confidence=ev.confidence,
            data=redact_obj(ev.data),
        )

    def add_evidence(
        self, investigation_id: str, finding_id: str | None, created_by: str, draft: EvidenceDraft, content_hash: str | None = None
    ) -> EvidenceOut:
        with session_scope(write=True) as s:
            row = self._evidence_row(investigation_id, finding_id, created_by, draft, content_hash)
            s.add(row)
            s.flush()
            return _evidence_out(row)

    def get_finding(self, finding_id: str) -> FindingOut | None:
        with session_scope() as s:
            f = s.get(Finding, finding_id)
            if f is None:
                return None
            ids = list(s.scalars(select(Evidence.id).where(Evidence.finding_id == finding_id).order_by(Evidence.created_at)))
            return _finding_out(f, ids)

    def update_finding(self, finding_id: str, **fields: Any) -> FindingOut:
        with session_scope(write=True) as s:
            f = s.get(Finding, finding_id)
            if f is None:
                raise KeyError(finding_id)
            for k, v in fields.items():
                if k == "attributes":
                    merged = dict(f.attributes or {})
                    merged.update(v)
                    v = redact_obj(merged)
                setattr(f, k, v)
            f.updated_at = utcnow()
        out = self.get_finding(finding_id)
        assert out is not None
        return out

    def recompute_confidence(self, finding_id: str, **inputs: Any) -> FindingOut:
        """Recompute a finding's confidence from all of its evidence plus recorded context."""
        with session_scope() as s:
            f = s.get(Finding, finding_id)
            evidence = list(s.scalars(select(Evidence).where(Evidence.finding_id == finding_id)))
            attrs = dict(f.attributes or {})
        conf_inputs = dict(attrs.get("confidence_inputs") or {})
        conf_inputs.update({k: v for k, v in inputs.items() if v is not None})
        attrs["confidence_inputs"] = conf_inputs
        result = compute_confidence(
            ConfidenceInputs(
                evidence=[(e.source_type, e.confidence) for e in evidence],
                is_hypothesis=f.is_hypothesis,
                **{k: v for k, v in conf_inputs.items() if k in ConfidenceInputs.__dataclass_fields__ and k != "evidence"},
            )
        )
        return self.update_finding(finding_id, confidence=result.score, confidence_factors=result.factors, attributes=attrs)

    def list_findings(
        self,
        investigation_id: str,
        *,
        status: str | list[str] | None = None,
        severity: str | None = None,
        category: str | None = None,
        agent: str | None = None,
        min_confidence: float | None = None,
        file: str | None = None,
    ) -> list[FindingOut]:
        with session_scope() as s:
            q = select(Finding).where(Finding.investigation_id == investigation_id)
            if status:
                q = q.where(Finding.status.in_([status] if isinstance(status, str) else status))
            if severity:
                q = q.where(Finding.severity == severity)
            if category:
                q = q.where(Finding.category == category)
            if agent:
                q = q.where(Finding.agent == agent)
            if min_confidence is not None:
                q = q.where(Finding.confidence >= min_confidence)
            rows = list(s.scalars(q.order_by(Finding.created_at)))
            ev_map: dict[str, list[str]] = defaultdict(list)
            for fid, eid in s.execute(
                select(Evidence.finding_id, Evidence.id).where(Evidence.investigation_id == investigation_id).order_by(Evidence.created_at)
            ):
                if fid:
                    ev_map[fid].append(eid)
            out = [_finding_out(f, ev_map.get(f.id, [])) for f in rows]
        if file:
            out = [f for f in out if any(file in af for af in f.affected_files)]
        return out

    def list_evidence(self, investigation_id: str, finding_id: str | None = None) -> list[EvidenceOut]:
        with session_scope() as s:
            q = select(Evidence).where(Evidence.investigation_id == investigation_id)
            if finding_id:
                q = q.where(Evidence.finding_id == finding_id)
            return [_evidence_out(e) for e in s.scalars(q.order_by(Evidence.created_at))]

    def blackboard_version(self, investigation_id: str) -> int:
        """Monotonic counter of blackboard knowledge (findings + evidence)."""
        with session_scope() as s:
            nf = s.scalar(select(func.count()).select_from(Finding).where(Finding.investigation_id == investigation_id)) or 0
            ne = s.scalar(select(func.count()).select_from(Evidence).where(Evidence.investigation_id == investigation_id)) or 0
            return int(nf + ne)

    def evidence_count(self, finding_id: str) -> int:
        with session_scope() as s:
            return int(s.scalar(select(func.count()).select_from(Evidence).where(Evidence.finding_id == finding_id)) or 0)

    # -------------------------------------------------------------- correlations
    def upsert_correlation(self, investigation_id: str, draft: CorrelationDraft) -> tuple[CorrelationOut, bool]:
        with session_scope(write=True) as s:
            existing = s.scalar(
                select(Correlation).where(Correlation.investigation_id == investigation_id, Correlation.signature == draft.signature)
            )
            if existing is not None:
                changed = sorted(existing.finding_ids or []) != sorted(draft.finding_ids) or existing.description != draft.description
                existing.finding_ids = draft.finding_ids
                existing.description = redact(draft.description)
                existing.title = redact(draft.title)
                existing.risk_multiplier = draft.risk_multiplier
                existing.confidence = draft.confidence
                existing.links = redact_obj(draft.links)
                existing.reasoning_summary = redact(draft.reasoning_summary)
                if changed and existing.status in ("verified", "rejected"):
                    existing.status = "proposed"
                existing.updated_at = utcnow()
                s.flush()
                return _correlation_out(existing), False
            row = Correlation(
                investigation_id=investigation_id,
                finding_ids=draft.finding_ids,
                relationship_type=draft.relationship_type.value,
                title=redact(draft.title),
                description=redact(draft.description),
                risk_multiplier=draft.risk_multiplier,
                confidence=draft.confidence,
                signature=draft.signature,
                links=redact_obj(draft.links),
                reasoning_summary=redact(draft.reasoning_summary),
                status="proposed",
            )
            s.add(row)
            s.flush()
            return _correlation_out(row), True

    def update_correlation(self, correlation_id: str, **fields: Any) -> CorrelationOut:
        with session_scope(write=True) as s:
            c = s.get(Correlation, correlation_id)
            for k, v in fields.items():
                setattr(c, k, v)
            c.updated_at = utcnow()
            s.flush()
            return _correlation_out(c)

    def list_correlations(self, investigation_id: str) -> list[CorrelationOut]:
        with session_scope() as s:
            rows = s.scalars(select(Correlation).where(Correlation.investigation_id == investigation_id).order_by(Correlation.created_at))
            return [_correlation_out(c) for c in rows]

    # ------------------------------------------------------------- verifications
    def add_verification(self, investigation_id: str, draft: VerificationDraft) -> VerificationOut:
        with session_scope(write=True) as s:
            row = Verification(
                investigation_id=investigation_id,
                finding_id=draft.finding_id,
                correlation_id=draft.correlation_id,
                round=draft.round,
                decision=draft.decision.value,
                confidence=draft.confidence,
                challenge=redact(draft.challenge),
                checks=redact_obj([c.model_dump() for c in draft.checks]),
                evidence_checked=draft.evidence_checked,
                additional_tests=redact_obj(draft.additional_tests),
                counter_evidence=redact_obj(draft.counter_evidence),
                adjusted_severity=draft.adjusted_severity.value if draft.adjusted_severity else None,
                reasoning_summary=redact(draft.reasoning_summary),
                decided_by=draft.decided_by,
            )
            s.add(row)
            s.flush()
            return _verification_out(row)

    def list_verifications(self, investigation_id: str, finding_id: str | None = None) -> list[VerificationOut]:
        with session_scope() as s:
            q = select(Verification).where(Verification.investigation_id == investigation_id)
            if finding_id:
                q = q.where(Verification.finding_id == finding_id)
            return [_verification_out(v) for v in s.scalars(q.order_by(Verification.verified_at))]

    # ------------------------------------------------------------------ requests
    def add_request(
        self,
        investigation_id: str,
        requested_by: str,
        objective: str,
        *,
        reason: str = "",
        target_agent: str | None = None,
        required_evidence: str = "analysis",
        focus: dict[str, Any] | None = None,
        related_finding_ids: list[str] | None = None,
    ) -> InvestigationRequestOut:
        with session_scope(write=True) as s:
            row = InvestigationRequest(
                investigation_id=investigation_id,
                requested_by=requested_by,
                target_agent=target_agent,
                objective=redact(objective),
                reason=redact(reason),
                required_evidence=required_evidence,
                focus=redact_obj(focus or {}),
                related_finding_ids=related_finding_ids or [],
                status="open",
            )
            s.add(row)
            s.flush()
            return _request_out(row)

    def list_requests(self, investigation_id: str, status: str | None = None) -> list[InvestigationRequestOut]:
        with session_scope() as s:
            q = select(InvestigationRequest).where(InvestigationRequest.investigation_id == investigation_id)
            if status:
                q = q.where(InvestigationRequest.status == status)
            return [_request_out(r) for r in s.scalars(q.order_by(InvestigationRequest.created_at))]

    def update_request(self, request_id: str, **fields: Any) -> InvestigationRequestOut:
        with session_scope(write=True) as s:
            r = s.get(InvestigationRequest, request_id)
            for k, v in fields.items():
                setattr(r, k, v)
            if fields.get("status") in ("declined", "fulfilled"):
                r.resolved_at = utcnow()
            s.flush()
            return _request_out(r)

    # -------------------------------------------------- risks / recommendations
    def add_risk(self, investigation_id: str, **fields: Any) -> RiskOut:
        with session_scope(write=True) as s:
            row = RiskAssessment(investigation_id=investigation_id, **fields)
            s.add(row)
            s.flush()
            return _risk_out(row)

    def list_risks(self, investigation_id: str) -> list[RiskOut]:
        with session_scope() as s:
            rows = s.scalars(
                select(RiskAssessment).where(RiskAssessment.investigation_id == investigation_id).order_by(RiskAssessment.score.desc())
            )
            return [_risk_out(r) for r in rows]

    def clear_risks(self, investigation_id: str) -> None:
        with session_scope(write=True) as s:
            for r in s.scalars(select(RiskAssessment).where(RiskAssessment.investigation_id == investigation_id)):
                s.delete(r)

    def add_recommendation(self, investigation_id: str, **fields: Any) -> RecommendationOut:
        with session_scope(write=True) as s:
            row = Recommendation(investigation_id=investigation_id, **redact_obj(fields))
            s.add(row)
            s.flush()
            return _recommendation_out(row)

    def list_recommendations(self, investigation_id: str) -> list[RecommendationOut]:
        order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}
        with session_scope() as s:
            rows = [
                _recommendation_out(r)
                for r in s.scalars(
                    select(Recommendation).where(Recommendation.investigation_id == investigation_id).order_by(Recommendation.created_at)
                )
            ]
        return sorted(rows, key=lambda r: order.get(r.priority, 9))

    def add_action(self, investigation_id: str, **fields: Any) -> ActionProposalOut:
        with session_scope(write=True) as s:
            row = ActionProposal(investigation_id=investigation_id, **fields)
            s.add(row)
            s.flush()
            return _action_out(row)

    def list_actions(self, investigation_id: str) -> list[ActionProposalOut]:
        with session_scope() as s:
            rows = s.scalars(
                select(ActionProposal).where(ActionProposal.investigation_id == investigation_id).order_by(ActionProposal.created_at)
            )
            return [_action_out(a) for a in rows]

    def get_action(self, action_id: str) -> ActionProposalOut | None:
        with session_scope() as s:
            a = s.get(ActionProposal, action_id)
            return _action_out(a) if a else None

    def update_action(self, action_id: str, **fields: Any) -> ActionProposalOut:
        with session_scope(write=True) as s:
            a = s.get(ActionProposal, action_id)
            for k, v in fields.items():
                setattr(a, k, v)
            s.flush()
            return _action_out(a)

    # -------------------------------------------------------------------- events
    def list_events(self, investigation_id: str, after_seq: int = 0, limit: int | None = None) -> list[ExecutionEventOut]:
        with session_scope() as s:
            q = (
                select(ExecutionEvent)
                .where(ExecutionEvent.investigation_id == investigation_id, ExecutionEvent.seq > after_seq)
                .order_by(ExecutionEvent.seq)
            )
            if limit:
                q = q.limit(limit)
            return [_event_out(e) for e in s.scalars(q)]

    def counts(self, investigation_id: str) -> dict[str, Any]:
        findings = self.list_findings(investigation_id)
        by_status: dict[str, int] = defaultdict(int)
        by_severity: dict[str, int] = defaultdict(int)
        for f in findings:
            by_status[f.status.value] += 1
            by_severity[f.severity.value] += 1
        with session_scope() as s:

            def count(model: Any) -> int:
                return int(s.scalar(select(func.count()).select_from(model).where(model.investigation_id == investigation_id)) or 0)

            return {
                "findings": len(findings),
                "findings_by_status": dict(by_status),
                "findings_by_severity": dict(by_severity),
                "evidence": count(Evidence),
                "correlations": count(Correlation),
                "verifications": count(Verification),
                "risks": count(RiskAssessment),
                "recommendations": count(Recommendation),
                "actions": count(ActionProposal),
                "events": count(ExecutionEvent),
                "agent_runs": count(AgentRun),
            }


def as_datetime(value: datetime | None) -> datetime | None:
    return value
