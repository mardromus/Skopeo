"""Command allowlist.

Skopeo never executes shell strings and never executes commands proposed by an LLM.
Every subprocess is an argv list built by Skopeo code and checked here first.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from app.security.paths import PathTraversalError, safe_join
from app.security.url_validation import InvalidRepositoryURL, validate_repository_url


class CommandNotAllowedError(PermissionError):
    pass


GIT_READ_SUBCOMMANDS = {"log", "diff", "show", "rev-parse", "ls-files", "ls-remote", "for-each-ref", "shortlog"}
GIT_WRITE_SUBCOMMANDS = {"clone", "init", "add", "commit"}  # clone into workspace / demo fixture init only
GIT_ALLOWED_CONFIG_KEYS = {
    "core.hooksPath",
    "core.symlinks",
    "core.fsmonitor",
    "core.autocrlf",
    "protocol.file.allow",
    "protocol.ext.allow",
    "transfer.fsckObjects",
    "advice.detachedHead",
    "init.defaultBranch",
    "user.name",
    "user.email",
    "commit.gpgsign",
    "safe.directory",
}
GIT_FORBIDDEN_FLAGS = (
    "--upload-pack",
    "--receive-pack",
    "--exec",
    "--output",
    "--ext-diff",
    "--textconv",
    "--config",
    "--template",
    "--git-dir",
    "--work-tree",
    "--separate-git-dir",
    "--reference",
    "-u",
    "-o",
)
CLONE_ALLOWED_FLAGS = {
    "--depth",
    "--branch",
    "--single-branch",
    "--no-tags",
    "--quiet",
    "--no-recurse-submodules",
    "--filter=blob:none",
    "--",
}

PYTHON_ALLOWED_MODULES = {"pytest", "coverage"}
PYTHON_ALLOWED_INTERPRETER_FLAGS = {"-B", "-s", "-u"}
BENCHMARK_SCRIPT_RE = re.compile(r"^(?:benchmarks?|bench|perf)/[A-Za-z0-9_\-/]+\.py$|^[A-Za-z0-9_\-/]*bench[A-Za-z0-9_\-]*\.py$")

SEMGREP_ALLOWED_FLAGS = {
    "scan",
    "--config",
    "--json",
    "--metrics=off",
    "--quiet",
    "--timeout",
    "--disable-version-check",
    "--no-git-ignore",
}

_ARG_SAFE_RE = re.compile(r"^[^\x00\r\n]*$")


def _is_python(executable: str) -> bool:
    name = Path(executable).name.lower()
    if executable == sys.executable or os.path.normcase(executable) == os.path.normcase(sys.executable):
        return True
    return name in {"python", "python3", "python.exe", "python3.exe"}


def check_command(argv: list[str], cwd: Path, repo_root: Path | None = None) -> None:
    """Raise CommandNotAllowedError unless argv matches an allowlisted shape."""
    if not argv or not all(isinstance(a, str) for a in argv):
        raise CommandNotAllowedError("argv must be a non-empty list of strings")
    for arg in argv:
        if not _ARG_SAFE_RE.match(arg):
            raise CommandNotAllowedError("control characters in arguments are not allowed")
    exe = argv[0]
    exe_name = Path(exe).name.lower().removesuffix(".exe")
    if exe_name == "git":
        _check_git(argv[1:])
    elif _is_python(exe):
        _check_python(argv[1:], cwd, repo_root)
    elif exe_name == "semgrep":
        _check_semgrep(argv[1:], cwd, repo_root)
    else:
        raise CommandNotAllowedError(f"executable not allowlisted: {exe_name}")


def _check_git(args: list[str]) -> None:
    i = 0
    while i < len(args) and args[i] == "-c":
        if i + 1 >= len(args):
            raise CommandNotAllowedError("dangling -c")
        key = args[i + 1].split("=", 1)[0]
        if key not in GIT_ALLOWED_CONFIG_KEYS:
            raise CommandNotAllowedError(f"git config override not allowed: {key}")
        i += 2
    if i >= len(args):
        raise CommandNotAllowedError("missing git subcommand")
    sub, rest = args[i], args[i + 1 :]
    if sub not in GIT_READ_SUBCOMMANDS | GIT_WRITE_SUBCOMMANDS:
        raise CommandNotAllowedError(f"git subcommand not allowed: {sub}")
    for arg in rest:
        if any(arg == f or arg.startswith(f + "=") for f in GIT_FORBIDDEN_FLAGS):
            raise CommandNotAllowedError(f"git flag not allowed: {arg}")
    if sub == "clone":
        _check_clone(rest)


def _check_clone(rest: list[str]) -> None:
    positional: list[str] = []
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg in ("--depth", "--branch"):
            if i + 1 >= len(rest):
                raise CommandNotAllowedError(f"{arg} needs a value")
            value = rest[i + 1]
            if arg == "--depth" and not value.isdigit():
                raise CommandNotAllowedError("--depth must be numeric")
            if arg == "--branch" and value.startswith("-"):
                raise CommandNotAllowedError("invalid branch for clone")
            i += 2
            continue
        if arg.startswith("-"):
            if arg not in CLONE_ALLOWED_FLAGS:
                raise CommandNotAllowedError(f"clone flag not allowed: {arg}")
        else:
            positional.append(arg)
        i += 1
    if len(positional) != 2:
        raise CommandNotAllowedError("clone requires exactly <url> <destination>")
    try:
        validate_repository_url(positional[0].removesuffix(".git"))
    except InvalidRepositoryURL as exc:
        raise CommandNotAllowedError(f"clone URL refused: {exc}") from exc


def _check_python(args: list[str], cwd: Path, repo_root: Path | None) -> None:
    i = 0
    while i < len(args) and args[i] in PYTHON_ALLOWED_INTERPRETER_FLAGS:
        i += 1
    if i >= len(args):
        raise CommandNotAllowedError("bare interpreter invocation is not allowed")
    if args[i] == "-c":
        raise CommandNotAllowedError("python -c is not allowed")
    if args[i] == "-m":
        if i + 1 >= len(args) or args[i + 1] not in PYTHON_ALLOWED_MODULES:
            raise CommandNotAllowedError("python module not allowlisted")
        if args[i + 1] == "coverage" and (i + 2 >= len(args) or args[i + 2] not in {"run", "json"}):
            raise CommandNotAllowedError("coverage subcommand not allowed")
        return
    script = args[i].replace("\\", "/")
    if not BENCHMARK_SCRIPT_RE.match(script):
        raise CommandNotAllowedError("only benchmark scripts may be executed directly")
    root = repo_root or cwd
    try:
        resolved = safe_join(root, script)
    except PathTraversalError as exc:
        raise CommandNotAllowedError(str(exc)) from exc
    if not resolved.is_file():
        raise CommandNotAllowedError("benchmark script does not exist")
    for extra in args[i + 1 :]:
        if extra not in {"--json", "--quick"}:
            raise CommandNotAllowedError(f"benchmark argument not allowed: {extra}")


def _check_semgrep(args: list[str], cwd: Path, repo_root: Path | None) -> None:
    if not args or args[0] != "scan":
        raise CommandNotAllowedError("only 'semgrep scan' is allowed")
    i = 1
    while i < len(args):
        arg = args[i]
        if arg in ("--config", "--timeout"):
            i += 2
            continue
        if arg.startswith("-") and arg not in SEMGREP_ALLOWED_FLAGS:
            raise CommandNotAllowedError(f"semgrep flag not allowed: {arg}")
        i += 1
