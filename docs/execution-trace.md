# Execution trace

Every significant step of an investigation is persisted as a row in `execution_events`
(`sender`, `receiver`, `event_type`, `severity`, `message`, `payload`, `timestamp`, monotonic `seq`).
The UI's *Execution trace* tab and the exported reports read this table directly. Nothing in a
trace is written for display.

## Event types

| Event | Emitted by | Meaning |
| --- | --- | --- |
| `investigation_started` | orchestrator | case opened, provider and DRY_RUN recorded |
| `repository_prepared` | orchestrator | clone / fixture ready, commit SHA and profile |
| `plan_created` | orchestrator | initial plan with a rationale per agent and per skip |
| `agent_started` / `agent_completed` / `agent_failed` | each agent | run lifecycle, duration, findings, limitations, error |
| `agent_message` | any agent | structured message to another agent or the orchestrator (own plan, discoveries, warnings) |
| `finding_created` / `evidence_added` | specialists, red team | blackboard writes |
| `tool_executed` | agents | a real subprocess ran: argv, exit code, duration, output tail |
| `investigation_requested` | any agent | a request for more investigation, written to `investigation_requests` |
| `request_decided` | orchestrator | request accepted (with assigned tasks) or declined (with reason) |
| `replan` | orchestrator | follow-up tasks added to the plan, with reasons |
| `agent_retry_scheduled` | orchestrator | failed run retried, with the fallback strategy |
| `orchestrator_decision` | orchestrator | review outcome and the next phase |
| `correlation_created` / `correlation_updated` | correlation agent, red team | relationship found / re-assessed / ruled |
| `verification_started` / `challenge` | red team | a round begins; a question put to a specific agent |
| `finding_verified` / `finding_rejected` / `verification_completed` | red team | ruling (the last one for insufficient evidence) |
| `risk_assessed` | risk agent | P0–P4 with score |
| `recommendation_created` / `github_action_proposed` | recommendation agent | remediation and proposals |
| `human_approval_required` / `action_decided` | orchestrator / human | approval gate |
| `investigation_completed` | orchestrator | final status, counts, partial coverage |

## A real trace

Excerpt from the reference investigation (`examples/vulnerable-demo-repo`, mock LLM, controlled
performance-agent failure). 59 of its 233 events are shown; the full trace is in
[sample-report.md](sample-report.md) and in the UI.

| # | Time (UTC) | From → To | Event | Message |
| --- | --- | --- | --- | --- |
| 1 | 10:32:53.251 | orchestrator → all_agents | `investigation_started` | Orchestrator created investigation of examples/vulnerable-demo-repo (main, depth=standard, mode=mock, DRY_RUN=True) |
| 2 | 10:32:56.351 | orchestrator → blackboard | `repository_prepared` | Repository prepared (demo_fixture) at 5eda3b9ec3: 28 files, primary language Python |
| 4 | 10:32:56.374 | orchestrator → all_agents | `plan_created` | Plan created: 8 specialist(s) in parallel — security_agent, dependency_agent, test_reliability_agent, api_compatibility_agent, performance_agent, code_quality_agent, license_agent, maintenance_agent |
| 23 | 10:32:56.667 | performance_agent → orchestrator | `agent_failed` | Performance Agent FAILED: ToolUnavailableError: benchmark harness unavailable [controlled fault injection: SKOPEO_FAULT_INJECTION=performance_agent@1] |
| 34 | 10:32:57.272 | dependency_agent → orchestrator | `investigation_requested` | Requests impact analysis: Assess real-world impact of vulnerable PyJWT 1.7.1 (usage, upgrade compatibility, test coverage) |
| 53 | 10:33:12.992 | test_reliability_agent → blackboard | `tool_executed` | test_reliability_agent executed python -B -m coverage run --data-file=<workspace>\82686e93-967b-4cf1-b7e2-5966701b9513\artifacts\.coverage --source=shopfront -m pytest -q -rfE -p no:cacheprovider -- |
| 60 | 10:33:13.197 | orchestrator → performance_agent | `agent_retry_scheduled` | performance_agent FAILED -> RETRYING (attempt 2, strategy 'static_only'): ToolUnavailableError: benchmark harness unavailable [controlled fault injection: SKOPEO_FAULT_INJECTION=performance_agent@1]; retry 2 with strategy 'static_only' |
| 61 | 10:33:13.244 | orchestrator → dependency_agent | `request_decided` | Accepted request from dependency_agent: assigning security_agent:dependency_usage, api_compatibility_agent:upgrade_compatibility, test_reliability_agent:dependency_coverage |
| 62 | 10:33:13.278 | orchestrator → all_agents | `replan` | Replanned: +security_agent (dependency_usage), +api_compatibility_agent (upgrade_compatibility), +test_reliability_agent (dependency_coverage); performance follow-up not required (pyjwt is not on a performance-sensitive path) |
| 73 | 10:33:13.669 | test_reliability_agent → blackboard | `evidence_added` | Linked untested authentication code to dependency pyjwt |
| 87 | 10:33:14.171 | correlation_agent → blackboard | `correlation_created` | Contradiction: Agents disagree about list_orders_with_items() |
| 89 | 10:33:14.392 | correlation_agent → blackboard | `correlation_created` | Shared Root Cause: Shared root cause: stale pin of pyjwt 1.7.1 |
| 90 | 10:33:14.628 | correlation_agent → blackboard | `correlation_created` | Compound Risk: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests |
| 91 | 10:33:14.905 | correlation_agent → blackboard | `correlation_created` | Compound Risk: Concentrated weaknesses in the authentication component (3 security findings, untested) |
| 96 | 10:33:15.258 | verification_agent → orchestrator | `verification_started` | Red-team round 1: challenging 24 finding(s) and pending correlations |
| 97 | 10:33:15.398 | verification_agent → dependency_agent | `challenge` | Challenge to dependency_agent: Is pyjwt actually imported and reachable, and is the critical severity backed by the advisory data? |
| 98 | 10:33:15.442 | verification_agent → dependency_agent | `finding_verified` | VERIFIED: PyJWT 1.7.1 is affected by 11 known vulnerabilities — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. `jwt` imported by shopfront/auth/middleware.py; i |
| 99 | 10:33:15.624 | verification_agent → security_agent | `challenge` | Challenge to security_agent: Is this a live credential, or a documented dummy value in a fixture? Is it used by production code? |
| 100 | 10:33:15.675 | verification_agent → security_agent | `finding_rejected` | REJECTED: Possible credential exposure: AWS access key ID in tests/fixtures/README.md — The detected string occurs in tests/fixtures/README.md and matches a documented placeholder pattern. AKIA************MPLE: value matches a documented pl |
| 101 | 10:33:15.854 | verification_agent → security_agent | `challenge` | Challenge to security_agent: Is this a live credential, or a documented dummy value in a fixture? Is it used by production code? |
| 102 | 10:33:15.905 | verification_agent → security_agent | `finding_rejected` | REJECTED: Possible credential exposure: AWS access key ID and AWS secret access key in tests/fixtures/example_credentials.txt — The detected string occurs in tests/fixtures/example_credentials.txt and matches a documented placeholder patter |
| 112 | 10:33:17.408 | verification_agent → security_agent | `finding_verified` | VERIFIED: Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py) — Verified: re-hashed 3 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (tra |
| 120 | 10:33:18.384 | verification_agent → dependency_agent | `finding_verified` | VERIFIED: PyJWT 1.7.1 is a major version behind latest 2.15.1, released 7 year(s) ago — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. `jwt` imported by shopfro |
| 124 | 10:33:18.788 | verification_agent → test_reliability_agent | `challenge` | Requested reproduction: re-running tests/test_pricing.py::test_format_price_pads_single_digit_cents |
| 125 | 10:33:27.228 | verification_agent → blackboard | `tool_executed` | verification_agent executed python -B -m pytest -q -p no:cacheprovider --no-header --color=no tests/test_pricing.py::test_format_price_pads_single_digit_cents |
| 126 | 10:33:27.311 | verification_agent → test_reliability_agent | `finding_verified` | VERIFIED: Failing test: tests/test_pricing.py::test_format_price_pads_single_digit_cents — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. reproduction confirmed |
| 130 | 10:33:27.658 | verification_agent → performance_agent | `verification_completed` | NEEDS MORE EVIDENCE: Blocking network call inside a loop in notify_customers() (shopfront/services/notifications.py) — STATIC SUSPECT — Needs more evidence: STATIC SUSPECT only — no benchmark has measured the impact; a medium+ performance c |
| 131 | 10:33:27.667 | verification_agent → orchestrator | `investigation_requested` | Requests benchmark: Run a benchmark for notify_customers() to measure the suspected network in loop |
| 133 | 10:33:27.839 | verification_agent → api_compatibility_agent | `finding_verified` | VERIFIED: Upgrading pyjwt 1.7.1 -> 2.14.0 breaks 2 call site(s) in shopfront/auth/middleware.py — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (trans |
| 135 | 10:33:28.007 | verification_agent → performance_agent | `verification_completed` | NEEDS MORE EVIDENCE: Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — STATIC SUSPECT — Needs more evidence: STATIC SUSPECT only — no benchmark has measured the impact; a medium |
| 136 | 10:33:28.020 | verification_agent → orchestrator | `investigation_requested` | Requests benchmark: Run a benchmark for list_orders_with_items() to measure the suspected n plus one |
| 147 | 10:33:29.315 | verification_agent → code_quality_agent | `challenge` | Challenge to code_quality_agent: Does measured evidence contradict this 'acceptable' assessment? |
| 148 | 10:33:29.358 | verification_agent → code_quality_agent | `verification_completed` | NEEDS MORE EVIDENCE: Data-access function list_orders_with_items() assessed acceptable for maintainability (shopfront/services/orders.py) — Needs more evidence: contested by performance_agent; neither side measured. |
| 149 | 10:33:29.371 | verification_agent → orchestrator | `investigation_requested` | Requests benchmark: Run a benchmark for list_orders_with_items() to measure the suspected n plus one |
| 156 | 10:33:30.316 | orchestrator → verification_agent | `request_decided` | Accepted request from verification_agent: assigning performance_agent:benchmark |
| 157 | 10:33:30.323 | orchestrator → verification_agent | `request_decided` | Accepted request from verification_agent: assigning performance_agent:benchmark |
| 158 | 10:33:30.329 | orchestrator → verification_agent | `request_decided` | Accepted request from verification_agent: assigning performance_agent:benchmark |
| 159 | 10:33:30.341 | orchestrator → all_agents | `replan` | Replanned: +performance_agent (benchmark), +performance_agent (benchmark) |
| 167 | 10:33:32.889 | performance_agent → blackboard | `tool_executed` | performance_agent executed python -B benchmarks/bench_orders.py --json |
| 168 | 10:33:32.961 | performance_agent → blackboard | `evidence_added` | Benchmark benchmarks/bench_orders.py: query count grows linearly with rows (51 queries at n=50 -> 2001 at n=2000); N+1 confirmed |
| 178 | 10:33:34.220 | verification_agent → orchestrator | `verification_started` | Red-team round 2: challenging 2 finding(s) and pending correlations |
| 180 | 10:33:34.402 | verification_agent → performance_agent | `finding_verified` | VERIFIED: Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analyse |
| 181 | 10:33:34.543 | verification_agent → code_quality_agent | `challenge` | Challenge to code_quality_agent: Does measured evidence contradict this 'acceptable' assessment? |
| 182 | 10:33:34.579 | verification_agent → code_quality_agent | `finding_rejected` | REJECTED: Data-access function list_orders_with_items() assessed acceptable for maintainability (shopfront/services/orders.py) — Rejected: measured evidence from performance_agent contradicts this assessment (query count grows linearly with |
| 192 | 10:33:35.255 | risk_agent → recommendation_agent | `risk_assessed` | P0 (score 82.5): PyJWT 1.7.1 is affected by 11 known vulnerabilities |
| 197 | 10:33:35.347 | risk_agent → recommendation_agent | `risk_assessed` | P2 (score 50.2): PyJWT 1.7.1 is a major version behind latest 2.15.1, released 7 year(s) ago |
| 205 | 10:33:35.436 | risk_agent → recommendation_agent | `risk_assessed` | P2 (score 42.0): Upgrading pyjwt 1.7.1 -> 2.14.0 breaks 2 call site(s) in shopfront/auth/middleware.py |
| 206 | 10:33:35.445 | risk_agent → recommendation_agent | `risk_assessed` | P1 (score 72.9): Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py) |
| 207 | 10:33:35.458 | risk_agent → recommendation_agent | `risk_assessed` | P2 (score 36.7): Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED |
| 208 | 10:33:35.631 | risk_agent → recommendation_agent | `risk_assessed` | P0 (score 94.5) compound: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests |
| 209 | 10:33:35.665 | risk_agent → recommendation_agent | `risk_assessed` | P1 (score 66.9) compound: Concentrated weaknesses in the authentication component (3 security findings, untested) |
| 213 | 10:33:35.853 | recommendation_agent → human | `recommendation_created` | P0 recommendation: Fix compound risk: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests |
| 214 | 10:33:35.862 | recommendation_agent → human | `github_action_proposed` | ACTION PROPOSED: GitHub issue '[Skopeo P0] Fix compound risk: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests' |
| 215 | 10:33:35.877 | recommendation_agent → human | `github_action_proposed` | ACTION PROPOSED: draft PR '[Skopeo] Upgrade PyJWT to 2.15.1 (draft)' |
| 216 | 10:33:36.058 | recommendation_agent → human | `recommendation_created` | P1 recommendation: Fix compound risk: Concentrated weaknesses in the authentication component (3 security findings, untested) |
| 217 | 10:33:36.070 | recommendation_agent → human | `github_action_proposed` | ACTION PROPOSED: GitHub issue '[Skopeo P1] Fix compound risk: Concentrated weaknesses in the authentication component (3 security findings, untested)' |
| 218 | 10:33:36.855 | recommendation_agent → human | `recommendation_created` | P2 recommendation: PyJWT 1.7.1 is a major version behind latest 2.15.1, released 7 year(s) ago |
| 219 | 10:33:37.233 | recommendation_agent → human | `recommendation_created` | P2 recommendation: Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED |
| 233 | 10:33:39.167 | orchestrator → human | `investigation_completed` | Investigation COMPLETED_WITH_LIMITATIONS: 20 verified, 3 rejected, 1 insufficient evidence; overall risk 97.8 (critical); partial coverage: security_agent, dependency_agent, api_compatibility_agent, maintenance_agent, performance_agent |

## Reading it

* **Parallel start (seq 4–23).** All eight specialists start within the same second.
* **Fault isolation (23, 60).** The performance agent fails on a controlled
  `ToolUnavailableError`; the others keep running. The orchestrator retries it with the
  `static_only` strategy.
* **Agent-initiated follow-up (34 → 61 → 62).** The dependency agent asks for impact analysis of
  PyJWT; the orchestrator accepts and fans out to three specialists, and says why performance is
  not included.
* **Cross-agent correlation (87–91).** A contradiction, a shared root cause and two compound risks,
  each built from findings by different agents.
* **The red team at work (96–149).** It verifies the vulnerable dependency through its own import
  graph, rejects both fake AWS credentials as documented placeholders, reproduces the failing test
  by re-running it, and refuses to verify unmeasured performance claims.
* **Verification-driven replanning (131–168).** Its benchmark requests make the orchestrator run
  the performance agent in benchmark mode; the benchmark measures 51 → 2001 queries for 50 → 2000
  rows.
* **Disagreement resolved (178–182).** Round 2 verifies the N+1 finding as MEASURED and rejects the
  code-quality agent's "acceptable" assessment.
* **Only verified evidence is scored (192–209).** The compound authentication upgrade risk is P0.
* **Honest limits (233).** The case ends `COMPLETED_WITH_LIMITATIONS` and names the agents with
  partial coverage. The notification-loop claim stays INSUFFICIENT EVIDENCE because no benchmark
  exists for it.

## Export

* `GET /api/investigations/{id}/report?format=json` returns the full report schema, including all events.
* `GET /api/investigations/{id}/report?format=markdown` returns a presentation-ready document.
* `python backend/scripts/run_demo.py --markdown out.md --json out.json` does both from the CLI.
