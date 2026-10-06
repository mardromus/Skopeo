# Demo scenario

The reference case is `examples/vulnerable-demo-repo` ("Shopfront"), a small order service with
deliberate, harmless problems. It runs offline, uses real advisory data from the bundled OSV/PyPI
snapshot, and finishes in under a minute.

## What is planted in the fixture

| Problem | Where | Expected outcome |
| --- | --- | --- |
| `PyJWT==1.7.1` (11 real advisories, latest 2.15.1) | `requirements.txt` | dependency finding → impact-analysis request → follow-ups |
| JWT decoded without `algorithms`; hard-coded fallback secret | `shopfront/auth/middleware.py` | security findings, verified (PyJWT < 2 has no mitigation) |
| MD5 password hashing | `shopfront/auth/passwords.py` | security finding, verified |
| No tests for the auth package | `tests/` | untested-critical-path finding, 0 % coverage measured |
| A genuinely failing test (cents not zero-padded) | `tests/test_pricing.py` | test failure, reproduced by the red team |
| N+1 query | `shopfront/services/orders.py` | static suspect → contested → benchmarked → verified as measured |
| Code-quality "acceptable" view of the same function | (agent opinion) | contradiction → rejected by measured evidence |
| HTTP call per customer in a loop | `shopfront/services/notifications.py` | stays INSUFFICIENT EVIDENCE: nothing can measure it |
| AWS documentation example key pair | `tests/fixtures/example_credentials.txt` | **false positive**: proposed, then rejected |
| `license = "Apache-2.0"` vs MIT `LICENSE`; GPL-3.0 vendored file | `pyproject.toml`, `shopfront/vendor/fastcsv.py` | license findings |
| `requests>=2.20` unpinned | `requirements.txt` | pinning finding, linked to the notification loop |
| Prompt-injection text addressed to AI reviewers | `README.md` | reported as a finding; never followed |
| Deprecated function still called | `shopfront/legacy.py` | API finding |

## Running it

UI: open the app and click **Run the reference case** (leave *Make the performance agent fail once*
ticked). CLI: `python backend/scripts/run_demo.py`. API: `POST /api/demo/investigations`.

## The script (about three minutes)

1. **Intake.** Point at the landing page: the right-hand log is the previous case's real trace.
   Start the reference case.
2. **The plan.** On *Summary → Plan*: "Repository detected as Python project …", eight specialists
   selected, each with its reason.
3. **Parallel work and a failure.** *Agents* tab: eight bars start together. The performance bar is
   hatched — `FAILED: ToolUnavailableError … [controlled fault injection]` — and a second
   performance run appears with strategy `static_only`. Everything else kept running.
4. **Adaptive follow-up.** *Execution trace*, filter *Planning and replanning*: the dependency agent
   requested impact analysis of PyJWT; the orchestrator replanned with Security
   (`dependency_usage`), API (`upgrade_compatibility`) and Tests (`dependency_coverage`), and noted
   that performance was not needed.
5. **Correlation.** *Correlations*: "Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in
   authentication code with insufficient tests" — four findings from four agents, ×1.75.
6. **The red team.** *Red-team rulings*: the AWS key is **rejected** (documented placeholder, only
   read by a test). The vulnerable dependency is **verified** through an independently rebuilt
   import graph. The failing test is **reproduced** by re-running it.
7. **Disagreement.** Still on rulings: the N+1 suspect first got *insufficient evidence* and a
   benchmark request; the benchmark measured 51 → 2001 queries; round 2 verified it and rejected
   the "acceptable" assessment. *Correlations* shows the contradiction as resolved.
8. **Risk.** *Summary*: the compound risk is P0 at 94.5, with its factor breakdown. Rejected and
   unverified findings are not scored.
9. **Fixes and the human gate.** *Fixes and actions*: the P0 fix (upgrade PyJWT, update the two
   breaking call sites, add auth tests) and two proposals — an issue and a draft PR with a diff.
   Approve one: it is recorded as *Approved · dry run* and nothing is sent.
10. **Report.** Download the Markdown report.

## Variations

* Untick the failure box: the performance agent benchmarks the N+1 suspect in round 1, so the
  red team verifies it immediately — a different path through the same graph
  (`tests/integration/test_fault_isolation.py::test_without_fault_performance_measures_in_first_round`).
* `SKOPEO_FAULT_INJECTION=license_agent@*` makes the license agent fail on every attempt; it is
  reported unavailable and the case still completes with limitations.
* Investigate a real repository: paste a GitHub URL. Without `SKOPEO_SANDBOX_EXECUTION`, tests and
  benchmarks are not executed and the coverage table says so.
