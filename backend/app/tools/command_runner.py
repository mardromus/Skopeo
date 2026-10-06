"""Sandboxed subprocess execution: allowlist, timeout, scrubbed env, output limits, redaction."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.observability import get_logger
from app.security.command_policy import check_command
from app.security.redaction import redact

log = get_logger("tools.command")

# Environment variables passed through to child processes. Everything else (tokens, keys,
# cloud credentials) is dropped so repository code can never read Skopeo's secrets.
_ENV_PASSTHROUGH = (
    "PATH",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "VIRTUAL_ENV",
)


class ToolTimeoutError(TimeoutError):
    pass


@dataclass
class CommandResult:
    argv: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    truncated: bool = False
    cwd: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def summary(self, limit: int = 1500) -> dict:
        return {
            "command": " ".join(self.argv_display()),
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "timed_out": self.timed_out,
            "stdout_tail": self.stdout[-limit:],
            "stderr_tail": self.stderr[-limit // 2 :],
            "truncated": self.truncated,
        }

    def argv_display(self) -> list[str]:
        out = []
        for a in self.argv:
            if a == sys.executable:
                out.append("python")
            else:
                out.append(a)
        return out


def scrubbed_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k.upper() in _ENV_PASSTHROUGH}
    env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_ASKPASS": "",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONIOENCODING": "utf-8",
            "NO_COLOR": "1",
        }
    )
    if extra:
        env.update(extra)
    return env


def _limit_resources() -> None:  # pragma: no cover - POSIX only
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    os.setsid()


class SafeCommandRunner:
    def __init__(self, default_timeout: float, max_output_bytes: int) -> None:
        self.default_timeout = default_timeout
        self.max_output_bytes = max_output_bytes

    def run(
        self,
        argv: list[str],
        cwd: Path,
        *,
        repo_root: Path | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        check_command(argv, cwd, repo_root)
        timeout = timeout or self.default_timeout
        started = time.monotonic()
        popen_kwargs: dict = {
            "cwd": str(cwd),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "env": scrubbed_env(env),
            "shell": False,
        }
        if os.name == "posix":  # pragma: no cover - exercised in Docker
            popen_kwargs["preexec_fn"] = _limit_resources
        else:
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        proc = subprocess.Popen(argv, **popen_kwargs)  # noqa: S603 - argv allowlisted above
        timed_out = False
        try:
            out_b, err_b = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill(proc)
            out_b, err_b = proc.communicate()
        duration_ms = int((time.monotonic() - started) * 1000)
        truncated = len(out_b) > self.max_output_bytes or len(err_b) > self.max_output_bytes
        stdout = redact(out_b[: self.max_output_bytes].decode("utf-8", errors="replace"))
        stderr = redact(err_b[: self.max_output_bytes].decode("utf-8", errors="replace"))
        result = CommandResult(
            argv=list(argv),
            exit_code=None if timed_out else proc.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            timed_out=timed_out,
            truncated=truncated,
            cwd=str(cwd),
        )
        log.info(
            "command executed",
            extra={
                "event_type": "tool_command",
                "data": {
                    "argv": result.argv_display()[:8],
                    "exit_code": result.exit_code,
                    "duration_ms": duration_ms,
                    "timed_out": timed_out,
                },
            },
        )
        return result

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        try:
            if os.name == "posix":  # pragma: no cover
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except OSError:
            pass
