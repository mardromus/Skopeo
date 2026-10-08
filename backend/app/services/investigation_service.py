"""Investigation lifecycle: create, run (background thread with its own event loop), cancel."""

from __future__ import annotations

import asyncio
import os
import shutil
import stat
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

from app.agents.base import AgentServices
from app.config import Settings, get_settings
from app.graph.builder import InvestigationGraph
from app.llm import create_provider
from app.models import utcnow
from app.observability import get_logger, investigation_id_var
from app.schemas import AgentTask, EventType
from app.schemas.investigation import DemoInvestigationCreate, InvestigationCreate
from app.security.url_validation import validate_repository_url
from app.services.events import EventBus
from app.services.evidence_store import EvidenceStore
from app.services.repository_ingestion import DEMO_FIXTURE_NAME
from app.tools.advisories import AdvisoryClient, RegistryClient
from app.tools.github import GitHubClient

log = get_logger("investigations")


class InvestigationService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = EvidenceStore()
        self.events = EventBus()
        self._executor = ThreadPoolExecutor(max_workers=self.settings.max_concurrent_investigations, thread_name_prefix="investigation")
        self._futures: dict[str, Future] = {}
        self._cancel_events: dict[str, threading.Event] = {}

    # ------------------------------------------------------------------ create
    def create(self, req: InvestigationCreate) -> str:
        ref = validate_repository_url(req.repository_url)
        return self.store.create_investigation(
            repository_url=ref.canonical_url,
            repository_name=ref.full_name,
            branch=req.branch,
            analysis_depth=req.analysis_depth,
            source="github",
            enable_github_actions=req.enable_github_actions,
            status="queued",
            execution_summary={"options": {"fault_injection": self.settings.skopeo_fault_injection or None}},
        )

    def create_demo(self, req: DemoInvestigationCreate) -> str:
        spec = ",".join(
            s for s in (self.settings.skopeo_fault_injection, self.settings.skopeo_demo_fault_injection if req.fault_injection else "") if s
        )
        delay = self.settings.skopeo_demo_step_delay_ms if req.step_delay_ms is None else req.step_delay_ms
        return self.store.create_investigation(
            repository_url=f"bundled://examples/{DEMO_FIXTURE_NAME}",
            repository_name=f"examples/{DEMO_FIXTURE_NAME}",
            branch="main",
            analysis_depth=req.analysis_depth,
            source="demo_fixture",
            enable_github_actions=False,
            status="queued",
            execution_summary={"options": {"fault_injection": spec or None, "step_delay_ms": delay, "offline": True}},
        )

    # --------------------------------------------------------------------- run
    def start(self, investigation_id: str) -> None:
        self._cancel_events[investigation_id] = threading.Event()
        self._futures[investigation_id] = self._executor.submit(self.run_sync, investigation_id)

    def run_sync(self, investigation_id: str) -> None:
        asyncio.run(self.run(investigation_id))

    def wait(self, investigation_id: str, timeout: float | None = None) -> None:
        fut = self._futures.get(investigation_id)
        if fut:
            fut.result(timeout=timeout)

    def _services(self, investigation_id: str) -> AgentServices:
        inv = self.store.get_investigation(investigation_id)
        assert inv is not None
        options = (inv.execution_summary or {}).get("options", {})
        offline = self.settings.skopeo_offline or inv.source == "demo_fixture"
        return AgentServices(
            investigation_id=investigation_id,
            settings=self.settings,
            store=self.store,
            events=self.events,
            llm=create_provider(self.settings),
            advisories=AdvisoryClient(self.settings, offline=offline),
            registry=RegistryClient(self.settings, offline=offline),
            github=GitHubClient(self.settings, offline=offline),
            fault_spec=options.get("fault_injection") or "",
            step_delay_ms=int(options.get("step_delay_ms") or 0),
            cancel_event=self._cancel_events.setdefault(investigation_id, threading.Event()),
        )

    async def run(self, investigation_id: str) -> None:
        investigation_id_var.set(investigation_id)
        inv = self.store.get_investigation(investigation_id)
        if inv is None:
            raise KeyError(investigation_id)
        services = self._services(investigation_id)
        orch_task = AgentTask(agent="orchestrator", objective="Coordinate the investigation", trigger="initial_plan")
        orch_run = self.store.create_agent_run(investigation_id, orch_task)
        self.store.start_agent_run(orch_run)
        self.store.update_investigation(investigation_id, status="running", started_at=utcnow())
        self.events.emit(
            investigation_id,
            "orchestrator",
            EventType.INVESTIGATION_STARTED,
            f"Orchestrator created investigation of {inv.repository_name} ({inv.branch}, depth={inv.analysis_depth}, mode={'mock' if services.llm.is_mock else services.llm.name}, DRY_RUN={self.settings.dry_run})",
            receiver="all_agents",
            payload={
                "repository": inv.repository_name,
                "source": inv.source,
                "llm_provider": services.llm.name,
                "fault_injection": services.fault_spec or None,
            },
        )
        graph = InvestigationGraph(services, orch_run).build()
        initial = {
            "investigation_id": investigation_id,
            "depth": inv.analysis_depth,
            "round": 0,
            "task_results": [],
            "started_monotonic": time.monotonic(),
        }
        try:
            await asyncio.wait_for(
                graph.ainvoke(initial, config={"recursion_limit": 300}), timeout=self.settings.investigation_timeout_seconds
            )
        except TimeoutError:
            services.cancel_event.set()
            self._fail(investigation_id, orch_run, f"investigation exceeded {self.settings.investigation_timeout_seconds}s")
        except Exception as exc:  # noqa: BLE001 - top-level guard: record, never crash the API process
            log.exception("investigation crashed", extra={"investigation_id": investigation_id})
            self._fail(investigation_id, orch_run, f"{type(exc).__name__}: {exc}")
        finally:
            if not self.settings.skopeo_keep_workspaces:
                self.remove_workspace(investigation_id)

    def remove_workspace(self, investigation_id: str) -> None:
        """Delete the cloned repository and artifacts once an investigation is over."""
        path = (self.settings.skopeo_workspace_dir / investigation_id).resolve()
        if path.parent != self.settings.skopeo_workspace_dir.resolve() or not path.is_dir():
            return

        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=_force)
        else:
            def _force_legacy(func, target, _exc_info):
                os.chmod(target, stat.S_IWRITE)
                func(target)
            shutil.rmtree(path, onerror=_force_legacy)
        log.info("workspace removed", extra={"investigation_id": investigation_id, "event_type": "workspace_removed"})

    def recover_interrupted(self) -> int:
        """Mark investigations left running by a previous process as failed (called on startup)."""
        count = 0
        for inv in self.store.list_investigations(limit=500):
            if inv.status not in ("queued", "running"):
                continue
            count += 1
            message = "Interrupted: the server restarted while this investigation was running. Start it again to finish it."
            self.store.update_investigation(inv.id, status="failed", error=message, completed_at=utcnow())
            self.events.emit(inv.id, "orchestrator", EventType.INVESTIGATION_FAILED, message, receiver="human", severity="error")
        return count

    def _fail(self, investigation_id: str, orch_run: str, error: str) -> None:
        self.store.update_investigation(investigation_id, status="failed", error=error[:2000], completed_at=utcnow())
        try:
            self.store.finish_agent_run(orch_run, "failed", error_type="InvestigationError", error_message=error[:500])
        except Exception as exc:  # noqa: BLE001 - best effort while already failing
            log.warning("could not close orchestrator run", extra={"investigation_id": investigation_id, "data": {"error": str(exc)[:200]}})
        self.events.emit(
            investigation_id,
            "orchestrator",
            EventType.INVESTIGATION_FAILED,
            f"Investigation failed: {error}",
            receiver="human",
            severity="error",
        )

    # ------------------------------------------------------------------ cancel
    def cancel(self, investigation_id: str) -> bool:
        inv = self.store.get_investigation(investigation_id)
        if inv is None:
            raise KeyError(investigation_id)
        if inv.status not in ("queued", "running"):
            return False
        self.store.update_investigation(investigation_id, cancel_requested=True)
        ev = self._cancel_events.get(investigation_id)
        if ev:
            ev.set()
        self.events.emit(
            investigation_id,
            "human",
            EventType.AGENT_MESSAGE,
            "Cancellation requested by user",
            receiver="orchestrator",
            severity="warning",
        )
        if inv.status == "queued":
            self.store.update_investigation(investigation_id, status="cancelled", completed_at=utcnow())
        return True

    def shutdown(self) -> None:
        for ev in self._cancel_events.values():
            ev.set()
        self._executor.shutdown(wait=False, cancel_futures=True)
