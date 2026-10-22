"""Fetching upstream and project repositories through the hardened git runner."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.config import Settings
from app.security.url_validation import validate_branch, validate_repository_url
from app.services.repository_ingestion import _git_safety_flags, git_auth_env
from app.tools.command_runner import SafeCommandRunner
from app.tools.manifests import is_requirements_file

PROJECT_FILE_SUFFIXES = (".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
PROJECT_MANIFESTS = re.compile(r"^(requirements[^/]*\.txt|pyproject\.toml|setup\.cfg|Pipfile|package\.json)$")
PROJECT_EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "coverage",
    "site-packages",
    ".tox",
}
MAX_PROJECT_FILES = 4000
MAX_PROJECT_FILE_BYTES = 400_000


class SourceError(RuntimeError):
    pass


@dataclass
class Checkout:
    root: Path
    sha: str | None
    ref: str | None


class RepositorySource(Protocol):
    def checkout(self, url: str, ref: str | None, dest: Path, depth: int, token: str | None = None) -> Checkout: ...

    def list_tags(self, url: str, workdir: Path) -> list[str]: ...

    def log(self, checkout: Checkout, base_sha: str | None, limit: int = 100) -> list[dict[str, Any]] | None: ...


class GitSource:
    def __init__(self, settings: Settings, runner: SafeCommandRunner | None = None) -> None:
        self.settings = settings
        self.runner = runner or SafeCommandRunner(settings.command_timeout_seconds, settings.max_output_bytes)

    def checkout(self, url: str, ref: str | None, dest: Path, depth: int, token: str | None = None) -> Checkout:
        repo = validate_repository_url(url)
        ws = dest.parent
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "no-hooks").mkdir(exist_ok=True)
        argv = [
            "git",
            *_git_safety_flags(ws),
            "clone",
            "--depth",
            str(max(1, int(depth))),
            "--single-branch",
            "--no-tags",
            "--no-recurse-submodules",
            "--quiet",
        ]
        if ref:
            argv += ["--branch", validate_branch(ref)]
        argv += [repo.clone_url, str(dest)]
        res = self.runner.run(argv, ws, repo_root=ws, timeout=self.settings.clone_timeout_seconds, env=git_auth_env(token))
        if not res.ok:
            detail = (res.stderr or res.stdout).strip().splitlines()[-1:] or ["unknown error"]
            raise SourceError(f"could not fetch {repo.full_name}{'@' + ref if ref else ''}: {detail[0][:300]}")
        sha = self._git(dest, "rev-parse", "HEAD")
        branch = self._git(dest, "rev-parse", "--abbrev-ref", "HEAD")
        return Checkout(root=dest, sha=sha, ref=ref or branch)

    def list_tags(self, url: str, workdir: Path) -> list[str]:
        repo = validate_repository_url(url)
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / "no-hooks").mkdir(exist_ok=True)
        res = self.runner.run(
            ["git", *_git_safety_flags(workdir), "ls-remote", "--tags", "--refs", repo.clone_url], workdir, repo_root=workdir, timeout=60
        )
        if not res.ok:
            return []
        return [line.split("refs/tags/", 1)[1].strip() for line in res.stdout.splitlines() if "refs/tags/" in line]

    def log(self, checkout: Checkout, base_sha: str | None, limit: int = 100) -> list[dict[str, Any]] | None:
        if not base_sha or not re.fullmatch(r"[0-9a-f]{7,64}", base_sha):
            return None
        out = self._git(checkout.root, "log", f"--max-count={int(limit)}", "--format=%H%x1f%an%x1f%aI%x1f%s", f"{base_sha}..HEAD", raw=True)
        if out is None:
            return None  # base commit is older than the shallow history
        commits = []
        for line in out.splitlines():
            parts = line.split("\x1f")
            if len(parts) == 4:
                commits.append({"sha": parts[0], "author": parts[1], "date": parts[2], "message": parts[3][:300]})
        return commits

    def _git(self, repo: Path, *args: str, raw: bool = False) -> str | None:
        res = self.runner.run(["git", "-c", f"safe.directory={repo.as_posix()}", *args], repo, repo_root=repo, timeout=60)
        if not res.ok:
            return None
        return res.stdout if raw else res.stdout.strip()


def read_project_tree(root: Path) -> list[tuple[str, str]]:
    """Source files and manifests of a checked-out project (tests included: they break too)."""
    out: list[tuple[str, str]] = []
    stack = [root]
    while stack and len(out) < MAX_PROJECT_FILES:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name not in PROJECT_EXCLUDED_DIRS and not entry.name.startswith("."):
                    stack.append(entry)
                continue
            rel = entry.relative_to(root).as_posix()
            if not (entry.name.endswith(PROJECT_FILE_SUFFIXES) or PROJECT_MANIFESTS.match(entry.name) or is_requirements_file(rel)):
                continue
            try:
                if entry.stat().st_size > MAX_PROJECT_FILE_BYTES:
                    continue
                out.append((rel, entry.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
    return out


def tag_for_version(tags: list[str], version: str, package_name: str | None = None) -> str | None:
    candidates = [version, f"v{version}"]
    if package_name:
        candidates += [f"{package_name}-{version}", f"{package_name}@{version}", f"{package_name}-v{version}"]
    candidates += [f"release-{version}", f"rel-{version}", f"version-{version}"]
    by_lower = {t.lower(): t for t in tags}
    for c in candidates:
        if c.lower() in by_lower:
            return by_lower[c.lower()]
    return None
