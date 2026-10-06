"""RepositoryTools — the safe tool layer agents use to inspect a cloned repository.

Every method:
* resolves paths through ``safe_join`` (no traversal, no symlink escapes);
* enforces size limits (files, results, output);
* runs subprocesses only through ``SafeCommandRunner`` (allowlist + timeout + scrubbed env);
* treats repository content as untrusted data.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import Settings
from app.security.paths import PathTraversalError, safe_join
from app.tools.command_runner import CommandResult, SafeCommandRunner

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".idea",
    ".vscode",
    "target",
    ".gradle",
    "coverage",
    ".next",
}
BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".bmp",
    ".webp",
    ".pdf",
    ".zip",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".7z",
    ".jar",
    ".war",
    ".class",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".bin",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".eot",
    ".mp3",
    ".mp4",
    ".mov",
    ".avi",
    ".wasm",
    ".pyc",
    ".pyo",
    ".db",
    ".sqlite",
    ".parquet",
}
LANGUAGE_BY_EXT = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".kt": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".swift": "Swift",
    ".scala": "Scala",
    ".sql": "SQL",
    ".sh": "Shell",
}
TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|__tests__|spec|specs|testing)(/|$)|(^|/)(test_[^/]+\.py|[^/]+_test\.(py|go)|[^/]+\.(test|spec)\.[jt]sx?)$"
)
FIXTURE_PATH_RE = re.compile(r"(^|/)(fixtures?|testdata|test_data|mocks?|examples?|samples?|docs?)(/|$)", re.IGNORECASE)


class BinaryFileError(ValueError):
    pass


class FileTooLargeError(ValueError):
    pass


class ToolUnavailableError(RuntimeError):
    """A required external tool is not available. Agents fail (or degrade) on this."""


@dataclass
class SearchHit:
    file: str
    line: int
    text: str


@dataclass
class Commit:
    sha: str
    author: str
    date: datetime
    subject: str
    files: list[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0


@dataclass
class RepositoryHandle:
    root: Path
    workspace: Path
    source: str
    full_name: str
    url: str
    branch: str
    commit_sha: str | None = None
    trusted_execution: bool = False
    profile: dict[str, Any] = field(default_factory=dict)


def is_test_path(path: str) -> bool:
    return bool(TEST_PATH_RE.search(path))


def is_fixture_path(path: str) -> bool:
    return bool(FIXTURE_PATH_RE.search(path))


class RepositoryTools:
    def __init__(self, handle: RepositoryHandle, runner: SafeCommandRunner, settings: Settings) -> None:
        self.handle = handle
        self.root = handle.root
        self.runner = runner
        self.settings = settings
        self._files: list[str] | None = None
        self._text_cache: dict[str, str] = {}

    # ------------------------------------------------------------------ files
    def list_files(self, suffixes: Iterable[str] | None = None, include_tests: bool = True) -> list[str]:
        if self._files is None:
            files: list[str] = []
            for path in sorted(self._walk(self.root)):
                files.append(path)
                if len(files) >= self.settings.max_repo_files:
                    break
            self._files = files
        result = self._files
        if suffixes is not None:
            sfx = tuple(s.lower() for s in suffixes)
            result = [f for f in result if f.lower().endswith(sfx)]
        if not include_tests:
            result = [f for f in result if not is_test_path(f)]
        return list(result)

    def _walk(self, directory: Path, prefix: str = "") -> Iterable[str]:
        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name)
        except OSError:
            return
        for entry in entries:
            if entry.is_symlink():
                continue  # never follow symlinks from untrusted repositories
            rel = f"{prefix}{entry.name}"
            if entry.is_dir():
                if entry.name in SKIP_DIRS or entry.name.endswith(".egg-info"):
                    continue
                yield from self._walk(entry, rel + "/")
            elif entry.is_file():
                if Path(entry.name).suffix.lower() in BINARY_EXTENSIONS:
                    continue
                yield rel

    def exists(self, relative: str) -> bool:
        try:
            path = safe_join(self.root, relative)
        except PathTraversalError:
            return False
        return path.is_file() and not path.is_symlink()

    def get_file(self, relative: str, max_bytes: int | None = None) -> str:
        if relative in self._text_cache:
            return self._text_cache[relative]
        path = safe_join(self.root, relative)
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError(relative)
        limit = max_bytes or self.settings.max_file_bytes
        size = path.stat().st_size
        if size > limit:
            raise FileTooLargeError(f"{relative} is {size} bytes (limit {limit})")
        data = path.read_bytes()
        if b"\x00" in data[:8192]:
            raise BinaryFileError(relative)
        text = data.decode("utf-8", errors="replace")
        self._text_cache[relative] = text
        return text

    def try_get_file(self, relative: str) -> str | None:
        try:
            return self.get_file(relative)
        except (OSError, ValueError, PathTraversalError):
            return None

    def get_lines(self, relative: str, start: int, end: int) -> list[str]:
        text = self.get_file(relative)
        lines = text.splitlines()
        return lines[max(0, start - 1) : max(start, end)]

    def line_hash(self, relative: str, start: int | None, end: int | None) -> str | None:
        """sha256 of the referenced lines — lets the red-team detect stale/fabricated evidence."""
        text = self.try_get_file(relative)
        if text is None:
            return None
        if start is None:
            payload = text
        else:
            lines = text.splitlines()
            payload = "\n".join(lines[max(0, start - 1) : (end or start)])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def search_repository(
        self,
        pattern: str | re.Pattern[str],
        *,
        file_filter: Callable[[str], bool] | None = None,
        suffixes: Iterable[str] | None = None,
        max_results: int | None = None,
        flags: int = 0,
    ) -> list[SearchHit]:
        regex = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern, flags)
        limit = max_results or self.settings.max_search_results
        hits: list[SearchHit] = []
        for rel in self.list_files(suffixes=suffixes):
            if file_filter and not file_filter(rel):
                continue
            text = self.try_get_file(rel)
            if text is None:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if len(line) > 2000:
                    line = line[:2000]
                if regex.search(line):
                    hits.append(SearchHit(file=rel, line=lineno, text=line.strip()[:400]))
                    if len(hits) >= limit:
                        return hits
        return hits

    # -------------------------------------------------------------------- git
    def _git(self, *args: str, timeout: float | None = None) -> CommandResult:
        return self.runner.run(
            ["git", "-c", f"safe.directory={self.root.as_posix()}", *args], self.root, repo_root=self.root, timeout=timeout
        )

    def has_git(self) -> bool:
        return (self.root / ".git").is_dir()

    def get_git_log(self, max_count: int = 500, paths: list[str] | None = None) -> list[Commit]:
        if not self.has_git():
            return []
        args = [
            "log",
            f"--max-count={int(max_count)}",
            "--no-color",
            "--date=iso-strict",
            "--numstat",
            "--pretty=format:@@@%H%x1f%an%x1f%aI%x1f%s",
        ]
        if paths:
            args += ["--", *paths]
        res = self._git(*args)
        if not res.ok:
            raise RuntimeError(f"git log failed: {res.stderr[:300]}")
        commits: list[Commit] = []
        current: Commit | None = None
        for line in res.stdout.splitlines():
            if line.startswith("@@@"):
                sha, author, date, subject = (line[3:].split("\x1f") + ["", "", "", ""])[:4]
                try:
                    when = datetime.fromisoformat(date)
                except ValueError:
                    continue
                current = Commit(sha=sha, author=author, date=when, subject=subject[:200])
                commits.append(current)
            elif current is not None and line.strip():
                parts = line.split("\t")
                if len(parts) == 3:
                    ins, dele, path = parts
                    current.files.append(path)
                    current.insertions += int(ins) if ins.isdigit() else 0
                    current.deletions += int(dele) if dele.isdigit() else 0
        return commits

    def get_git_diff(self, rev_a: str, rev_b: str = "HEAD", paths: list[str] | None = None) -> str:
        for rev in (rev_a, rev_b):
            if not re.fullmatch(r"[A-Za-z0-9_.~^/\-]{1,100}", rev) or rev.startswith("-"):
                raise ValueError(f"invalid revision {rev!r}")
        args = ["diff", "--no-color", "--no-ext-diff", f"{rev_a}..{rev_b}"]
        if paths:
            args += ["--", *paths]
        res = self._git(*args)
        return res.stdout if res.ok else ""

    def git_show_file(self, rev: str, path: str) -> str | None:
        if not re.fullmatch(r"[A-Za-z0-9_.~^\-]{1,100}", rev) or rev.startswith("-"):
            raise ValueError("invalid revision")
        safe_join(self.root, path)  # validates the path shape
        res = self._git("show", f"{rev}:{path}")
        return res.stdout if res.ok else None

    def list_tags(self) -> list[tuple[str, str]]:
        if not self.has_git():
            return []
        res = self._git("for-each-ref", "--sort=-creatordate", "--format=%(refname:short)%09%(creatordate:iso-strict)", "refs/tags")
        out = []
        for line in res.stdout.splitlines():
            if "\t" in line:
                name, date = line.split("\t", 1)
                out.append((name, date))
        return out

    # ---------------------------------------------------------- manifests
    def inspect_manifest(self) -> list[str]:
        from app.tools.manifests import MANIFEST_NAMES

        return [f for f in self.list_files() if Path(f).name in MANIFEST_NAMES or re.match(r"(.*/)?requirements[^/]*\.txt$", f)]

    def inspect_dependencies(self) -> list[Any]:
        from app.tools.manifests import parse_dependencies

        return parse_dependencies(self)

    # ------------------------------------------------------------ execution
    def _require_trusted_execution(self, what: str) -> None:
        if not (self.handle.trusted_execution or self.settings.skopeo_sandbox_execution):
            raise PermissionError(f"{what} refused: repository code is untrusted and SKOPEO_SANDBOX_EXECUTION is disabled")

    def run_tests(self, test_paths: list[str], source_packages: list[str], timeout: float | None = None) -> dict[str, Any]:
        """Run pytest under coverage. Returns parsed results. Never fabricates output."""
        self._require_trusted_execution("Test execution")
        for p in test_paths:
            safe_join(self.root, p)
        out_dir = self.handle.workspace / "artifacts"
        out_dir.mkdir(parents=True, exist_ok=True)
        data_file = out_dir / ".coverage"
        json_file = out_dir / "coverage.json"
        for f in (data_file, json_file):
            if f.exists():
                f.unlink()
        env = {"PYTHONPATH": str(self.root), "COVERAGE_FILE": str(data_file)}
        argv = [sys.executable, "-B", "-m", "coverage", "run", f"--data-file={data_file}"]
        if source_packages:
            argv.append("--source=" + ",".join(source_packages))
        argv += ["-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider", "--no-header", "--color=no", *test_paths]
        res = self.runner.run(argv, self.root, repo_root=self.root, timeout=timeout or self.settings.command_timeout_seconds, env=env)
        coverage: dict[str, Any] | None = None
        if data_file.exists():
            cov_res = self.runner.run(
                [sys.executable, "-B", "-m", "coverage", "json", f"--data-file={data_file}", "-o", str(json_file), "--quiet"],
                self.root,
                repo_root=self.root,
                timeout=60,
                env=env,
            )
            if cov_res.ok and json_file.exists():
                coverage = json.loads(json_file.read_text(encoding="utf-8"))
        return {"result": res, "pytest": parse_pytest_output(res.stdout + "\n" + res.stderr), "coverage": coverage}

    def rerun_test(self, node_id: str, timeout: float | None = None) -> CommandResult:
        self._require_trusted_execution("Test reproduction")
        file_part = node_id.split("::", 1)[0]
        safe_join(self.root, file_part)
        if not re.fullmatch(r"[A-Za-z0-9_./\-]+(::[A-Za-z0-9_\[\]\-.]+)*", node_id):
            raise ValueError("invalid test node id")
        return self.runner.run(
            [sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", "--color=no", node_id],
            self.root,
            repo_root=self.root,
            timeout=timeout or 60,
            env={"PYTHONPATH": str(self.root)},
        )

    def run_benchmark(self, script: str, timeout: float | None = None) -> CommandResult:
        self._require_trusted_execution("Benchmark execution")
        safe_join(self.root, script)
        return self.runner.run(
            [sys.executable, "-B", script, "--json"],
            self.root,
            repo_root=self.root,
            timeout=timeout or 90,
            env={"PYTHONPATH": str(self.root)},
        )

    def run_static_analysis(self, rules_file: Path, timeout: float | None = None) -> dict[str, Any] | None:
        """Run Semgrep with a local ruleset when available. Returns None when Semgrep is not installed."""
        semgrep = shutil.which("semgrep")
        if not semgrep:
            return None
        res = self.runner.run(
            [
                semgrep,
                "scan",
                "--config",
                str(rules_file),
                "--json",
                "--metrics=off",
                "--quiet",
                "--disable-version-check",
                "--timeout",
                "20",
                ".",
            ],
            self.root,
            repo_root=self.root,
            timeout=timeout or 180,
        )
        try:
            return {"result": res, "data": json.loads(res.stdout or "{}")}
        except json.JSONDecodeError:
            return {"result": res, "data": {}}


_PYTEST_SUMMARY_RE = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|warnings?)")
_PYTEST_FAILED_RE = re.compile(r"^(FAILED|ERROR) (\S+)(?: - (.*))?$", re.MULTILINE)


def parse_pytest_output(output: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    summary_line = ""
    for line in output.splitlines()[::-1]:
        if re.search(r"\b(passed|failed|error|errors|no tests ran)\b", line) and (" in " in line or "no tests ran" in line):
            summary_line = line.strip("= ").strip()
            break
    for num, kind in _PYTEST_SUMMARY_RE.findall(summary_line):
        key = {"error": "errors", "errors": "errors", "warning": "warnings", "warnings": "warnings"}.get(kind, kind)
        counts[key] = int(num)
    failures = [
        {"kind": kind.lower(), "node_id": node, "message": (msg or "")[:300]} for kind, node, msg in _PYTEST_FAILED_RE.findall(output)
    ]
    return {"summary": summary_line, "counts": counts, "failures": failures}
