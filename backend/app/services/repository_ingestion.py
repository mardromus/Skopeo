"""Repository ingestion: safe clone (or bundled demo fixture copy) into an isolated workspace,
followed by deterministic profiling (languages, ecosystems, tests, entrypoints, history)."""

from __future__ import annotations

import contextlib
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from app.config import Settings
from app.observability import get_logger
from app.security.url_validation import validate_branch, validate_repository_url
from app.tools.command_runner import SafeCommandRunner
from app.tools.manifests import detect_ecosystems
from app.tools.repository import LANGUAGE_BY_EXT, RepositoryHandle, RepositoryTools, is_test_path

log = get_logger("ingestion")

DEMO_FIXTURE_NAME = "vulnerable-demo-repo"
_DEMO_COMMIT_ENV = {
    "GIT_AUTHOR_NAME": "Skopeo Demo Fixture",
    "GIT_AUTHOR_EMAIL": "demo@skopeo.invalid",
    "GIT_COMMITTER_NAME": "Skopeo Demo Fixture",
    "GIT_COMMITTER_EMAIL": "demo@skopeo.invalid",
    "GIT_AUTHOR_DATE": "2026-01-15T09:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-01-15T09:00:00+00:00",
}


class IngestionError(RuntimeError):
    pass


def _workspace(settings: Settings, investigation_id: str) -> Path:
    ws = (settings.skopeo_workspace_dir / investigation_id).resolve()
    if ws.exists():
        shutil.rmtree(ws, ignore_errors=True)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "no-hooks").mkdir(exist_ok=True)
    return ws


def _git_safety_flags(ws: Path) -> list[str]:
    return [
        "-c",
        f"core.hooksPath={(ws / 'no-hooks').as_posix()}",
        "-c",
        "core.symlinks=false",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.autocrlf=false",
        "-c",
        "protocol.file.allow=never",
        "-c",
        "protocol.ext.allow=never",
        "-c",
        "transfer.fsckObjects=true",
        "-c",
        "advice.detachedHead=false",
    ]


def clone_repository(settings: Settings, runner: SafeCommandRunner, investigation_id: str, url: str, branch: str) -> RepositoryHandle:
    ref = validate_repository_url(url)
    branch = validate_branch(branch)
    ws = _workspace(settings, investigation_id)
    dest = ws / "repo"
    argv = [
        "git",
        *_git_safety_flags(ws),
        "clone",
        "--depth",
        str(int(settings.clone_depth)),
        "--branch",
        branch,
        "--single-branch",
        "--no-tags",
        "--no-recurse-submodules",
        "--quiet",
        ref.clone_url,
        str(dest),
    ]
    result = runner.run(argv, ws, repo_root=ws, timeout=settings.clone_timeout_seconds)
    if not result.ok:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ["unknown error"]
        raise IngestionError(f"git clone failed ({'timeout' if result.timed_out else result.exit_code}): {detail[0][:300]}")
    handle = RepositoryHandle(
        root=dest,
        workspace=ws,
        source="github",
        full_name=ref.full_name,
        url=ref.canonical_url,
        branch=branch,
        trusted_execution=False,
    )
    handle.commit_sha = _head_sha(runner, dest)
    return handle


def prepare_demo_fixture(settings: Settings, runner: SafeCommandRunner, investigation_id: str) -> RepositoryHandle:
    """Copy the bundled demo fixture and commit it so git-based tools have a real (1-commit) history."""
    source = (settings.skopeo_examples_dir / DEMO_FIXTURE_NAME).resolve()
    if not source.is_dir():
        raise IngestionError(f"demo fixture not found at {source}")
    ws = _workspace(settings, investigation_id)
    dest = ws / "repo"
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".coverage", "*.pyc"))
    flags = _git_safety_flags(ws) + [
        "-c",
        "user.name=Skopeo Demo Fixture",
        "-c",
        "user.email=demo@skopeo.invalid",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "init.defaultBranch=main",
    ]
    for args in (["init", "--quiet"], ["add", "--all"], ["commit", "--quiet", "--no-verify", "-m", "Import Skopeo demo fixture"]):
        res = runner.run(["git", *flags, *args], dest, repo_root=dest, env=_DEMO_COMMIT_ENV)
        if not res.ok:
            raise IngestionError(f"demo fixture git {args[0]} failed: {res.stderr[:200]}")
    handle = RepositoryHandle(
        root=dest,
        workspace=ws,
        source="demo_fixture",
        full_name=f"examples/{DEMO_FIXTURE_NAME}",
        url=f"bundled://examples/{DEMO_FIXTURE_NAME}",
        branch="main",
        trusted_execution=True,  # bundled, reviewed fixture — safe to execute its tests/benchmarks
    )
    handle.commit_sha = _head_sha(runner, dest)
    return handle


def _head_sha(runner: SafeCommandRunner, repo: Path) -> str | None:
    res = runner.run(["git", "-c", f"safe.directory={repo.as_posix()}", "rev-parse", "HEAD"], repo, repo_root=repo)
    return res.stdout.strip() if res.ok else None


def build_profile(tools: RepositoryTools) -> dict[str, Any]:
    """Deterministic repository profile — the orchestrator's planning input."""
    files = tools.list_files()
    languages: Counter[str] = Counter()
    for f in files:
        lang = LANGUAGE_BY_EXT.get(Path(f).suffix.lower())
        if lang:
            languages[lang] += 1
    test_files = [f for f in files if is_test_path(f) and Path(f).suffix in (".py", ".js", ".ts", ".tsx", ".go", ".java", ".rs")]
    source_files = [f for f in files if Path(f).suffix.lower() in LANGUAGE_BY_EXT and not is_test_path(f)]
    python_packages = sorted(
        {f.split("/")[0] for f in files if f.endswith("/__init__.py") and f.count("/") == 1 and not is_test_path(f)}
        | {f.split("/")[1] for f in files if f.startswith("src/") and f.endswith("/__init__.py") and f.count("/") == 2}
    )
    entrypoints = [
        f
        for f in files
        if Path(f).name in {"app.py", "main.py", "wsgi.py", "asgi.py", "manage.py", "server.py", "index.js", "server.js", "main.go"}
        or "/routes" in f
        or "/api/" in f
    ][:20]
    commits = 0
    if tools.has_git():
        try:
            commits = len(tools.get_git_log(max_count=tools.settings.clone_depth))
        except RuntimeError:
            commits = 0
    benchmark_scripts = [f for f in files if f.endswith(".py") and ("bench" in f.lower() or f.startswith(("benchmarks/", "perf/")))]
    db_signals = tools.search_repository(
        r"\b(sqlite3|sqlalchemy|psycopg|pymysql|django\.db|\.execute\(|SELECT\s)", suffixes=(".py", ".js", ".ts"), max_results=20
    )
    http_signals = tools.search_repository(
        r"\b(requests\.(get|post|put)|httpx\.|fetch\(|axios\.)", suffixes=(".py", ".js", ".ts"), max_results=20
    )
    total_bytes = 0
    for f in files[:2000]:
        with contextlib.suppress(OSError):
            total_bytes += (tools.root / f).stat().st_size
    has_license = any(Path(f).name.upper().startswith(("LICENSE", "LICENCE", "COPYING")) for f in files)
    profile = {
        "repository": tools.handle.full_name,
        "source": tools.handle.source,
        "commit_sha": tools.handle.commit_sha,
        "file_count": len(files),
        "file_limit_reached": len(files) >= tools.settings.max_repo_files,
        "total_bytes_sampled": total_bytes,
        "languages": dict(languages.most_common()),
        "primary_language": languages.most_common(1)[0][0] if languages else None,
        "ecosystems": detect_ecosystems(files),
        "manifests": tools.inspect_manifest(),
        "source_file_count": len(source_files),
        "test_file_count": len(test_files),
        "test_files": test_files[:50],
        "python_packages": python_packages,
        "entrypoints": entrypoints,
        "benchmark_scripts": benchmark_scripts[:20],
        "has_license_file": has_license,
        "git_commits_available": commits,
        "has_git_history": commits > 0,
        "uses_database": bool(db_signals),
        "uses_network_calls": bool(http_signals),
        "trusted_execution": tools.handle.trusted_execution or tools.settings.skopeo_sandbox_execution,
        "github_metadata_available": tools.handle.source == "github" and not tools.settings.skopeo_offline,
    }
    return profile
