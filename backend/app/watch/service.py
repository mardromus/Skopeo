"""Watches: check an upstream repository and explain how its changes affect the user's project.

A check:

1. fetches the upstream head (shallow) and extracts its public API surface;
2. loads the project's code (a fresh shallow clone, or the files the user uploaded);
3. picks the baseline: the snapshot from the previous check, or, on the first check (or when
   asked), the release tag matching the version the project's manifest pins;
4. diffs the two surfaces, finds the project's usages and joins them into impacts;
5. stores a report, schedules the next check and sends notifications.

Upstream and project code are only *read* (parsed), never executed.
"""

from __future__ import annotations

import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, Field

from app.config import Settings
from app.llm import LLMRequest, create_provider
from app.models import Project, User, Watch, WatchReport, utcnow
from app.notifications import Message, NotificationService
from app.notifications.events import IMPACT_SEVERITY
from app.observability import get_logger
from app.security.redaction import redact
from app.security.url_validation import InvalidBranchName, InvalidRepositoryURL, validate_branch, validate_repository_url
from app.services.account_store import AccountStore
from app.services.github_accounts import clone_token
from app.watch.diff import changelog_highlights, diff_surfaces
from app.watch.impact import IMPACT_ORDER, assess_impacts, impact_level, usage_inventory
from app.watch.sources import Checkout, GitSource, RepositorySource, read_project_tree, tag_for_version
from app.watch.surface import extract_surface
from app.watch.usage import find_pinned_version, find_usages

log = get_logger("watches")

FREQUENCIES: dict[str, timedelta | None] = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "manual": None,
}
MAX_WATCHES_PER_USER = 50


class WatchError(ValueError):
    pass


class ImpactNarrative(BaseModel):
    summary: str = Field(
        max_length=1500, description="2-4 sentences for the project owner: what changed upstream and what it means for their code"
    )
    actions: list[str] = Field(default_factory=list, max_length=8, description="concrete next steps, most important first")


def watch_out(w: Watch, latest: WatchReport | None = None) -> dict[str, Any]:
    return {
        "watch_id": w.id,
        "project_id": w.project_id,
        "upstream_url": w.upstream_url,
        "upstream_name": w.upstream_name,
        "branch": w.branch,
        "package_name": w.package_name,
        "import_names": list(w.import_names or []),
        "ecosystem": w.ecosystem,
        "frequency": w.frequency,
        "enabled": w.enabled,
        "status": w.status,
        "last_error": w.last_error,
        "last_checked_at": w.last_checked_at,
        "next_check_at": w.next_check_at,
        "last_seen_sha": w.last_seen_sha,
        "last_seen_version": w.last_seen_version,
        "created_at": w.created_at,
        "latest_report": report_summary(latest) if latest else None,
    }


def report_summary(r: WatchReport) -> dict[str, Any]:
    return {
        "report_id": r.id,
        "watch_id": r.watch_id,
        "kind": r.kind,
        "trigger": r.trigger,
        "base_ref": r.base_ref,
        "head_ref": r.head_ref,
        "head_sha": r.head_sha,
        "impact_level": r.impact_level,
        "summary": r.summary,
        "stats": r.stats,
        "created_at": r.created_at,
    }


def report_out(r: WatchReport) -> dict[str, Any]:
    return report_summary(r) | {
        "base_sha": r.base_sha,
        "narrative": r.narrative,
        "commits": r.commits,
        "upstream_changes": r.upstream_changes,
        "impacts": r.impacts,
        "usages": r.usages,
    }


class WatchService:
    def __init__(
        self,
        settings: Settings,
        store: AccountStore | None = None,
        notifier: NotificationService | None = None,
        source: RepositorySource | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or AccountStore()
        self.notifier = notifier
        self.source: RepositorySource = source or GitSource(settings)
        self._executor = ThreadPoolExecutor(max_workers=max(1, settings.watch_max_concurrent_checks), thread_name_prefix="watch")
        self._running: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._scheduler: threading.Thread | None = None

    # ------------------------------------------------------------------ CRUD
    def create_watch(
        self,
        user: User,
        project_id: str,
        *,
        upstream_url: str,
        branch: str | None = None,
        package_name: str | None = None,
        import_names: list[str] | None = None,
        ecosystem: str | None = None,
        frequency: str = "daily",
    ) -> Watch:
        if self.store.get_project(user.id, project_id) is None:
            raise LookupError("project not found")
        if len(self.store.list_watches(user.id)) >= MAX_WATCHES_PER_USER:
            raise WatchError(f"you can watch at most {MAX_WATCHES_PER_USER} repositories")
        try:
            ref = validate_repository_url(upstream_url)
            branch = validate_branch(branch) if branch else None
        except (InvalidRepositoryURL, InvalidBranchName) as exc:
            raise WatchError(str(exc)) from exc
        if frequency not in FREQUENCIES:
            raise WatchError("frequency must be hourly, daily, weekly or manual")
        if ecosystem not in (None, "PyPI", "npm"):
            raise WatchError("ecosystem must be PyPI or npm")
        names = [n.strip() for n in (import_names or []) if n and n.strip()]
        if any(not _valid_import_name(n) for n in names):
            raise WatchError("import names must look like Python modules or npm package names")
        return self.store.add_watch(
            user.id,
            project_id=project_id,
            upstream_url=ref.canonical_url,
            upstream_name=ref.full_name,
            branch=branch,
            package_name=(package_name or "").strip()[:214] or None,
            import_names=names[:10],
            ecosystem=ecosystem,
            frequency=frequency,
            next_check_at=utcnow(),
        )

    def update_watch(self, user: User, watch_id: str, **fields: Any) -> Watch:
        w = self.store.get_watch(user.id, watch_id)
        if w is None:
            raise LookupError("watch not found")
        clean: dict[str, Any] = {}
        if fields.get("frequency") is not None:
            if fields["frequency"] not in FREQUENCIES:
                raise WatchError("frequency must be hourly, daily, weekly or manual")
            clean["frequency"] = fields["frequency"]
            step = FREQUENCIES[fields["frequency"]]
            clean["next_check_at"] = (utcnow() + step) if step else None
        if fields.get("enabled") is not None:
            clean["enabled"] = bool(fields["enabled"])
        if "package_name" in fields and fields["package_name"] is not None:
            clean["package_name"] = fields["package_name"].strip()[:214] or None
        if fields.get("import_names") is not None:
            names = [n.strip() for n in fields["import_names"] if n and n.strip()]
            if any(not _valid_import_name(n) for n in names):
                raise WatchError("import names must look like Python modules or npm package names")
            clean["import_names"] = names[:10]
        if "branch" in fields and fields["branch"] is not None:
            try:
                clean["branch"] = validate_branch(fields["branch"]) if fields["branch"].strip() else None
            except InvalidBranchName as exc:
                raise WatchError(str(exc)) from exc
            clean |= {"snapshot": {}, "last_seen_sha": None}  # a different branch needs a new baseline
        return self.store.update_watch(w.id, **clean) if clean else w

    # ---------------------------------------------------------------- checks
    def submit(self, watch_id: str, trigger: str = "manual", from_pinned: bool = False) -> bool:
        """Queue a check in the background. False if one is already running for this watch."""
        with self._lock:
            if watch_id in self._running:
                return False
            self._running.add(watch_id)
        self.store.update_watch(watch_id, status="checking", last_error=None)
        self._executor.submit(self._run, watch_id, trigger, from_pinned)
        return True

    def _run(self, watch_id: str, trigger: str, from_pinned: bool) -> None:
        try:
            self.check(watch_id, trigger=trigger, from_pinned=from_pinned)
        except Exception:  # noqa: BLE001 - already recorded on the watch by check()
            log.warning("watch check failed", extra={"event_type": "watch_failed", "data": {"watch_id": watch_id}})
        finally:
            with self._lock:
                self._running.discard(watch_id)

    def check(self, watch_id: str, *, trigger: str = "manual", from_pinned: bool = False) -> dict[str, Any]:
        w = self.store.get_watch(None, watch_id)
        if w is None:
            raise LookupError("watch not found")
        project = self.store.get_project(w.user_id, w.project_id)
        if project is None:
            raise LookupError("project not found")
        ws = (self.settings.skopeo_workspace_dir / "watches" / w.id / uuid.uuid4().hex[:8]).resolve()
        ws.mkdir(parents=True, exist_ok=True)
        now = utcnow()
        step = FREQUENCIES.get(w.frequency)
        try:
            result = self._check(w, project, ws, trigger, from_pinned)
        except Exception as exc:
            error = redact(f"{type(exc).__name__}: {exc}")[:1000]
            self.store.update_watch(
                w.id,
                status="failed",
                last_error=error,
                last_checked_at=now,
                next_check_at=(now + min(step, timedelta(hours=6))) if step else None,
            )
            self._notify_failure(w, project, error)
            raise
        finally:
            _remove_tree(ws)
        return result

    def _check(self, w: Watch, project: Project, ws, trigger: str, from_pinned: bool) -> dict[str, Any]:
        now = utcnow()
        step = FREQUENCIES.get(w.frequency)
        head = self.source.checkout(w.upstream_url, w.branch, ws / "upstream", self.settings.watch_clone_depth)
        new = extract_surface(head.root, ecosystem=w.ecosystem, import_names=w.import_names or None)
        ecosystem = w.ecosystem or new["ecosystem"]
        package_name = w.package_name or new.get("package_name")
        import_names = list(w.import_names or new.get("import_names") or ([package_name] if package_name else []))
        files = self._project_files(project, ws)
        pin = find_pinned_version(files, package_name, ecosystem)
        usages = find_usages(files, ecosystem=ecosystem, import_names=import_names)

        identity = {"package_name": package_name, "import_names": import_names, "ecosystem": ecosystem}
        unchanged = bool(w.last_seen_sha) and w.last_seen_sha == head.sha and not from_pinned
        if unchanged and trigger == "schedule":
            self.store.update_watch(w.id, status="ok", last_checked_at=now, next_check_at=(now + step) if step else None, **identity)
            return {"status": "no_change", "report_id": None}

        base: dict[str, Any] | None = None
        base_ref = base_sha = None
        kind = "update"
        commits: list[dict[str, Any]] = []
        if unchanged:
            # nothing new upstream: re-assess the last report's changes against the current project code
            latest = self.store.latest_report(w.id)
            if latest is not None and latest.upstream_changes:
                return self._store_report(
                    w, project, trigger, "recheck", latest.base_ref, latest.base_sha, head, new, latest.upstream_changes,
                    latest.commits, usages, pin, identity, latest.narrative.get("changelog") or [],
                )  # fmt: skip
            kind = "baseline"
        elif w.snapshot and w.last_seen_sha and not from_pinned:
            base, base_ref, base_sha = w.snapshot, (w.last_seen_version or w.last_seen_sha[:12]), w.last_seen_sha
        elif pin and (pin.get("version") or pin.get("floor")):
            version = pin.get("version") or pin.get("floor")
            tag = tag_for_version(self.source.list_tags(w.upstream_url, ws / "tags"), version, package_name)
            if tag:
                base_checkout = self.source.checkout(w.upstream_url, tag, ws / "base", 1)
                base = extract_surface(base_checkout.root, ecosystem=ecosystem, import_names=import_names)
                base_ref, base_sha = tag, base_checkout.sha
        if base is None and kind != "baseline":
            kind = "baseline"

        changes = diff_surfaces(base, new) if base is not None else []
        if base_sha and head.sha and base_sha != head.sha:
            commits = self.source.log(head, base_sha, 100) or []
        highlights = changelog_highlights(base.get("changelog") if base else None, new.get("changelog")) if base is not None else []
        return self._store_report(
            w, project, trigger, kind, base_ref, base_sha, head, new, changes, commits, usages, pin, identity, highlights
        )

    def _store_report(
        self,
        w: Watch,
        project: Project,
        trigger: str,
        kind: str,
        base_ref: str | None,
        base_sha: str | None,
        head: Checkout,
        new: dict[str, Any],
        changes: list[dict[str, Any]],
        commits: list[dict[str, Any]],
        usages: list[dict[str, Any]],
        pin: dict[str, Any] | None,
        identity: dict[str, Any],
        highlights: list[str],
    ) -> dict[str, Any]:
        now = utcnow()
        step = FREQUENCIES.get(w.frequency)
        impacts = assess_impacts(changes, usages)
        level = impact_level(impacts)
        inventory = usage_inventory(usages)
        by_kind: dict[str, int] = {}
        for c in changes:
            by_kind[c["kind"]] = by_kind.get(c["kind"], 0) + 1
        stats = {
            "changes": len(changes),
            "changes_by_kind": by_kind,
            "breaking_changes": sum(1 for c in changes if c["severity"] == "breaking"),
            "impacts": len(impacts),
            "impacts_by_level": {lv: sum(1 for i in impacts if i["level"] == lv) for lv in IMPACT_ORDER if lv != "none"},
            "affected_files": len({i["file"] for i in impacts}),
            "usages": sum(1 for u in usages if u["kind"] != "import"),
            "files_using_library": len({u["file"] for u in usages}),
            "commits": len(commits),
            "upstream_version": new.get("version"),
            "pinned": pin,
            "package_name": identity["package_name"],
            "import_names": identity["import_names"],
            "ecosystem": identity["ecosystem"],
        }
        narrative = self._narrative(w, project, kind, base_ref, head, changes, impacts, inventory, stats, highlights)
        summary = narrative["summary"]
        report = self.store.add_report(
            watch_id=w.id,
            user_id=w.user_id,
            kind=kind,
            trigger=trigger,
            base_ref=base_ref,
            base_sha=base_sha,
            head_ref=head.ref,
            head_sha=head.sha,
            impact_level=level,
            summary=summary,
            narrative=narrative,
            commits=commits[:100],
            upstream_changes=[c for c in changes if c["kind"] != "added"][:400] + [c for c in changes if c["kind"] == "added"][:100],
            impacts=impacts[:500],
            usages=inventory,
            stats=stats,
        )
        self.store.update_watch(
            w.id,
            status="ok",
            last_error=None,
            last_checked_at=now,
            next_check_at=(now + step) if step else None,
            last_seen_sha=head.sha,
            last_seen_version=new.get("version"),
            snapshot={
                k: new[k] for k in ("schema", "ecosystem", "package_name", "version", "import_names", "symbols", "modules", "changelog")
            },
            **identity,
        )
        self._notify_report(w, project, report)
        return {"status": kind, "report_id": report.id, "impact_level": level}

    def _project_files(self, project: Project, ws) -> list[tuple[str, str]]:
        if project.source == "github" and project.repository_url:
            token = clone_token(self.settings, project.user_id) if project.github_private else None
            extra = {"token": token} if token else {}
            co = self.source.checkout(project.repository_url, project.branch or None, ws / "project", 1, **extra)
            files = read_project_tree(co.root)
        else:
            files = [(f.path, f.content) for f in self.store.list_project_files(project.id)]
        return files

    # -------------------------------------------------------------- narrative
    def _narrative(
        self,
        w: Watch,
        project: Project,
        kind: str,
        base_ref: str | None,
        head: Checkout,
        changes: list[dict[str, Any]],
        impacts: list[dict[str, Any]],
        inventory: list[dict[str, Any]],
        stats: dict[str, Any],
        highlights: list[str],
    ) -> dict[str, Any]:
        def policy() -> ImpactNarrative:
            return ImpactNarrative(**_template_narrative(w, project, kind, base_ref, head, changes, impacts, inventory, stats))

        llm = create_provider(self.settings)
        decision = llm.decide(
            LLMRequest(
                task_type="watch.impact_summary",
                role_instructions=(
                    "You explain to a software team how changes in an open-source dependency affect their own project. "
                    "Be specific: name files, lines and symbols from the structured state. Never invent changes that are not listed."
                ),
                task=f"Summarise the impact of {w.upstream_name} changes ({base_ref or 'baseline'} -> {head.ref}) on the project '{project.name}'.",
                structured_input={
                    "kind": kind,
                    "stats": {k: v for k, v in stats.items() if k != "pinned"},
                    "pinned": stats.get("pinned"),
                    "impacts": [{k: i[k] for k in ("level", "title", "file", "line", "explanation")} for i in impacts[:25]],
                    "upstream_changes": [
                        {k: c.get(k) for k in ("kind", "severity", "symbol", "detail")} for c in changes if c["kind"] != "added"
                    ][:30],
                    "project_uses": inventory[:20],
                },
                untrusted={"project_notes": project.notes[:4000], "changelog_highlights": "\n".join(highlights)[:6000]}
                if (project.notes or highlights)
                else None,
                tier="fast",
            ),
            ImpactNarrative,
            policy,
        )
        return {**decision.value.model_dump(), "decided_by": decision.decided_by, "changelog": highlights}

    # ---------------------------------------------------------- notifications
    def _notify_report(self, w: Watch, project: Project, report: WatchReport) -> None:
        if self.notifier is None or report.kind == "recheck":
            return
        url = self.notifier.link(f"/projects/{project.id}?watch={w.id}&report={report.id}")
        stats = report.stats or {}
        fields = [
            ("Upstream", w.upstream_name),
            ("Project", project.name),
            ("Compared", f"{report.base_ref or 'first check'} → {report.head_ref or ''} {(report.head_sha or '')[:10]}".strip()),
            ("Impact", report.impact_level),
            ("Affected files", str(stats.get("affected_files", 0))),
        ]
        items = [f"[{i['level']}] {i['file']}:{i['line']}: {i['title']}" for i in report.impacts[:8]]
        context = {"project_id": project.id, "watch_id": w.id, "impact_level": report.impact_level}
        data = {"report_id": report.id, "watch_id": w.id, "project_id": project.id, "impact_level": report.impact_level, "stats": stats}
        if report.impacts:
            msg = Message(
                event="watch.impact",
                subject=f"{w.upstream_name} changes affect {project.name} ({report.impact_level})",
                text=report.summary,
                severity=IMPACT_SEVERITY.get(report.impact_level, "warning"),
                url=url,
                fields=fields,
                items=items,
                data=data,
            )
            self.notifier.safe_dispatch(w.user_id, "watch.impact", msg, context)
        if report.kind == "update" and (stats.get("changes") or stats.get("commits")):
            digest = Message(
                event="watch.update",
                subject=f"{w.upstream_name}: {stats.get('changes', 0)} API change(s), {stats.get('commits', 0)} commit(s)",
                text=report.summary,
                severity="info",
                url=url,
                fields=fields,
                items=[f"{c['message'][:120]}" for c in report.commits[:8]],
                data=data,
            )
            self.notifier.safe_dispatch(w.user_id, "watch.update", digest, context)

    def _notify_failure(self, w: Watch, project: Project, error: str) -> None:
        if self.notifier is None:
            return
        msg = Message(
            event="watch.failed",
            subject=f"Skopeo could not check {w.upstream_name}",
            text=error,
            severity="warning",
            url=self.notifier.link(f"/projects/{project.id}?watch={w.id}"),
            fields=[("Upstream", w.upstream_name), ("Project", project.name)],
            data={"watch_id": w.id, "project_id": project.id},
        )
        self.notifier.safe_dispatch(w.user_id, "watch.failed", msg, {"project_id": project.id, "watch_id": w.id})

    # -------------------------------------------------------------- scheduler
    def start_scheduler(self) -> None:
        if not self.settings.watch_scheduler_enabled or self._scheduler is not None:
            return
        reset = self.store.reset_stuck_watches()
        if reset:
            log.info("reset interrupted watch checks", extra={"event_type": "watch_reset", "data": {"count": reset}})
        self._scheduler = threading.Thread(target=self._loop, name="watch-scheduler", daemon=True)
        self._scheduler.start()

    def _loop(self) -> None:
        interval = max(5, int(self.settings.watch_scheduler_interval_seconds))
        while not self._stop.wait(interval):
            self.tick()

    def tick(self) -> int:
        """Queue every watch that is due. Returns how many were queued."""
        queued = 0
        try:
            for w in self.store.due_watches(utcnow()):
                queued += self.submit(w.id, trigger="schedule")
        except Exception:  # noqa: BLE001 - the scheduler must survive database hiccups
            log.exception("watch scheduler tick failed")
        return queued

    def wait_idle(self, timeout: float = 60.0) -> None:
        """Block until no check is running (tests)."""
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if not self._running:
                    return
            time.sleep(0.05)

    def shutdown(self) -> None:
        self._stop.set()
        self._executor.shutdown(wait=False, cancel_futures=True)


def _remove_tree(path) -> None:
    """Delete a check's workspace; git marks object files read-only on Windows."""
    import os
    import stat

    def _force(func, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            pass

    shutil.rmtree(path, onexc=_force)


def _valid_import_name(name: str) -> bool:
    import re

    return bool(re.fullmatch(r"(@[a-z0-9][\w.-]*/)?[A-Za-z0-9_][\w.-]{0,213}", name))


def _template_narrative(
    w: Watch,
    project: Project,
    kind: str,
    base_ref: str | None,
    head: Checkout,
    changes: list[dict[str, Any]],
    impacts: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    stats: dict[str, Any],
) -> dict[str, Any]:
    head_label = f"{head.ref or 'HEAD'} ({(head.sha or '')[:10]})"
    pin = stats.get("pinned") or {}
    pin_text = f" Your manifest asks for {stats.get('package_name')} {pin.get('spec')} ({pin.get('manifest')})." if pin else ""
    uses = f"{project.name} uses {len(inventory)} symbol(s) of {stats.get('package_name') or w.upstream_name} in {stats.get('files_using_library', 0)} file(s)."
    if kind == "baseline":
        summary = (
            f"First look at {w.upstream_name} at {head_label}. {uses}{pin_text} "
            "Skopeo recorded the current public API; the next check will report every change against it and where it touches your code."
        )
        actions = ["Upload or connect the files that use this library if the usage count looks too low."] if not inventory else []
        if pin and not pin.get("version") and not pin.get("floor"):
            actions.append("Pin an exact version in your manifest so Skopeo can compare against the release you actually run.")
        return {"summary": summary, "actions": actions}
    breaking = [i for i in impacts if i["level"] == "breaking"]
    span = f"{base_ref or 'the previous check'} → {head_label}"
    if not changes:
        summary = f"No public API changes in {w.upstream_name} between {span}. {uses}"
        return {"summary": summary, "actions": []}
    changed = stats["changes"] - stats["changes_by_kind"].get("added", 0)
    added = stats["changes_by_kind"].get("added", 0)
    delta = f"changed {changed} public API element(s) ({stats['breaking_changes']} breaking)" + (f" and added {added}" if added else "")
    if not impacts:
        summary = f"{w.upstream_name} {delta} between {span}, but none of the changes touch code in {project.name}. {uses}"
        return {"summary": summary, "actions": ["You can upgrade; run your test suite as usual."]}
    files = sorted({i["file"] for i in impacts})
    summary = (
        f"{w.upstream_name} {delta} between {span}. "
        f"{len(impacts)} place(s) in {project.name} are affected across {len(files)} file(s)"
        + (f", {len(breaking)} of them breaking" if breaking else "")
        + f". The most serious: {impacts[0]['title']} at {impacts[0]['file']}:{impacts[0]['line']}.{pin_text}"
    )
    actions = []
    seen_lines: set[tuple[str, int]] = set()
    for i in impacts:
        if IMPACT_ORDER[i["level"]] < IMPACT_ORDER["medium"] or (i["file"], i["line"]) in seen_lines:
            continue
        seen_lines.add((i["file"], i["line"]))
        actions.append(f"{i['file']}:{i['line']}: {i['suggestion']}")
        if len(actions) == 5:
            break
    if not actions:
        actions.append("Nothing needs to change in your code; re-run your test suite after upgrading.")
    if breaking:
        actions.append("Do not upgrade until the breaking call sites above are updated, or pin the current version.")
    return {"summary": summary, "actions": actions[:8]}
