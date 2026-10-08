"""Unit tests for TraceExporter utility."""

import pytest
from app.config import get_settings
from app.schemas import AgentTask, EventType
from app.services.investigation_service import InvestigationService
from app.services.evidence_store import EvidenceStore
from app.utils.trace_exporter import TraceExporter


from app.services.events import EventBus


@pytest.fixture
def store():
    return EvidenceStore()


def test_trace_exporter_markdown_and_json(store):
    inv_id = store.create_investigation(
        repository_url="https://github.com/psf/requests",
        repository_name="psf/requests",
        commit_sha="main",
    )
    store.update_investigation(inv_id, status="running")

    task = AgentTask(
        agent="security",
        mode="full",
        objective="Scan for secrets",
        round=1,
    )
    run_id = store.create_agent_run(inv_id, task)
    store.start_agent_run(run_id)
    store.finish_agent_run(run_id, status="completed", duration_ms=150)

    bus = EventBus()
    bus.emit(
        investigation_id=inv_id,
        sender="security",
        event_type=EventType.FINDING_CREATED,
        message="Found candidate secret in test fixture",
        receiver="orchestrator",
    )

    exporter = TraceExporter(store)
    md = exporter.export_markdown(inv_id)
    assert "# Skopeo Multi-Agent Execution Trace" in md
    assert "security" in md
    assert "Found candidate secret" in md

    data = exporter.export_json(inv_id)
    assert data["investigation_id"] == inv_id
    assert len(data["agent_runs"]) == 1
    assert data["agent_runs"][0]["agent"] == "security"
    assert len(data["events"]) == 1
