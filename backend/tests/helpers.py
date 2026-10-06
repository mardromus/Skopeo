"""Helpers to run individual agents against a repository directory without the full graph."""

from __future__ import annotations

from pathlib import Path

from app.agents.base import Agent, AgentContext, AgentServices
from app.config import get_settings
from app.llm import LLMProvider, MockLLMProvider
from app.schemas import AgentOutcome, AgentTask
from app.services.events import EventBus
from app.services.evidence_store import EvidenceStore
from app.services.repository_ingestion import build_profile
from app.tools.advisories import AdvisoryClient, RegistryClient
from app.tools.command_runner import SafeCommandRunner
from app.tools.github import GitHubClient
from app.tools.repository import RepositoryHandle, RepositoryTools


def make_services(
    repo_root: Path, *, source: str = "github", trusted: bool = False, llm: LLMProvider | None = None, fault_spec: str = ""
) -> AgentServices:
    settings = get_settings()
    store = EvidenceStore()
    iid = store.create_investigation(
        repository_url="https://github.com/test/repo", repository_name="test/repo", source=source, status="running"
    )
    runner = SafeCommandRunner(settings.command_timeout_seconds, settings.max_output_bytes)
    workspace = repo_root.parent / "ws"
    workspace.mkdir(exist_ok=True)
    handle = RepositoryHandle(
        root=repo_root,
        workspace=workspace,
        source=source,
        full_name="test/repo",
        url="https://github.com/test/repo",
        branch="main",
        trusted_execution=trusted,
    )
    tools = RepositoryTools(handle, runner, settings)
    handle.profile = build_profile(tools)
    return AgentServices(
        investigation_id=iid,
        settings=settings,
        store=store,
        events=EventBus(),
        llm=llm or MockLLMProvider(),
        advisories=AdvisoryClient(settings, offline=True),
        registry=RegistryClient(settings, offline=True),
        github=GitHubClient(settings, offline=True),
        fault_spec=fault_spec,
        repo=handle,
        tools=tools,
    )


def run_agent(services: AgentServices, agent: Agent, task: AgentTask | None = None) -> AgentOutcome:
    task = task or AgentTask(agent=agent.name, objective="unit test")
    run_id = services.store.create_agent_run(services.investigation_id, task)
    ctx = AgentContext(services, agent.name, task, run_id, run_ordinal=services.next_run_ordinal(agent.name))
    return agent.run(ctx)
