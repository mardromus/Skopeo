"""An LLM orchestrator that asks to re-run finished agents must not duplicate findings."""

from __future__ import annotations

from collections import Counter

import pytest

from app.config import get_settings
from app.llm.base import LLMDecision
from app.llm.mock_provider import MockLLMProvider
from app.schemas.investigation import DemoInvestigationCreate
from app.schemas.tasks import FollowUpDecision
from app.services import investigation_service
from app.services.investigation_service import InvestigationService
from app.services.report import build_report

pytestmark = pytest.mark.slow


class EagerReplanner(MockLLMProvider):
    """Behaves like the policy, but every orchestrator review also asks for full re-runs (as a live LLM did)."""

    is_mock = False

    def decide(self, request, schema, policy, validate=None):
        value = policy()
        if request.task_type == "orchestrator.review":
            focus_n = len(value.follow_ups)
            value.follow_ups += [
                FollowUpDecision(agent=a, objective="re-check", mode="full", focus={"pass": focus_n + i}, rationale="re-run")
                for i, a in enumerate(["security_agent", "security_agent", "license_agent", "code_quality_agent"])
            ]
        if validate is not None:
            value = validate(value)
        decision = LLMDecision(value=value, decided_by="llm:test")
        self.usage.record(request.task_type, decision)
        return decision


def test_full_reruns_are_refused_and_findings_are_not_duplicated(monkeypatch):
    monkeypatch.setattr(investigation_service, "create_provider", lambda settings: EagerReplanner())
    svc = InvestigationService(get_settings())
    try:
        iid = svc.create_demo(DemoInvestigationCreate(fault_injection=False, step_delay_ms=0))
        svc.run_sync(iid)
        report = build_report(svc.store, iid)
    finally:
        svc.shutdown()
    keys = Counter((f["agent"], f["rule_id"], f["title"], tuple(sorted(f["affected_files"]))) for f in report["findings"])
    assert keys and max(keys.values()) == 1
    full_runs = Counter(
        e["sender"] for e in report["events"] if e["event_type"] == "agent_started" and (e.get("payload") or {}).get("mode") == "full"
    )
    assert full_runs["security_agent"] == 1 and full_runs["license_agent"] <= 1
    # the dependency agent's impact-analysis request is still answered with targeted follow-ups
    modes = {(e["sender"], (e.get("payload") or {}).get("mode")) for e in report["events"] if e["event_type"] == "agent_started"}
    assert ("security_agent", "dependency_usage") in modes


def test_accepted_request_without_tasks_gets_policy_followups(monkeypatch):
    class AcceptOnly(EagerReplanner):
        def decide(self, request, schema, policy, validate=None):
            value = policy()
            if request.task_type == "orchestrator.review":
                value.follow_ups = [f for f in value.follow_ups if not f.request_id]
            if validate is not None:
                value = validate(value)
            decision = LLMDecision(value=value, decided_by="llm:test")
            self.usage.record(request.task_type, decision)
            return decision

    monkeypatch.setattr(investigation_service, "create_provider", lambda settings: AcceptOnly())
    svc = InvestigationService(get_settings())
    try:
        iid = svc.create_demo(DemoInvestigationCreate(fault_injection=False, step_delay_ms=0))
        svc.run_sync(iid)
        report = build_report(svc.store, iid)
    finally:
        svc.shutdown()
    modes = {(e["sender"], (e.get("payload") or {}).get("mode")) for e in report["events"] if e["event_type"] == "agent_started"}
    assert ("security_agent", "dependency_usage") in modes


def test_llm_cannot_finish_a_case_without_risk_assessment(monkeypatch):
    class Hasty(EagerReplanner):
        def decide(self, request, schema, policy, validate=None):
            value = policy()
            if request.task_type == "orchestrator.review" and getattr(value, "next_step", None) in ("verify", "assess"):
                value.next_step = "finalize"
            if validate is not None:
                value = validate(value)
            decision = LLMDecision(value=value, decided_by="llm:test")
            self.usage.record(request.task_type, decision)
            return decision

    monkeypatch.setattr(investigation_service, "create_provider", lambda settings: Hasty())
    svc = InvestigationService(get_settings())
    try:
        iid = svc.create_demo(DemoInvestigationCreate(fault_injection=False, step_delay_ms=0))
        svc.run_sync(iid)
        report = build_report(svc.store, iid)
    finally:
        svc.shutdown()
    assert report["overall_risk"]["score"] is not None
    assert any(e["event_type"] == "risk_assessed" for e in report["events"])
