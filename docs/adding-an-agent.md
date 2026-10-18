# Guide: Adding a Custom Specialist Agent

This guide walks through creating and registering a new specialist agent in Skopeo.

---

## 1. Overview

Skopeo agents are independent modules located under `backend/app/agents/`. Specialist agents:
1. Inherit from `SpecialistAgent` (defined in [`app/agents/base.py`](../backend/app/agents/base.py)).
2. Receive explicit dependencies through `AgentContext` (no hidden global state).
3. Produce their own list of execution steps in `plan(ctx)`.
4. Publish structured findings, evidence, and follow-up requests to the shared blackboard (the Evidence Store).
5. Are registered in [`app/agents/registry.py`](../backend/app/agents/registry.py).

---

## 2. Agent Structure

A specialist agent class defines class-level metadata and implements `plan()`:

```python
"""Example: Infrastructure as Code (IaC) and configuration specialist."""

from __future__ import annotations

from typing import ClassVar

from app.agents.base import AgentContext, SpecialistAgent, Step
from app.schemas import FindingDraft


class InfrastructureAgent(SpecialistAgent):
    name: ClassVar[str] = "infrastructure"
    display_name: ClassVar[str] = "Infrastructure & IaC"
    description: ClassVar[str] = (
        "Inspects Dockerfiles, Kubernetes manifests, and Terraform files "
        "for misconfigurations, unpinned bases, and security drift."
    )
    modes: ClassVar[list[str]] = ["full", "container_only"]

    def plan(self, ctx: AgentContext) -> list[Step]:
        """Construct the step sequence for this run."""
        steps: list[Step] = [
            ("scan_dockerfiles", self._scan_dockerfiles),
        ]
        if ctx.task.mode == "full":
            steps.append(("scan_manifests", self._scan_manifests))
        return steps

    def _scan_dockerfiles(self, ctx: AgentContext) -> list[Step] | None:
        """Inspect Dockerfiles using the safe repository tools."""
        dockerfiles = ctx.repo.find_files("Dockerfile*")
        for path in dockerfiles:
            content = ctx.repo.read_text(path)
            if "FROM python:latest" in content:
                # Post finding draft to blackboard
                ctx.finding(
                    rule_id="iac.unpinned_base_image",
                    title="Unpinned Docker base image tag",
                    description=f"{path} uses ':latest' tag, causing non-deterministic builds.",
                    severity="medium",
                    file_path=path,
                    line_start=1,
                    confidence=0.9,
                    suggested_fix="Pin base image to an exact digest or semantic tag.",
                )
        return None

    def _scan_manifests(self, ctx: AgentContext) -> list[Step] | None:
        # Additional step implementation
        return None
```

---

## 3. Working with `AgentContext`

All runtime capabilities are provided safely via `ctx`:

### Repository & Tools
- `ctx.repo.find_files(pattern)`: Glob search for files safely within the workspace boundary.
- `ctx.repo.read_text(rel_path)`: Read file contents (enforcing path traversal protections).
- `ctx.repo.ast_parse(rel_path)`: Obtain a cached Python AST tree.

### Blackboard Access
- `ctx.finding(...)`: Publish a new candidate finding to the Evidence Store.
- `ctx.evidence(finding_id, kind, body)`: Attach supporting proof (code excerpts, tool outputs, diffs).
- `ctx.request_investigation(objective, ...)`: Request another specialist to investigate cross-domain evidence (e.g. asking the Security agent to trace reachability).

### Structured LLM Decisions
Specialists can use the LLM to analyze complex snippets using typed Pydantic schemas and deterministic fallback policies:

```python
decision = ctx.decide(
    task_type="iac_analysis",
    schema=IaCAnalysisOutput,
    policy=lambda: deterministic_fallback_scan(content),
    role="Infrastructure security expert",
    task="Review configuration for privilege escalation risks",
    structured={"file": path},
    untrusted={"content": content},
)
```

---

## 4. Registering the Agent

Register your specialist in [`backend/app/agents/registry.py`](../backend/app/agents/registry.py):

```python
# 1. Import your agent
from app.agents.infrastructure import InfrastructureAgent

# 2. Add to SPECIALIST_CLASSES dictionary
SPECIALIST_CLASSES: dict[str, type[SpecialistAgent]] = {
    # ... existing specialists ...
    InfrastructureAgent.name: InfrastructureAgent,
}
```

---

## 5. Adding Red-Team & Orchestrator Awareness

1. **Verification Rules**: Ensure the Red-Team Agent ([`app/agents/verification.py`](../backend/app/agents/verification.py)) knows how to challenge findings from your rule domain (e.g., distinguishing test docker-compose setups from production manifests).
2. **Orchestrator Profile**: In [`app/agents/orchestrator.py`](../backend/app/agents/orchestrator.py), update repository profiling so your agent is dispatched when matching configuration files are present.

---

## 6. Testing Your Agent

Create unit and integration tests under `backend/tests/`:

```python
import pytest
from app.agents.infrastructure import InfrastructureAgent


def test_infrastructure_agent_plan():
    agent = InfrastructureAgent()
    # Test planning step generation with mock context
    assert "scan_dockerfiles" in [label for label, _ in agent.plan(mock_ctx)]
```

Run tests and linters locally:
```bash
cd backend
ruff check .
ruff format --check .
python -m pytest tests/test_agents.py
```
