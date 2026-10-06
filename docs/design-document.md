# Skopeo — design document

## 1. Problem

Before adopting, upgrading or shipping a codebase, an engineering lead needs to know what is
actually risky in it. Today that means running half a dozen tools (vulnerability scanners,
linters, coverage, license checkers) whose outputs are siloed, noisy and full of false positives.
Nobody connects "this dependency is vulnerable" with "it is used in the login path" and "that path
has no tests", and nobody checks whether the scanner's scary finding is a dummy value in a test
fixture. The result is either alert fatigue or missed compound risks.

## 2. Target users

* **Engineering leads and tech-debt owners** deciding what to fix first.
* **Security reviewers** triaging scanner output before a release or an acquisition.
* **Maintainers** evaluating a dependency or a repository before adopting it.
* **Evaluators** of the system itself, who need to see why each conclusion was reached.

## 3. Architecture

Full diagrams: [architecture.md](architecture.md). In short:

```
User → React UI → FastAPI → InvestigationService → LangGraph state machine
        Orchestrator ⇄ 8 parallel specialists ⇄ Evidence Store (blackboard)
        → Correlation → Verification / Red-Team → Risk → Recommendation → Human approval → GitHub (draft only)
```

All agents read and write the Evidence Store (SQLite through SQLAlchemy; PostgreSQL-ready). The
orchestrator chooses every transition after inspecting it.

## 4. Agent responsibilities

| # | Agent | Responsibility |
| --- | --- | --- |
| 1 | **Orchestrator Agent** | inspects the repository profile, plans, monitors results, accepts or declines investigation requests, schedules follow-ups and retries, re-plans, routes to correlation / verification / risk, enforces budgets |
| 2 | **Security Agent** | secrets, insecure code patterns (AST), prompt-injection content, dependency usage and reachability, optional Semgrep / Dependabot |
| 3 | **Dependency Health Agent** | ecosystem detection, manifest parsing, OSV advisories, freshness, abandonment, pinning, conflicts |
| 4 | **Code Quality Agent** | complexity, size, nesting, swallowed exceptions, duplication, data-access maintainability stance |
| 5 | **API Compatibility Agent** | public API, deprecations in use, history-based breaking changes, dependency upgrade compatibility |
| 6 | **Test Reliability Agent** | test discovery, assertion quality, flakiness indicators, test-to-code mapping, real test execution with coverage |
| 7 | **License Compliance Agent** | license identification, metadata consistency, SPDX headers, dependency license compatibility |
| 8 | **Maintenance Activity Agent** | commit cadence, contributor concentration, stale modules, releases, pull-request activity |
| 9 | **Performance Agent** | static suspects (N+1, network in loops) vs measured issues via benchmarks |
| 10 | **Correlation Agent** | compound risks, shared root causes, causal chains, dependency links, duplicates, contradictions |
| 11 | **Verification / Red-Team Agent** | adversarial checks; verifies, rejects or requests more evidence |
| 12 | **Risk Assessment Agent** | scores verified findings and compound risks, P0–P4 with explanations |
| 13 | **Recommendation Agent** | actionable remediation; GitHub issue and draft-PR proposals requiring approval |

Details, modes and tools: [agent-specifications.md](agent-specifications.md).

## 5. Orchestration pattern

* **Orchestrator–worker.** The orchestrator produces `AgentTask`s (agent, objective, mode,
  strategy, focus, trigger, attempt, round). Workers execute them and return `TaskResult`s.
* **Blackboard.** Workers do not call each other. They publish findings, evidence and investigation
  requests to the Evidence Store; the orchestrator, the correlation agent and the red team read it.
  Later work is driven by what is on the board, which is how one agent's discovery changes another
  agent's task.
* **Adaptive routing.** `review` runs after every phase and returns one of
  `dispatch | correlate | verify | assess | finalize`. The route depends on new failures, open
  requests, new high-impact findings, whether the blackboard changed since the last correlation,
  and whether findings remain unchallenged. In live mode the LLM proposes the decision and
  guardrails validate it; in mock mode a transparent policy makes it.
* **Parallel execution.** Tasks fan out with LangGraph `Send`; the next `review` runs when the
  whole superstep completes. The reference case runs eight agents at once.
* **Event-driven communication.** Every message (`agent_message`, `investigation_requested`,
  `challenge`, `request_decided`, `replan`, …) is a persisted event with sender and receiver.

Why not one agent? No single agent has all the evidence or expertise. Skopeo uses independent
specialist investigations, cross-agent correlation and an adversarial verification stage, and the
final risk assessment only trusts findings that survive verification. Why not a fixed pipeline?
Because the work required depends on what is found: a vulnerable auth library triggers three
follow-ups, an unmeasured performance claim triggers a benchmark, a crashed agent triggers a
degraded retry, and none of that is known before the first round runs.

## 6. Agent state

* **Graph state** (`app/graph/state.py`): investigation id, depth, round, pending tasks, the list of
  task results (reducer `operator.add` so parallel branches merge), reviewed task ids, completed
  task keys (deduplication), reviewed finding ids, escalated packages, blackboard version at the
  last correlation / verification, round counters, next step, fatal error.
* **Per-run context** (`AgentContext`): task, run id, iteration and tool-call counters, deadline,
  stop flag, coverage notes. Persisted as an `agent_runs` row when the run ends.
* **Knowledge**: only in the database. An agent that needs to know something reads the blackboard.

## 7. Evidence Store

Entities: `investigations`, `agent_runs`, `findings`, `evidence`, `correlations`,
`verifications`, `risks`, `recommendations`, `action_proposals`, `execution_events`,
`investigation_requests` (UUID keys, indexed by investigation, agent, severity, status, created_at;
Alembic migration `0001`). Rules enforced at write time:

* a finding without evidence is refused unless it is explicitly a hypothesis (confidence capped at 0.40);
* evidence paths must be repository-relative; cited line ranges are hashed so the red team can
  detect stale or fabricated evidence;
* every text field is redacted before it is stored;
* confidence is computed from the evidence (below), never supplied by an agent.

**Confidence model** (`services/confidence.py`): noisy-OR of evidence weights by source type
(benchmark 0.92, test 0.88, dependency 0.80, git/GitHub 0.70, static analysis 0.65, LLM 0.35),
then +0.10 reproduced, ±0.05/−0.25 reachability, +0.05 per corroborating agent (max 0.15),
−0.10 static suspect, −0.15 per contradiction (max 0.30), +0.10 verified / −0.10 needs evidence,
rejected capped at 0.10, hypotheses capped at 0.40, clamped to [0.01, 0.99]. Each factor is stored
and shown in the UI.

## 8. Correlation

Candidates come from typed links between findings — same package, same file, same security-critical
component, same code subject, opposite stances — and each candidate is assessed by the LLM (or the
policy) which may reject it. Six relationship types; compound risks carry a multiplier
`1 + 0.25 × (distinct dimensions − 1)` (max 2.0). Contradictions are sent to the red team. A
correlation only affects risk after the red team has verified its members.

## 9. Verification

The red team distrusts the other agents and re-derives facts with its own tools: it re-hashes cited
lines, rebuilds the import graph to test reachability, re-runs failing tests, recomputes metrics,
checks placeholders and production references for secrets, compares claimed severity with advisory
data, checks mitigations, and refuses to verify unmeasured medium+ performance claims. It returns
**verified**, **rejected** or **needs_more_evidence** (which becomes an investigation request). It
runs again when new evidence arrives, up to `MAX_VERIFICATION_ROUNDS`. Correlations are ruled on
from their members.

## 10. Risk assessment

```
raw   = severity_weight × confidence × impact × exploitability × correlation_multiplier
score = 100 × (1 − e^(−2.2 · raw))      P0 ≥ 80 · P1 ≥ 60 · P2 ≥ 35 · P3 ≥ 12 · P4
```

Severity weights: critical 1.0, high 0.75, medium 0.5, low 0.25, info 0.05. Impact: 1.0 for
security-critical components, 0.8 production dependency/security code, 0.7 production code, 0.6
license exposure, 0.3 test-only. Exploitability: 0.8 reachable from entrypoints, 0.65 reachable,
0.25 unreachable, 0.6 measured performance vs 0.35 static. Compound risks are scored once on their
own entry. Overall risk combines the top ten with halving weights. Only verified findings enter.

## 11. Fault isolation

Every agent runs behind `run_agent_isolated` (`graph/runtime.py`): exceptions, timeouts and budget
overruns become a `FAILED`/`TIMEOUT` AgentRun with the redacted error; evidence already written is
kept; an `agent_failed` event notifies the orchestrator; parallel siblings are unaffected. The
orchestrator retries once with the agent's fallback strategy or reports the capability as
unavailable. Coordination agents are isolated the same way. The final coverage table marks each
specialist `complete`, `partial`, `unavailable` or `skipped`, and any limitation makes the case
`completed_with_limitations`. A controlled failure (`SKOPEO_FAULT_INJECTION`) is used in the demo
and in tests; its error message says it was injected.

## 12. Security

See [security.md](security.md): URL validation, argv allowlist (no shell, no LLM-originated
commands), hardened clone, path-traversal protection, trust policy for executing repository code,
resource limits, scrubbed child environments, pervasive redaction, a one-way prompt-injection
boundary, DRY_RUN and human approval for every outward action, hardened container.

## 13. Input schema

```json
{ "repository_url": "https://github.com/owner/repository", "branch": "main",
  "analysis_depth": "quick | standard | deep", "enable_github_actions": false }
```

Validated by `InvestigationCreate` (unknown fields rejected). Demo: `POST /api/demo/investigations`
with `fault_injection` and `step_delay_ms`.

## 14. Output schema

`GET /api/investigations/{id}/report` returns `investigation_id`, `repository`, `status`,
`overall_risk {score, level}`, `agent_summary`, `plan`, `findings`, `correlations`,
`verified_findings`, `rejected_findings`, `insufficient_evidence_findings`, `verifications`,
`risks`, `recommendations`, `actions`, `requests`, `coverage`, `execution_summary`, `events`.
Field-level schemas: [api.md](api.md).

## 15. Failure modes

| Failure | Behaviour |
| --- | --- |
| Clone fails (private repo, bad branch, network) | investigation `failed` with the git error; no agents run |
| A specialist crashes or times out | run `FAILED`/`TIMEOUT`, retried once, then reported unavailable; others continue |
| Tool missing (Semgrep, harness) | limitation or degraded strategy; never a silent pass |
| Advisory / registry / GitHub API unreachable or rate-limited | INSUFFICIENT EVIDENCE for the affected packages; limitation recorded |
| LLM returns invalid or unsafe output | deterministic policy decides; `policy-fallback` recorded |
| LLM budget exhausted | remaining decisions made by policy |
| Red team cannot settle a claim | finding stays `needs_more_evidence`, excluded from risk |
| Runaway investigation | round limits, per-agent budgets, 80 % deadline guard routes to assessment, hard timeout fails the case |
| User cancels | agents stop at their next step; case `cancelled` |
| Untrusted code would need executing | refused; reported as a limitation |

## 16. Example investigation

The reference case ([demo-scenario.md](demo-scenario.md), trace in
[execution-trace.md](execution-trace.md)): eight specialists start together; the performance agent
fails on a controlled tool error and is retried with `static_only`; the dependency agent's request
about PyJWT 1.7.1 makes the orchestrator add three follow-ups; the correlation agent builds a
compound authentication upgrade risk from four agents' findings; the red team rejects two fake AWS
credentials, verifies the vulnerable dependency through its own import graph, reproduces a failing
test, and demands a benchmark for the N+1 claim; the benchmark measures 51 → 2001 queries; round 2
verifies the N+1 finding and rejects the opposing "acceptable" assessment; the compound risk is P0
(94.5); recommendations and a draft-PR proposal await approval; the case ends
`completed_with_limitations`.

## 17. Technology choices

| Choice | Why |
| --- | --- |
| Python 3.12, FastAPI, Pydantic 2 | typed schemas end-to-end; validation of every LLM output |
| LangGraph | explicit state machine with conditional edges, `Send` fan-out and fan-in, recursion limits |
| SQLite + SQLAlchemy 2 + Alembic | a real relational blackboard with migrations; portable to PostgreSQL |
| `httpx` provider abstraction | OpenAI, any OpenAI-compatible server, or the mock — no vendor lock-in |
| OSV.dev + PyPI/npm, offline snapshot | real advisory data; deterministic offline demos without fabricating anything |
| Python `ast`, coverage.py, pytest | deterministic tools before any LLM call |
| React, TypeScript, Vite, Recharts | typed client mirroring the API schemas |
| Docker Compose | one command to run API + UI with a hardened container |

## 18. Limitations

* Deep static analysis is Python-first. JavaScript/TypeScript, Java, Go and Rust get manifest,
  advisory, license and regex coverage, not AST or data-flow analysis; their test suites are not executed.
* Test execution of real repositories requires opting in to sandboxed execution and the project's
  dependencies being installable; otherwise the Test agent is static only.
* Reachability is import-graph based; dynamic imports and framework routing can be missed (reported
  as inconclusive, not as unreachable).
* Transitive Python dependencies are not resolved without a lockfile.
* Benchmarks follow a simple protocol (one JSON line per script); a repository without such scripts
  cannot have performance claims measured, so they stay INSUFFICIENT EVIDENCE.
* In mock mode the agents' "reasoning" is a transparent rule-based policy. The event flow and state
  transitions are genuine, but the natural-language judgement of a model is absent.
* The API has no authentication; deploy it behind your own gateway.
