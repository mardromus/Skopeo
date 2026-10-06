"""Fault isolation: an agent that fails on every attempt never crashes the investigation, and
without the controlled failure the orchestrator follows a different (adaptive) path."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.schemas.investigation import DemoInvestigationCreate
from app.services.investigation_service import InvestigationService
from app.services.report import build_report

pytestmark = pytest.mark.slow


def test_permanently_failing_agent_is_reported_unavailable(monkeypatch):
    settings = get_settings().model_copy(update={"skopeo_fault_injection": "license_agent@*", "skopeo_demo_fault_injection": ""})
    svc = InvestigationService(settings)
    iid = svc.create_demo(DemoInvestigationCreate(fault_injection=False, step_delay_ms=0))
    # LicenseAgent declares no tool requirement, so route the fault through its first step.
    from app.agents import license as license_mod

    original = license_mod.LicenseAgent._identify

    def failing_identify(self, ctx):
        ctx.require_tool("license database")
        return original(self, ctx)

    monkeypatch.setattr(license_mod.LicenseAgent, "_identify", failing_identify)
    svc.run_sync(iid)
    report = build_report(svc.store, iid)
    runs = [r for r in svc.store.list_agent_runs(iid) if r.agent == "license_agent"]
    assert len(runs) == 2 and all(r.status == "failed" for r in runs)  # original + one retry
    assert report["coverage"]["agents"]["license_agent"]["status"] == "unavailable"
    assert report["status"] == "completed_with_limitations"
    assert report["verified_findings"] and report["risks"]
    messages = [e["message"] for e in report["events"] if e["event_type"] == "agent_message" and e["sender"] == "orchestrator"]
    assert any("unavailable" in m and "Continuing" in m for m in messages)
    svc.shutdown()


def test_without_fault_performance_measures_in_first_round():
    settings = get_settings().model_copy(update={"skopeo_demo_fault_injection": ""})
    svc = InvestigationService(settings)
    iid = svc.create_demo(DemoInvestigationCreate(fault_injection=False, step_delay_ms=0))
    svc.run_sync(iid)
    runs = [r for r in svc.store.list_agent_runs(iid) if r.agent == "performance_agent"]
    assert runs[0].status == "completed" and runs[0].trigger == "initial_plan"
    report = build_report(svc.store, iid)
    n1 = next(f for f in report["findings"] if f["rule_id"] == "performance.n_plus_one")
    assert n1["attributes"]["measurement"] == "measured" and n1["status"] == "verified"
    # no failure -> no retry, and no benchmark follow-up was necessary
    assert not any(r.trigger == "retry" for r in svc.store.list_agent_runs(iid))
    assert report["coverage"]["agents"]["performance_agent"]["status"] in ("complete", "partial")
    svc.shutdown()
