# Agent specifications

Thirteen agents, each an independent module under `backend/app/agents/`. All of them receive
their dependencies explicitly through `AgentContext` (`base.py`) and share no hidden state.

Every agent run is bounded by the same budgets (configurable, see `.env.example`):

| Limit | Default | Enforced in |
| --- | --- | --- |
| `AGENT_MAX_ITERATIONS` | 40 reasoning steps | `AgentContext.tick()` |
| `AGENT_MAX_TOOL_CALLS` | 400 | `AgentContext.tool()` |
| `AGENT_TIMEOUT_SECONDS` | 180 s | `asyncio.wait_for` in `graph/runtime.py` + cooperative stop flag |
| `AGENT_MAX_RETRIES` | 1 | orchestrator review policy |
| `INVESTIGATION_TIMEOUT_SECONDS` | 1200 s | graph invocation + orchestrator deadline guard |

Specialists inherit from `SpecialistAgent`: they build **their own step list** from the repository
profile, the assigned mode and what is already on the blackboard, announce it as an
`agent_message`, and may append steps when intermediate results warrant it (e.g. the Code Quality
agent adds an LLM review step only when it found complex functions).

---

## 1. Orchestrator (`orchestrator.py`)

| | |
| --- | --- |
| Job | Plan, monitor, re-plan, handle failures, route between phases |
| Inputs | Repository profile; after every phase: task results, failures, open investigation requests, new findings, blackboard version, budgets |
| Decisions | `orchestrator.plan` → `PlanDecision`; `orchestrator.review` → `ReviewDecision` (retries, request decisions, follow-ups, `next_step`) |
| Guardrails | unknown agents and invalid modes dropped; request IDs must exist; dedup against completed tasks; round/time budgets; verification cannot be skipped |
| Events | `plan_created`, `orchestrator_decision`, `request_decided`, `replan`, `agent_retry_scheduled`, `agent_message` |

Adaptive behaviour implemented in `_rule_review` (the policy) and accepted from the LLM in live mode:

* A failed agent is retried once with the agent's own fallback strategy (Performance:
  `ToolUnavailableError` → `static_only`). A second failure marks it unavailable and the
  investigation continues.
* An `impact_analysis` request about a vulnerable package fans out to Security
  (`dependency_usage`), API Compatibility (`upgrade_compatibility`) and Test Reliability
  (`dependency_coverage`); Performance is added only for performance-sensitive packages, and the
  replan event says why it was not.
* A `benchmark` request from the red team dispatches Performance in `benchmark` mode.
* Next phase: dispatch if work was scheduled → correlate if the blackboard changed → verify if
  findings are unchallenged → assess.

## 2. Security (`security.py`)

| Mode | What it does |
| --- | --- |
| `full` | Secret scanning (AWS, GitHub, Stripe, Google, Slack, private keys, high-entropy assignments) · AST rules for JWT decode without `algorithms` or with verification disabled, MD5/SHA1 password hashing, `eval`/`exec`, pickle/yaml loads, shell injection, SQL built with string formatting, TLS verification disabled, hard-coded secret fallbacks in `os.environ.get` · regex sinks for JS/TS · prompt-injection signatures in docs · Semgrep with a local ruleset when installed · Dependabot alerts as corroborating evidence when a token is set |
| `dependency_usage` | Import-graph and call-site analysis for one package; classifies the component (authentication, payments …) and whether it is reachable from entrypoints |

The detector is recall-oriented by design; its reasoning summary says that context (fixture vs
production) is left to the red team.

## 3. Dependency Health (`dependencies.py`)

Detects ecosystems (PyPI, npm, Go, crates.io, Maven) and parses `requirements*.txt`,
`pyproject.toml`, `Pipfile`, `package.json` (+ lockfile), `go.mod`, `Cargo.toml`, `pom.xml`,
`build.gradle`. For exact versions it queries OSV (merging GHSA/PYSEC/CVE aliases), and the
registry for latest version, release dates and license.

Findings: `dependency.vulnerable` (severity = highest advisory severity), `dependency.outdated`,
`dependency.abandoned`, `dependency.unpinned`, `dependency.conflicting_specs`. A high/critical
vulnerability posts an `impact_analysis` investigation request. Packages missing from the data
source are reported as INSUFFICIENT EVIDENCE, never as clean.

## 4. Code Quality (`code_quality.py`)

AST metrics per function: McCabe complexity, length, nesting, parameters; silent broad exception
handlers; duplicated 6-line windows; file size for non-Python sources. It also reviews
data-access functions through a maintainability lens and records a stance (`acceptable` /
`concern`). The LLM (`code_quality.review`) is used only for a short narrative on the most complex
functions, stored as low-weight `llm_analysis` evidence.

## 5. API Compatibility (`api_compatibility.py`)

| Mode | What it does |
| --- | --- |
| `full` | Public API surface, functions emitting `DeprecationWarning` that production code still calls, public-signature diff between the oldest available commit and HEAD |
| `upgrade_compatibility` | Checks call sites against `app/data/api_migrations.json` — documented breaking changes (PyJWT 2.0 `algorithms` required, `encode` returns `str`, `verify` removed; Pydantic 2 `@validator`; Flask 2.3 `before_first_request`), each with its upstream changelog URL |

## 6. Test Reliability (`test_reliability.py`)

| Mode | What it does |
| --- | --- |
| `full` | Discovers frameworks; flags tests without assertions, tests whose only assertions are truthiness/not-None checks, and flakiness indicators; maps tests to production modules with the import graph; flags untested security-critical components; **runs the suite under coverage** when the trust policy allows, recording argv, exit code, duration and output |
| `dependency_coverage` | Determines whether modules importing a given package are exercised by tests; enriches an existing finding instead of duplicating it |

Failures become `testing.test_failure` findings with the observed message. Nothing is inferred:
an abnormal exit (collection error, timeout) is reported as a limitation.

## 7. License Compliance (`license.py`)

Identifies the license file by text fingerprint, compares it with `pyproject.toml` / `package.json`
/ `Cargo.toml` metadata, scans `SPDX-License-Identifier` headers, and checks dependency licenses
from registry metadata with a permissive / weak / strong / network copyleft matrix.

## 8. Maintenance Activity (`maintenance.py`)

Git history (age of last commit, contributor concentration, modules untouched for 18 months while
the project is active) and GitHub metadata (archived flag, releases, stale pull requests). Below
five commits it reports INSUFFICIENT EVIDENCE instead of computing meaningless metrics. Rate limits
and missing tokens degrade to limitations.

## 9. Performance (`performance.py`)

| Strategy / mode | What it does |
| --- | --- |
| `default` | Initialises the benchmark harness (the controlled fault-injection point), finds static suspects (DB calls in loops → N+1, network calls in loops, `re.compile` in loops), then benchmarks suspects that have a harness |
| `static_only` | Degraded strategy after a tool failure: static suspects only |
| `benchmark` mode | Runs benchmark scripts (Skopeo benchmark protocol: one JSON line with `{n, queries, seconds}` per size) for the requested findings and attaches measured evidence |

Findings carry `measurement: static_suspect | measured | measured_no_issue`. A claim is labelled
measured only when a benchmark ran and its output parsed.

## 10. Correlation (`correlation.py`)

Generates candidate relationships deterministically from typed links (same package, same file,
same component, same code subject, opposite stances), then assesses each one (LLM in live mode,
policy in mock mode, `correlation.assess`). Relationship types: `compound_risk`,
`shared_root_cause`, `contradiction`, `causal`, `dependency`, `duplicate`.

* Compound dependency risk: vulnerable package + code-level usage + test gap (+ breaking upgrade);
  multiplier `1 + 0.25 × (dimensions − 1)`, capped at 2.0.
* Component cluster: ≥2 security weaknesses in one security-critical component plus a test gap.
* Contradiction: same subject, one agent reports an issue, another assesses it acceptable. The red
  team is messaged to adjudicate.

Confidence = geometric mean of member confidences × link strength.

## 11. Verification / Red Team (`verification.py`)

Challenges every non-informational finding (and informational ones that are contested) with its own
tool calls:

| Check | Question | Method |
| --- | --- | --- |
| `evidence_integrity` | Is the evidence real? | re-hash the cited line ranges |
| `staleness` | Is the evidence stale? | commit SHA comparison |
| `location_context` | Could this be a false positive? | fixture / test / docs paths |
| `placeholder` | Documented dummy credential? | known vendor placeholders, markers, surrounding docs |
| `production_reference` | Used by production code? | repository search for references |
| `dependency_used` / `reachability` | Is it used / reachable? | independently rebuilt import graph to entrypoints |
| `severity_justified` | Is the severity backed? | advisory severities in the evidence |
| `mitigation` | Does configuration mitigate it? | rule-specific checks (PyJWT version, deployment env files) |
| `reproduction` | Can it be reproduced? | re-run the failing test; benchmark evidence for performance |
| `recompute` / `independent_mapping` | Can the metric be reproduced? | recompute complexity; rebuild the test mapping |
| `theoretical_vs_actual` | Theoretical or actual? | medium+ performance claims need measurement |
| `contradiction` | Is there contradictory evidence? | contradiction correlations + measured evidence |

Decision policy: failed integrity → rejected; any failed check that supports rejection → rejected;
an open check that needs evidence → `needs_more_evidence` plus an investigation request; otherwise
verified (with a severity downgrade if a downgrade check failed). In live mode the LLM's
`verification.judge` ruling is only accepted when it is consistent with these checks.
Correlations are then verified from their members' rulings.

## 12. Risk Assessment (`risk.py`)

Scores only verified, non-informational findings and verified compound/causal correlations:

```
raw   = severity_weight × confidence × impact × exploitability × correlation_multiplier
score = 100 × (1 − e^(−2.2 · raw))         P0 ≥ 80 · P1 ≥ 60 · P2 ≥ 35 · P3 ≥ 12 · P4
```

Compound risks carry their multiplier once, on their own risk entry. Each risk stores the factor
breakdown and a sentence explaining its priority. Rejected and unverified findings are listed as
excluded with the reason.

## 13. Recommendation (`recommendation.py`)

Writes one recommendation per compound risk and per remaining risk (P0–P3) with problem, affected
component, why it matters, proposed fix, estimated risk, verification status, expected benefit and
difficulty. For P0/P1 it proposes a GitHub issue and, for a vulnerable pinned dependency, a draft
pull request with a unified diff. Every proposal is `proposed` and requires approval.
