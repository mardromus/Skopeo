"""Controlled fault injection (chaos switch) used to demonstrate and test fault isolation.

Spec: comma separated ``agent@attempt`` items, e.g. ``performance_agent@1`` (fail first attempt
only) or ``license_agent@*`` (fail every attempt). Injected failures are always labelled as such
in the error message and the execution trace — they are never presented as genuine tool output.
"""

from __future__ import annotations

from app.tools.repository import ToolUnavailableError


def parse_spec(spec: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for item in (spec or "").split(","):
        item = item.strip()
        if not item:
            continue
        agent, _, attempt = item.partition("@")
        out.setdefault(agent.strip(), set()).add((attempt or "*").strip())
    return out


def should_fail(spec: str, agent: str, attempt: int) -> bool:
    rules = parse_spec(spec).get(agent)
    if not rules:
        return False
    return "*" in rules or str(attempt) in rules


def maybe_inject(spec: str, agent: str, attempt: int, tool: str) -> None:
    if should_fail(spec, agent, attempt):
        raise ToolUnavailableError(f"{tool} unavailable [controlled fault injection: SKOPEO_FAULT_INJECTION={agent}@{attempt}]")
