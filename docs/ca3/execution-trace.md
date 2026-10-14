# Skopeo Multi-Agent Execution Trace

> **Captured run, not edited.** Exported with `backend/app/utils/trace_exporter.py` from the Evidence Store of a real run on 15 Oct 2026.
> Input: `POST /api/demo/investigations {"fault_injection": true}` (bundled reference repository `examples/vulnerable-demo-repo`, controlled failure of the performance agent switched on).
> LLM mode for this capture: `mock` (agent decisions made by the deterministic policies behind the same `LLMProvider.decide()` calls). With `SKOPEO_MODE=live` + Groq the same graph runs and each decision records `decided_by: llm:<model>`.
> Totals: 21 agent runs, 8 agents in parallel, 1 failure, 1 retry, 5 follow-up tasks, 2 replans, 24 findings (20 verified, 3 rejected by the red team, 1 insufficient evidence), 233 events.

**Investigation ID**: `a2d2d2d9-32ba-420e-af12-d187dee772af`
**Target Repository**: `bundled://examples/vulnerable-demo-repo` (`5eda3b9ec3c34ef25e95cc8180a669e983de998a`)
**Status**: `completed_with_limitations`
**Overall Risk Score**: `97.8` / 100

## 1. Active Agents Summary
| Agent Name | Mode | Status | Findings | Duration (ms) |
| --- | --- | --- | --- | --- |
| orchestrator | full | completed | 0 | 4117 |
| security_agent | full | completed | 7 | 272 |
| dependency_agent | full | completed | 4 | 259 |
| test_reliability_agent | full | completed | 4 | 1601 |
| api_compatibility_agent | full | completed | 2 | 205 |
| performance_agent | full | failed | 2 | 121 |
| code_quality_agent | full | completed | 3 | 160 |
| license_agent | full | completed | 2 | 119 |
| maintenance_agent | full | completed | 0 | 85 |
| performance_agent | full | completed | 2 | 108 |
| security_agent | dependency_usage | completed | 7 | 83 |
| api_compatibility_agent | upgrade_compatibility | completed | 2 | 74 |
| test_reliability_agent | dependency_coverage | completed | 4 | 59 |
| correlation_agent | full | completed | 0 | 92 |
| verification_agent | full | completed | 0 | 1175 |
| performance_agent | benchmark | completed | 2 | 14 |
| performance_agent | benchmark | completed | 2 | 505 |
| correlation_agent | full | completed | 0 | 41 |
| verification_agent | full | completed | 0 | 45 |
| risk_agent | full | completed | 0 | 83 |
| recommendation_agent | full | completed | 0 | 54 |

## 2. Real-Time Inter-Agent Execution Chronology

- **[001] `orchestrator` → `all_agents`** (`investigation_started`): Orchestrator created investigation of examples/vulnerable-demo-repo (main, depth=standard, mode=mock, DRY_RUN=True)
- **[002] `orchestrator` → `blackboard`** (`repository_prepared`): Repository prepared (demo_fixture) at 5eda3b9ec3: 28 files, primary language Python
- **[003] `orchestrator` → `blackboard`** (`agent_message`): Repository detected as Python project (19 source files, 3 test files, ecosystems: PyPI, 1 commit(s) of history).
- **[004] `orchestrator` → `all_agents`** (`plan_created`): Plan created: 8 specialist(s) in parallel — security_agent, dependency_agent, test_reliability_agent, api_compatibility_agent, performance_agent, code_quality_agent, license_agent, maintenance_agent
- **[005] `security_agent` → `orchestrator`** (`agent_started`): Security Agent started: Find secrets, insecure patterns and prompt-injection content
- **[006] `security_agent` → `orchestrator`** (`agent_message`): Security Agent plan (full/default): scan for committed secrets, analyse insecure code patterns (AST), scan for prompt-injection content, run Semgrep ruleset if available
- **[007] `dependency_agent` → `orchestrator`** (`agent_started`): Dependency Health Agent started: Assess dependency health for PyPI
- **[008] `dependency_agent` → `orchestrator`** (`agent_message`): Dependency Health Agent plan (full/default): detect ecosystems & parse manifests, query vulnerability database, check freshness & maintenance via registry, check version pinning & conflicts
- **[009] `dependency_agent` → `orchestrator`** (`agent_message`): Detected ecosystem(s) PyPI; 3 dependencies in requirements.txt
- **[010] `test_reliability_agent` → `orchestrator`** (`agent_started`): Test Reliability Agent started: Assess test coverage and reliability (execute suite)
- **[011] `test_reliability_agent` → `orchestrator`** (`agent_message`): Test Reliability Agent plan (full/default): discover test framework & suites, analyse assertion quality & flakiness indicators, map tests to production modules, execute test suite with coverage
- **[012] `security_agent` → `blackboard`** (`finding_created`): HIGH security: Possible credential exposure: AWS access key ID in tests/fixtures/README.md
- **[013] `dependency_agent` → `blackboard`** (`finding_created`): CRITICAL dependency: PyJWT 1.7.1 is affected by 11 known vulnerabilities
- **[014] `test_reliability_agent` → `orchestrator`** (`agent_message`): Discovered 3 Python test module(s); frameworks: pytest
- **[015] `api_compatibility_agent` → `orchestrator`** (`agent_started`): API Compatibility Agent started: Review public API surface, deprecations and breaking changes
- **[016] `dependency_agent` → `orchestrator`** (`investigation_requested`): Requests impact analysis: Assess real-world impact of vulnerable PyJWT 1.7.1 (usage, upgrade compatibility, test coverage)
- **[017] `api_compatibility_agent` → `orchestrator`** (`agent_message`): API Compatibility Agent plan (full/default): extract public API surface, find deprecated APIs still in use, compare public API across git history
- **[018] `security_agent` → `blackboard`** (`finding_created`): HIGH security: Possible credential exposure: AWS access key ID and AWS secret access key in tests/fixtures/example_credentials.txt
- **[019] `test_reliability_agent` → `blackboard`** (`finding_created`): LOW testing: 1 test(s) in tests/test_orders.py only make weak assertions
- **[020] `performance_agent` → `orchestrator`** (`agent_started`): Performance Agent started: Find performance bottlenecks (static + benchmarks)
- **[021] `dependency_agent` → `blackboard`** (`finding_created`): MEDIUM dependency: PyJWT 1.7.1 is a major version behind latest 2.15.1, released 7 year(s) ago
- **[022] `api_compatibility_agent` → `blackboard`** (`finding_created`): LOW api_compatibility: Deprecated legacy_price_lookup() is still called from 1 production site(s)
- **[023] `performance_agent` → `orchestrator`** (`agent_message`): Performance Agent plan (full/default): initialise benchmark/profiling harness, detect static performance suspects (AST)
- **[024] `security_agent` → `blackboard`** (`finding_created`): MEDIUM security: Hardcoded fallback value for secret SHOPFRONT_SECRET in shopfront/auth/middleware.py
- **[025] `test_reliability_agent` → `blackboard`** (`finding_created`): HIGH testing: Security-critical authentication code has no tests (shopfront/auth/middleware.py, shopfront/auth/passwords.py)
- **[026] `code_quality_agent` → `orchestrator`** (`agent_started`): Code Quality Agent started: Measure maintainability and code smells
- **[027] `dependency_agent` → `blackboard`** (`finding_created`): MEDIUM dependency: python-dateutil appears unmaintained (latest release 2+ years ago)
- **[028] `code_quality_agent` → `orchestrator`** (`agent_message`): Code Quality Agent plan (full/default): compute function metrics (AST), detect silent exception handling, detect duplicated code blocks, review data-access functions
- **[029] `security_agent` → `blackboard`** (`finding_created`): HIGH security: JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py
- **[030] `license_agent` → `orchestrator`** (`agent_started`): License Compliance Agent started: Check license and dependency license compliance
- **[031] `dependency_agent` → `blackboard`** (`finding_created`): LOW dependency: 1 runtime dependency is not pinned to exact versions (requests>=2.20)
- **[032] `code_quality_agent` → `blackboard`** (`finding_created`): MEDIUM code_quality: build_sales_report() has cyclomatic complexity 17 (shopfront/services/reports.py)
- **[033] `security_agent` → `blackboard`** (`finding_created`): HIGH security: Passwords hashed with MD5 (fast, unsalted) in shopfront/auth/passwords.py
- **[034] `license_agent` → `orchestrator`** (`agent_message`): License Compliance Agent plan (full/default): identify repository license, check package metadata consistency, scan SPDX headers in source files, check dependency licenses
- **[035] `code_quality_agent` → `orchestrator`** (`agent_message`): Code Quality Agent extended its plan after 'compute function metrics (AST)': LLM maintainability review of most complex functions
- **[036] `maintenance_agent` → `orchestrator`** (`agent_started`): Maintenance Activity Agent started: Assess maintenance activity
- **[037] `maintenance_agent` → `orchestrator`** (`agent_message`): Maintenance Activity Agent plan (full/default): analyse git history
- **[038] `security_agent` → `blackboard`** (`finding_created`): LOW security: AI-directed instructions (possible prompt injection) in README.md
- **[039] `license_agent` → `blackboard`** (`finding_created`): MEDIUM license: License metadata mismatch: pyproject.toml declares Apache-2.0 but LICENSE is MIT
- **[040] `performance_agent` → `orchestrator`** (`agent_failed`): Performance Agent FAILED: ToolUnavailableError: benchmark harness unavailable [controlled fault injection: SKOPEO_FAULT_INJECTION=performance_agent@1]
- **[041] `code_quality_agent` → `blackboard`** (`finding_created`): LOW code_quality: Broad exception silently swallowed in shopfront/services/reports.py (1x)
- **[042] `security_agent` → `orchestrator`** (`agent_message`): Prompt-injection content detected in README.md; handled as untrusted data (no instructions followed)
- **[043] `maintenance_agent` → `orchestrator`** (`agent_message`): Maintenance analysis limited: 1 commit(s) of history available
- **[044] `api_compatibility_agent` → `orchestrator`** (`agent_completed`): API Compatibility Agent completed in 205 ms: 1 finding(s) published, 0 enriched
- **[045] `license_agent` → `blackboard`** (`finding_created`): HIGH license: GPL-3.0 licensed source in a MIT project (shopfront/vendor/fastcsv.py)
- **[046] `code_quality_agent` → `blackboard`** (`finding_created`): INFO code_quality: Data-access function list_orders_with_items() assessed acceptable for maintainability (shopfront/services/orders.py)
- **[047] `dependency_agent` → `orchestrator`** (`agent_completed`): Dependency Health Agent completed in 259 ms: 4 finding(s) published, 0 enriched
- **[048] `security_agent` → `orchestrator`** (`agent_completed`): Security Agent completed in 272 ms: 6 finding(s) published, 0 enriched
- **[049] `maintenance_agent` → `orchestrator`** (`agent_completed`): Maintenance Activity Agent completed in 85 ms: 0 finding(s) published, 0 enriched
- **[050] `license_agent` → `orchestrator`** (`agent_completed`): License Compliance Agent completed in 119 ms: 2 finding(s) published, 0 enriched
- **[051] `code_quality_agent` → `blackboard`** (`evidence_added`): Maintainability review attached to build_sales_report (policy)
- **[052] `code_quality_agent` → `orchestrator`** (`agent_completed`): Code Quality Agent completed in 160 ms: 3 finding(s) published, 1 enriched
- **[053] `test_reliability_agent` → `blackboard`** (`tool_executed`): test_reliability_agent executed python -B -m coverage run --data-file=/tmp/claude-0/-home-claude-skopeo/ae5ac9f1-2a34-589b-a566-78c054655430/scratchpad/cap/ws/a2d2d2d9-32ba-420e-af12-d187dee772af/artifacts/.coverage --source=shopfront -m pytest -q -rfE -p no:cacheprovider --no-header --color=no tests
- **[054] `test_reliability_agent` → `orchestrator`** (`agent_message`): Executed test suite: 1 failed, 6 passed in 0.04s (exit code 1, 1152 ms)
- **[055] `test_reliability_agent` → `blackboard`** (`finding_created`): MEDIUM testing: Failing test: tests/test_pricing.py::test_format_price_pads_single_digit_cents
- **[056] `test_reliability_agent` → `blackboard`** (`evidence_added`): Coverage run confirms shopfront/auth/middleware.py at 0% coverage
- **[057] `test_reliability_agent` → `blackboard`** (`evidence_added`): Coverage run confirms shopfront/auth/passwords.py at 0% coverage
- **[058] `test_reliability_agent` → `blackboard`** (`finding_created`): MEDIUM testing: Overall line coverage is 20%
- **[059] `test_reliability_agent` → `orchestrator`** (`agent_completed`): Test Reliability Agent completed in 1601 ms: 4 finding(s) published, 2 enriched
- **[060] `orchestrator` → `performance_agent`** (`agent_retry_scheduled`): performance_agent FAILED -> RETRYING (attempt 2, strategy 'static_only'): ToolUnavailableError: benchmark harness unavailable [controlled fault injection: SKOPEO_FAULT_INJECTION=performance_agent@1]; retry 2 with strategy 'static_only'
- **[061] `orchestrator` → `dependency_agent`** (`request_decided`): Accepted request from dependency_agent: assigning security_agent:dependency_usage, api_compatibility_agent:upgrade_compatibility, test_reliability_agent:dependency_coverage
- **[062] `orchestrator` → `all_agents`** (`replan`): Replanned: +security_agent (dependency_usage), +api_compatibility_agent (upgrade_compatibility), +test_reliability_agent (dependency_coverage); performance follow-up not required (pyjwt is not on a performance-sensitive path)
- **[063] `orchestrator` → `all_agents`** (`orchestrator_decision`): Review round 1: performance_agent failed (ToolUnavailableError); retrying with 'static_only'; 3 follow-up(s) scheduled Next: dispatch.
- **[064] `performance_agent` → `orchestrator`** (`agent_started`): Performance Agent started: Retry: performance_agent (static_only) (attempt 2, strategy static_only)
- **[065] `performance_agent` → `orchestrator`** (`agent_message`): Performance Agent plan (full/static_only): detect static performance suspects (AST)
- **[066] `security_agent` → `orchestrator`** (`agent_started`): Security Agent started: Inspect how pyjwt is used and whether it reaches security-critical code [dependency_usage]
- **[067] `security_agent` → `orchestrator`** (`agent_message`): Security Agent plan (dependency_usage/default): trace dependency usage & reachability
- **[068] `api_compatibility_agent` → `orchestrator`** (`agent_started`): API Compatibility Agent started: Check whether upgrading pyjwt 1.7.1 -> 2.14.0 breaks APIs [upgrade_compatibility]
- **[069] `performance_agent` → `blackboard`** (`finding_created`): MEDIUM performance: Blocking network call inside a loop in notify_customers() (shopfront/services/notifications.py) — STATIC SUSPECT
- **[070] `api_compatibility_agent` → `orchestrator`** (`agent_message`): API Compatibility Agent plan (upgrade_compatibility/default): check upgrade compatibility against migration knowledge base
- **[071] `security_agent` → `blackboard`** (`finding_created`): HIGH security: Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py)
- **[072] `security_agent` → `orchestrator`** (`agent_message`): Confirmed pyjwt is used by authentication code (shopfront/auth/middleware.py); reachable from entrypoints: yes
- **[073] `test_reliability_agent` → `orchestrator`** (`agent_started`): Test Reliability Agent started: Identify tests covering code that uses pyjwt [dependency_coverage]
- **[074] `performance_agent` → `blackboard`** (`finding_created`): MEDIUM performance: Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — STATIC SUSPECT
- **[075] `test_reliability_agent` → `orchestrator`** (`agent_message`): Test Reliability Agent plan (dependency_coverage/default): map tests to code using the dependency
- **[076] `api_compatibility_agent` → `blackboard`** (`finding_created`): MEDIUM api_compatibility: Upgrading pyjwt 1.7.1 -> 2.14.0 breaks 2 call site(s) in shopfront/auth/middleware.py
- **[077] `security_agent` → `orchestrator`** (`agent_completed`): Security Agent completed in 83 ms: 1 finding(s) published, 0 enriched
- **[078] `api_compatibility_agent` → `orchestrator`** (`agent_message`): Upgrade of pyjwt is not drop-in: 2 call site(s) need changes
- **[079] `performance_agent` → `orchestrator`** (`agent_completed`): Performance Agent completed in 108 ms: 2 finding(s) published, 0 enriched
- **[080] `test_reliability_agent` → `blackboard`** (`evidence_added`): Linked untested authentication code to dependency pyjwt
- **[081] `api_compatibility_agent` → `orchestrator`** (`agent_completed`): API Compatibility Agent completed in 74 ms: 1 finding(s) published, 0 enriched
- **[082] `test_reliability_agent` → `orchestrator`** (`agent_message`): Code using pyjwt (shopfront/auth/middleware.py) is not exercised by any test — an upgrade of pyjwt would ship without regression tests (evidence added to existing finding)
- **[083] `test_reliability_agent` → `orchestrator`** (`agent_completed`): Test Reliability Agent completed in 59 ms: 0 finding(s) published, 1 enriched
- **[084] `orchestrator` → `all_agents`** (`orchestrator_decision`): Review round 2: 4 task(s) completed, 4 new finding(s) Next: correlate.
- **[085] `correlation_agent` → `orchestrator`** (`agent_started`): Correlation Agent started: Correlate findings across agents
- **[086] `correlation_agent` → `orchestrator`** (`agent_message`): Correlation pass over 24 findings from 7 agents: 5 candidate relationship(s)
- **[087] `correlation_agent` → `blackboard`** (`correlation_created`): Contradiction: Agents disagree about list_orders_with_items()
- **[088] `correlation_agent` → `verification_agent`** (`agent_message`): Contradiction requires adjudication: Agents disagree about list_orders_with_items(). Disagreement on py:shopfront/services/orders.py::list_orders_with_items: performance_agent flags a potential issue ('Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — STATIC SUSPECT'), code_quality_agent considers it acceptable (Short, low-complexity function using parameterised queries; scale judged from repository seed data contains 25 orders.). Potential issue but insufficient evidence — needs measurement to adjudicate.
- **[089] `correlation_agent` → `blackboard`** (`correlation_created`): Shared Root Cause: Shared root cause: stale pin of pyjwt 1.7.1
- **[090] `correlation_agent` → `blackboard`** (`correlation_created`): Compound Risk: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests
- **[091] `correlation_agent` → `blackboard`** (`correlation_created`): Compound Risk: Concentrated weaknesses in the authentication component (3 security findings, untested)
- **[092] `correlation_agent` → `blackboard`** (`correlation_created`): Dependency: Unpinned requests is used on a hot path
- **[093] `correlation_agent` → `orchestrator`** (`agent_completed`): Correlation Agent completed in 92 ms: 5 new and 0 updated correlation(s) from 5 candidates
- **[094] `orchestrator` → `all_agents`** (`orchestrator_decision`): Review round 2: phase complete Next: verify.
- **[095] `verification_agent` → `orchestrator`** (`agent_started`): Verification / Red-Team Agent started: Red-team verification round 1
- **[096] `verification_agent` → `orchestrator`** (`verification_started`): Red-team round 1: challenging 24 finding(s) and pending correlations
- **[097] `verification_agent` → `dependency_agent`** (`challenge`): Challenge to dependency_agent: Is pyjwt actually imported and reachable, and is the critical severity backed by the advisory data?
- **[098] `verification_agent` → `dependency_agent`** (`finding_verified`): VERIFIED: PyJWT 1.7.1 is affected by 11 known vulnerabilities — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. `jwt` imported by shopfront/auth/middleware.py; imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. claimed critical matches the highest advi
- **[099] `verification_agent` → `security_agent`** (`challenge`): Challenge to security_agent: Is this a live credential, or a documented dummy value in a fixture? Is it used by production code?
- **[100] `verification_agent` → `security_agent`** (`finding_rejected`): REJECTED: Possible credential exposure: AWS access key ID in tests/fixtures/README.md — The detected string occurs in tests/fixtures/README.md and matches a documented placeholder pattern. AKIA************MPLE: value matches a documented placeholder (AWS documentation example access key ID). all affected files are tests/fixtures/docs: tests/fixtures/README.md. No production credential 
- **[101] `verification_agent` → `security_agent`** (`challenge`): Challenge to security_agent: Is this a live credential, or a documented dummy value in a fixture? Is it used by production code?
- **[102] `verification_agent` → `security_agent`** (`finding_rejected`): REJECTED: Possible credential exposure: AWS access key ID and AWS secret access key in tests/fixtures/example_credentials.txt — The detected string occurs in tests/fixtures/example_credentials.txt and matches a documented placeholder pattern. AKIA************MPLE: value matches a documented placeholder (AWS documentation example access key ID); wJal********************************EKEY: value matches a documented placeholder 
- **[103] `verification_agent` → `test_reliability_agent`** (`challenge`): Challenge to test_reliability_agent: Do tests really not exercise this code? Re-derive the mapping independently.
- **[104] `verification_agent` → `test_reliability_agent`** (`finding_verified`): VERIFIED: Security-critical authentication code has no tests (shopfront/auth/middleware.py, shopfront/auth/passwords.py) — Verified: re-hashed 5 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. independently rebuilt import graph: no test imports shopfront/auth/middleware.py, shopfront/auth/passwords.py. shopfront/auth/middleware.py: 0% line coverage (0/23 statement
- **[105] `verification_agent` → `security_agent`** (`challenge`): Challenge to security_agent: Is the evidence real, current and reachable, and is the severity justified?
- **[106] `verification_agent` → `security_agent`** (`finding_verified`): VERIFIED: JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.
- **[107] `verification_agent` → `security_agent`** (`challenge`): Challenge to security_agent: Is the evidence real, current and reachable, and is the severity justified?
- **[108] `verification_agent` → `security_agent`** (`finding_verified`): VERIFIED: Passwords hashed with MD5 (fast, unsalted) in shopfront/auth/passwords.py — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.
- **[109] `verification_agent` → `license_agent`** (`challenge`): Challenge to license_agent: Is the evidence real, current and reachable, and is the severity justified?
- **[110] `verification_agent` → `license_agent`** (`finding_verified`): VERIFIED: GPL-3.0 licensed source in a MIT project (shopfront/vendor/fastcsv.py) — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. copyleft-licensed file is part of shipped code: imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.
- **[111] `verification_agent` → `security_agent`** (`challenge`): Challenge to security_agent: Is the evidence real, current and reachable, and is the severity justified?
- **[112] `verification_agent` → `security_agent`** (`finding_verified`): VERIFIED: Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py) — Verified: re-hashed 3 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.
- **[113] `verification_agent` → `dependency_agent`** (`challenge`): Challenge to dependency_agent: Is the evidence real, current and reachable, and is the severity justified?
- **[114] `verification_agent` → `dependency_agent`** (`finding_verified`): VERIFIED: PyJWT 1.7.1 is a major version behind latest 2.15.1, released 7 year(s) ago — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. `jwt` imported by shopfront/auth/middleware.py; imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py.
- **[115] `verification_agent` → `security_agent`** (`challenge`): Challenge to security_agent: Is the evidence real, current and reachable, and is the severity justified?
- **[116] `verification_agent` → `security_agent`** (`finding_verified`): VERIFIED: Hardcoded fallback value for secret SHOPFRONT_SECRET in shopfront/auth/middleware.py — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.
- **[117] `verification_agent` → `dependency_agent`** (`challenge`): Challenge to dependency_agent: Is the evidence real, current and reachable, and is the severity justified?
- **[118] `verification_agent` → `dependency_agent`** (`finding_verified`): VERIFIED: python-dateutil appears unmaintained (latest release 2+ years ago) — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. Severity downgraded medium -> low: no production module imports `dateutil` — theoretical risk only
- **[119] `verification_agent` → `code_quality_agent`** (`challenge`): Challenge to code_quality_agent: Is the evidence real, current and reachable, and is the severity justified?
- **[120] `verification_agent` → `code_quality_agent`** (`finding_verified`): VERIFIED: build_sales_report() has cyclomatic complexity 17 (shopfront/services/reports.py) — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. recomputed independently: complexity 17, 43 lines, nesting 5.
- **[121] `verification_agent` → `license_agent`** (`challenge`): Challenge to license_agent: Is the evidence real, current and reachable, and is the severity justified?
- **[122] `verification_agent` → `license_agent`** (`finding_verified`): VERIFIED: License metadata mismatch: pyproject.toml declares Apache-2.0 but LICENSE is MIT — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. 'Apache-2.0' and 'MIT' are distinct licenses with different obligations.
- **[123] `verification_agent` → `test_reliability_agent`** (`challenge`): Challenge to test_reliability_agent: Does the failure reproduce on an independent re-run?
- **[124] `verification_agent` → `test_reliability_agent`** (`challenge`): Requested reproduction: re-running tests/test_pricing.py::test_format_price_pads_single_digit_cents
- **[125] `verification_agent` → `blackboard`** (`tool_executed`): verification_agent executed python -B -m pytest -q -p no:cacheprovider --no-header --color=no tests/test_pricing.py::test_format_price_pads_single_digit_cents
- **[126] `verification_agent` → `test_reliability_agent`** (`finding_verified`): VERIFIED: Failing test: tests/test_pricing.py::test_format_price_pads_single_digit_cents — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. reproduction confirmed: `python -B -m pytest -q -p no:cacheprovider --no-header --color=no tests/test_pricing.py::test_format_price_pads_single_digit_cents` failed again (ex
- **[127] `verification_agent` → `test_reliability_agent`** (`challenge`): Challenge to test_reliability_agent: Do tests really not exercise this code? Re-derive the mapping independently.
- **[128] `verification_agent` → `test_reliability_agent`** (`finding_verified`): VERIFIED: Overall line coverage is 20% — Verified: evidence captured at the analysed commit 5eda3b9ec3. test-quality claim re-derived from the test AST.
- **[129] `verification_agent` → `performance_agent`** (`challenge`): Challenge to performance_agent: Has this been measured, or is it a theoretical static suspect? Is the code on a reachable path?
- **[130] `verification_agent` → `performance_agent`** (`verification_completed`): NEEDS MORE EVIDENCE: Blocking network call inside a loop in notify_customers() (shopfront/services/notifications.py) — STATIC SUSPECT — Needs more evidence: STATIC SUSPECT only — no benchmark has measured the impact; a medium+ performance claim needs measurement.
- **[131] `verification_agent` → `orchestrator`** (`investigation_requested`): Requests benchmark: Run a benchmark for notify_customers() to measure the suspected network in loop
- **[132] `verification_agent` → `performance_agent`** (`challenge`): Challenge to performance_agent: Has this been measured, or is it a theoretical static suspect? Is the code on a reachable path?
- **[133] `verification_agent` → `performance_agent`** (`verification_completed`): NEEDS MORE EVIDENCE: Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — STATIC SUSPECT — Needs more evidence: STATIC SUSPECT only — no benchmark has measured the impact; a medium+ performance claim needs measurement. code_quality_agent disagrees; requires measurement to adjudicate.
- **[134] `verification_agent` → `orchestrator`** (`investigation_requested`): Requests benchmark: Run a benchmark for list_orders_with_items() to measure the suspected n plus one
- **[135] `verification_agent` → `api_compatibility_agent`** (`challenge`): Challenge to api_compatibility_agent: Is the evidence real, current and reachable, and is the severity justified?
- **[136] `verification_agent` → `api_compatibility_agent`** (`finding_verified`): VERIFIED: Upgrading pyjwt 1.7.1 -> 2.14.0 breaks 2 call site(s) in shopfront/auth/middleware.py — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.
- **[137] `verification_agent` → `test_reliability_agent`** (`challenge`): Challenge to test_reliability_agent: Do tests really not exercise this code? Re-derive the mapping independently.
- **[138] `verification_agent` → `test_reliability_agent`** (`finding_verified`): VERIFIED: 1 test(s) in tests/test_orders.py only make weak assertions — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. test-quality claim re-derived from the test AST.
- **[139] `verification_agent` → `api_compatibility_agent`** (`challenge`): Challenge to api_compatibility_agent: Is the evidence real, current and reachable, and is the severity justified?
- **[140] `verification_agent` → `api_compatibility_agent`** (`finding_verified`): VERIFIED: Deprecated legacy_price_lookup() is still called from 1 production site(s) — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. shopfront/api/routes.py is itself an entrypoint. affected files are production code.
- **[141] `verification_agent` → `dependency_agent`** (`challenge`): Challenge to dependency_agent: Is the evidence real, current and reachable, and is the severity justified?
- **[142] `verification_agent` → `dependency_agent`** (`finding_verified`): VERIFIED: 1 runtime dependency is not pinned to exact versions (requests>=2.20) — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. derived from deterministic git / GitHub data.
- **[143] `verification_agent` → `security_agent`** (`challenge`): Challenge to security_agent: Is the evidence real, current and reachable, and is the severity justified?
- **[144] `verification_agent` → `security_agent`** (`finding_verified`): VERIFIED: AI-directed instructions (possible prompt injection) in README.md — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. affected files are production code.
- **[145] `verification_agent` → `code_quality_agent`** (`challenge`): Challenge to code_quality_agent: Is the evidence real, current and reachable, and is the severity justified?
- **[146] `verification_agent` → `code_quality_agent`** (`finding_verified`): VERIFIED: Broad exception silently swallowed in shopfront/services/reports.py (1x) — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3.
- **[147] `verification_agent` → `code_quality_agent`** (`challenge`): Challenge to code_quality_agent: Does measured evidence contradict this 'acceptable' assessment?
- **[148] `verification_agent` → `code_quality_agent`** (`verification_completed`): NEEDS MORE EVIDENCE: Data-access function list_orders_with_items() assessed acceptable for maintainability (shopfront/services/orders.py) — Needs more evidence: contested by performance_agent; neither side measured.
- **[149] `verification_agent` → `orchestrator`** (`investigation_requested`): Requests benchmark: Run a benchmark for list_orders_with_items() to measure the suspected n plus one
- **[150] `verification_agent` → `orchestrator`** (`correlation_updated`): Correlation needs more evidence: Agents disagree about list_orders_with_items() — Contradiction unresolved: performance_agent=needs_more_evidence, code_quality_agent=needs_more_evidence
- **[151] `verification_agent` → `orchestrator`** (`correlation_updated`): Correlation verified: Shared root cause: stale pin of pyjwt 1.7.1 — 2 of 2 member findings verified
- **[152] `verification_agent` → `orchestrator`** (`correlation_updated`): Correlation verified: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests — 4 of 4 member findings verified
- **[153] `verification_agent` → `orchestrator`** (`correlation_updated`): Correlation verified: Concentrated weaknesses in the authentication component (3 security findings, untested) — 4 of 4 member findings verified
- **[154] `verification_agent` → `orchestrator`** (`correlation_updated`): Correlation needs more evidence: Unpinned requests is used on a hot path — awaiting verification of 1 member(s)
- **[155] `verification_agent` → `orchestrator`** (`agent_completed`): Verification / Red-Team Agent completed in 1175 ms: Round 1: 3 needs_more_evidence, 2 rejected, 19 verified
- **[156] `orchestrator` → `verification_agent`** (`request_decided`): Accepted request from verification_agent: assigning performance_agent:benchmark
- **[157] `orchestrator` → `verification_agent`** (`request_decided`): Accepted request from verification_agent: assigning performance_agent:benchmark
- **[158] `orchestrator` → `verification_agent`** (`request_decided`): Accepted request from verification_agent: assigning performance_agent:benchmark
- **[159] `orchestrator` → `all_agents`** (`replan`): Replanned: +performance_agent (benchmark), +performance_agent (benchmark)
- **[160] `orchestrator` → `all_agents`** (`orchestrator_decision`): Review round 2: phase complete; 3 follow-up(s) scheduled Next: dispatch.
- **[161] `performance_agent` → `orchestrator`** (`agent_started`): Performance Agent started: Run a benchmark for notify_customers() to measure the suspected network in loop [benchmark]
- **[162] `performance_agent` → `orchestrator`** (`agent_message`): Performance Agent plan (benchmark/default): run benchmarks for requested suspects
- **[163] `performance_agent` → `orchestrator`** (`agent_started`): Performance Agent started: Run a benchmark for list_orders_with_items() to measure the suspected n plus one [benchmark]
- **[164] `performance_agent` → `verification_agent`** (`agent_message`): INSUFFICIENT EVIDENCE: no benchmark harness exercises notify_customers() in shopfront/services/notifications.py; finding stays a static suspect
- **[165] `performance_agent` → `orchestrator`** (`agent_message`): Performance Agent plan (benchmark/default): run benchmarks for requested suspects
- **[166] `performance_agent` → `orchestrator`** (`agent_completed`): Performance Agent completed in 14 ms: 0 finding(s) published, 0 enriched
- **[167] `performance_agent` → `blackboard`** (`tool_executed`): performance_agent executed python -B benchmarks/bench_orders.py --json
- **[168] `performance_agent` → `blackboard`** (`evidence_added`): Benchmark benchmarks/bench_orders.py: query count grows linearly with rows (51 queries at n=50 -> 2001 at n=2000); N+1 confirmed
- **[169] `performance_agent` → `verification_agent`** (`agent_message`): Benchmark for list_orders_with_items(): query count grows linearly with rows (51 queries at n=50 -> 2001 at n=2000); N+1 confirmed
- **[170] `performance_agent` → `orchestrator`** (`agent_completed`): Performance Agent completed in 505 ms: 0 finding(s) published, 1 enriched
- **[171] `orchestrator` → `all_agents`** (`orchestrator_decision`): Review round 3: 2 task(s) completed, 0 new finding(s) Next: correlate.
- **[172] `correlation_agent` → `orchestrator`** (`agent_started`): Correlation Agent started: Correlate findings across agents
- **[173] `correlation_agent` → `orchestrator`** (`agent_message`): Correlation pass over 22 findings from 7 agents: 5 candidate relationship(s)
- **[174] `correlation_agent` → `blackboard`** (`correlation_updated`): Re-assessed contradiction: Agents disagree about list_orders_with_items()
- **[175] `correlation_agent` → `orchestrator`** (`agent_completed`): Correlation Agent completed in 41 ms: 0 new and 1 updated correlation(s) from 5 candidates
- **[176] `orchestrator` → `all_agents`** (`orchestrator_decision`): Review round 3: phase complete Next: verify.
- **[177] `verification_agent` → `orchestrator`** (`agent_started`): Verification / Red-Team Agent started: Red-team verification round 2
- **[178] `verification_agent` → `orchestrator`** (`verification_started`): Red-team round 2: challenging 2 finding(s) and pending correlations
- **[179] `verification_agent` → `performance_agent`** (`challenge`): Challenge to performance_agent: Has this been measured, or is it a theoretical static suspect? Is the code on a reachable path?
- **[180] `verification_agent` → `performance_agent`** (`finding_verified`): VERIFIED: Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. benchmark executed: query count grows linearly with rows (51 queries at n=50 -> 2001 at n
- **[181] `verification_agent` → `code_quality_agent`** (`challenge`): Challenge to code_quality_agent: Does measured evidence contradict this 'acceptable' assessment?
- **[182] `verification_agent` → `code_quality_agent`** (`finding_rejected`): REJECTED: Data-access function list_orders_with_items() assessed acceptable for maintainability (shopfront/services/orders.py) — Rejected: measured evidence from performance_agent contradicts this assessment (query count grows linearly with rows (51 queries at n=50 -> 2001 at n=2000); N+1 confirmed).
- **[183] `verification_agent` → `orchestrator`** (`correlation_updated`): Correlation verified: Agents disagree about list_orders_with_items() — Resolved in favour of performance_agent: Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED. code_quality_agent's position was rejected by evidence.
- **[184] `verification_agent` → `orchestrator`** (`correlation_updated`): Correlation needs more evidence: Unpinned requests is used on a hot path — awaiting verification of 1 member(s)
- **[185] `verification_agent` → `orchestrator`** (`agent_completed`): Verification / Red-Team Agent completed in 45 ms: Round 2: 1 rejected, 1 verified
- **[186] `orchestrator` → `all_agents`** (`orchestrator_decision`): Review round 3: phase complete Next: assess.
- **[187] `risk_agent` → `orchestrator`** (`agent_started`): Risk Assessment Agent started: Assess and prioritise verified risks
- **[188] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P0 (score 82.5): PyJWT 1.7.1 is affected by 11 known vulnerabilities
- **[189] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P4 (score 5.5): 1 test(s) in tests/test_orders.py only make weak assertions
- **[190] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P2 (score 50.2): PyJWT 1.7.1 is a major version behind latest 2.15.1, released 7 year(s) ago
- **[191] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P3 (score 17.2): Deprecated legacy_price_lookup() is still called from 1 production site(s)
- **[192] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P2 (score 48.5): Hardcoded fallback value for secret SHOPFRONT_SECRET in shopfront/auth/middleware.py
- **[193] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P2 (score 55.8): Security-critical authentication code has no tests (shopfront/auth/middleware.py, shopfront/auth/passwords.py)
- **[194] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P4 (score 8.3): python-dateutil appears unmaintained (latest release 2+ years ago)
- **[195] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P1 (score 63.0): JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py
- **[196] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P3 (score 17.2): 1 runtime dependency is not pinned to exact versions (requests>=2.20)
- **[197] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P3 (score 25.7): build_sales_report() has cyclomatic complexity 17 (shopfront/services/reports.py)
- **[198] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P1 (score 63.0): Passwords hashed with MD5 (fast, unsalted) in shopfront/auth/passwords.py
- **[199] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P3 (score 16.8): AI-directed instructions (possible prompt injection) in README.md
- **[200] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P3 (score 31.5): License metadata mismatch: pyproject.toml declares Apache-2.0 but LICENSE is MIT
- **[201] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P3 (score 12.9): Broad exception silently swallowed in shopfront/services/reports.py (1x)
- **[202] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P3 (score 34.7): GPL-3.0 licensed source in a MIT project (shopfront/vendor/fastcsv.py)
- **[203] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P3 (score 15.1): Failing test: tests/test_pricing.py::test_format_price_pads_single_digit_cents
- **[204] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P3 (score 30.3): Overall line coverage is 20%
- **[205] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P1 (score 72.9): Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py)
- **[206] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P2 (score 36.7): Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED
- **[207] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P2 (score 42.0): Upgrading pyjwt 1.7.1 -> 2.14.0 breaks 2 call site(s) in shopfront/auth/middleware.py
- **[208] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P0 (score 94.5) compound: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests
- **[209] `risk_agent` → `recommendation_agent`** (`risk_assessed`): P1 (score 66.9) compound: Concentrated weaknesses in the authentication component (3 security findings, untested)
- **[210] `risk_agent` → `orchestrator`** (`agent_message`): Risk assessment: 22 verified risk(s); overall 97.8 (critical); 3 finding(s) excluded
- **[211] `risk_agent` → `orchestrator`** (`agent_completed`): Risk Assessment Agent completed in 83 ms: 22 risks scored; overall 97.8 (critical)
- **[212] `recommendation_agent` → `orchestrator`** (`agent_started`): Recommendation Agent started: Generate remediation recommendations
- **[213] `recommendation_agent` → `human`** (`recommendation_created`): P0 recommendation: Fix compound risk: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests
- **[214] `recommendation_agent` → `human`** (`github_action_proposed`): ACTION PROPOSED: GitHub issue '[Skopeo P0] Fix compound risk: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests'
- **[215] `recommendation_agent` → `human`** (`github_action_proposed`): ACTION PROPOSED: draft PR '[Skopeo] Upgrade PyJWT to 2.15.1 (draft)'
- **[216] `recommendation_agent` → `human`** (`recommendation_created`): P1 recommendation: Fix compound risk: Concentrated weaknesses in the authentication component (3 security findings, untested)
- **[217] `recommendation_agent` → `human`** (`github_action_proposed`): ACTION PROPOSED: GitHub issue '[Skopeo P1] Fix compound risk: Concentrated weaknesses in the authentication component (3 security findings, untested)'
- **[218] `recommendation_agent` → `human`** (`recommendation_created`): P2 recommendation: PyJWT 1.7.1 is a major version behind latest 2.15.1, released 7 year(s) ago
- **[219] `recommendation_agent` → `human`** (`recommendation_created`): P2 recommendation: Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED
- **[220] `recommendation_agent` → `human`** (`recommendation_created`): P3 recommendation: GPL-3.0 licensed source in a MIT project (shopfront/vendor/fastcsv.py)
- **[221] `recommendation_agent` → `human`** (`recommendation_created`): P3 recommendation: License metadata mismatch: pyproject.toml declares Apache-2.0 but LICENSE is MIT
- **[222] `recommendation_agent` → `human`** (`recommendation_created`): P3 recommendation: Overall line coverage is 20%
- **[223] `recommendation_agent` → `human`** (`recommendation_created`): P3 recommendation: build_sales_report() has cyclomatic complexity 17 (shopfront/services/reports.py)
- **[224] `recommendation_agent` → `human`** (`recommendation_created`): P3 recommendation: Deprecated legacy_price_lookup() is still called from 1 production site(s)
- **[225] `recommendation_agent` → `human`** (`recommendation_created`): P3 recommendation: 1 runtime dependency is not pinned to exact versions (requests>=2.20)
- **[226] `recommendation_agent` → `human`** (`recommendation_created`): P3 recommendation: AI-directed instructions (possible prompt injection) in README.md
- **[227] `recommendation_agent` → `human`** (`recommendation_created`): P3 recommendation: Failing test: tests/test_pricing.py::test_format_price_pads_single_digit_cents
- **[228] `recommendation_agent` → `human`** (`recommendation_created`): P3 recommendation: Broad exception silently swallowed in shopfront/services/reports.py (1x)
- **[229] `recommendation_agent` → `orchestrator`** (`agent_completed`): Recommendation Agent completed in 54 ms: 13 recommendation(s) generated
- **[230] `orchestrator` → `human`** (`human_approval_required`): Human approval required before '[Skopeo P0] Fix compound risk: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests' (github_issue). Status: ACTION PROPOSED (DRY_RUN).
- **[231] `orchestrator` → `human`** (`human_approval_required`): Human approval required before '[Skopeo] Upgrade PyJWT to 2.15.1 (draft)' (pull_request). Status: ACTION PROPOSED (DRY_RUN).
- **[232] `orchestrator` → `human`** (`human_approval_required`): Human approval required before '[Skopeo P1] Fix compound risk: Concentrated weaknesses in the authentication component (3 security findings, untested)' (github_issue). Status: ACTION PROPOSED (DRY_RUN).
- **[233] `orchestrator` → `human`** (`investigation_completed`): Investigation COMPLETED_WITH_LIMITATIONS: 20 verified, 3 rejected, 1 insufficient evidence; overall risk 97.8 (critical); partial coverage: security_agent, dependency_agent, api_compatibility_agent, maintenance_agent, performance_agent

## 3. Red Team Verification Rulings
- **PyJWT 1.7.1 is affected by 11 known vulnerabilities** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. `jwt` imported by shopfront/auth/middleware.py; imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. claimed critical matches the highest advisory severity in the evidence (critical) for the exact pinned version.
- **Possible credential exposure: AWS access key ID in tests/fixtures/README.md** (round 1, decided by `policy`): ruling = `rejected`, confidence 0.70. The detected string occurs in tests/fixtures/README.md and matches a documented placeholder pattern. AKIA************MPLE: value matches a documented placeholder (AWS documentation example access key ID). all affected files are tests/fixtures/docs: tests/fixtures/README.md. No production credential exposure established.
- **Possible credential exposure: AWS access key ID and AWS secret access key in tests/fixtures/example_credentials.txt** (round 1, decided by `policy`): ruling = `rejected`, confidence 0.80. The detected string occurs in tests/fixtures/example_credentials.txt and matches a documented placeholder pattern. AKIA************MPLE: value matches a documented placeholder (AWS documentation example access key ID); wJal********************************EKEY: value matches a documented placeholder (AWS documentation example secret access key). example_credentials.txt is only referenced by tests (tests/test_config.py); no production code loads it. all affected files are tests/fixtures/docs: tests/fixtures/example_credentials.txt. No production credential exposure established.
- **Security-critical authentication code has no tests (shopfront/auth/middleware.py, shopfront/auth/passwords.py)** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 5 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. independently rebuilt import graph: no test imports shopfront/auth/middleware.py, shopfront/auth/passwords.py. shopfront/auth/middleware.py: 0% line coverage (0/23 statements) during the executed test run.
- **JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.
- **Passwords hashed with MD5 (fast, unsalted) in shopfront/auth/passwords.py** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.
- **GPL-3.0 licensed source in a MIT project (shopfront/vendor/fastcsv.py)** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. copyleft-licensed file is part of shipped code: imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.
- **Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py)** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 3 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.
- **PyJWT 1.7.1 is a major version behind latest 2.15.1, released 7 year(s) ago** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. `jwt` imported by shopfront/auth/middleware.py; imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py.
- **Hardcoded fallback value for secret SHOPFRONT_SECRET in shopfront/auth/middleware.py** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.
- **python-dateutil appears unmaintained (latest release 2+ years ago)** (round 1, decided by `policy`): ruling = `verified`, confidence 0.83. Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. Severity downgraded medium -> low: no production module imports `dateutil` — theoretical risk only
- **build_sales_report() has cyclomatic complexity 17 (shopfront/services/reports.py)** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. recomputed independently: complexity 17, 43 lines, nesting 5.
- **License metadata mismatch: pyproject.toml declares Apache-2.0 but LICENSE is MIT** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. 'Apache-2.0' and 'MIT' are distinct licenses with different obligations.
- **Failing test: tests/test_pricing.py::test_format_price_pads_single_digit_cents** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. reproduction confirmed: `python -B -m pytest -q -p no:cacheprovider --no-header --color=no tests/test_pricing.py::test_format_price_pads_single_digit_cents` failed again (exit 1, 799 ms).
- **Overall line coverage is 20%** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: evidence captured at the analysed commit 5eda3b9ec3. test-quality claim re-derived from the test AST.
- **Blocking network call inside a loop in notify_customers() (shopfront/services/notifications.py) — STATIC SUSPECT** (round 1, decided by `policy`): ruling = `needs_more_evidence`, confidence 0.88. Needs more evidence: STATIC SUSPECT only — no benchmark has measured the impact; a medium+ performance claim needs measurement.
- **Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED** (round 1, decided by `policy`): ruling = `needs_more_evidence`, confidence 0.80. Needs more evidence: STATIC SUSPECT only — no benchmark has measured the impact; a medium+ performance claim needs measurement. code_quality_agent disagrees; requires measurement to adjudicate.
- **Upgrading pyjwt 1.7.1 -> 2.14.0 breaks 2 call site(s) in shopfront/auth/middleware.py** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.
- **1 test(s) in tests/test_orders.py only make weak assertions** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. test-quality claim re-derived from the test AST.
- **Deprecated legacy_price_lookup() is still called from 1 production site(s)** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. shopfront/api/routes.py is itself an entrypoint. affected files are production code.
- **1 runtime dependency is not pinned to exact versions (requests>=2.20)** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. derived from deterministic git / GitHub data.
- **AI-directed instructions (possible prompt injection) in README.md** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. affected files are production code.
- **Broad exception silently swallowed in shopfront/services/reports.py (1x)** (round 1, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3.
- **Data-access function list_orders_with_items() assessed acceptable for maintainability (shopfront/services/orders.py)** (round 1, decided by `policy`): ruling = `needs_more_evidence`, confidence 0.83. Needs more evidence: contested by performance_agent; neither side measured.
- **correlation 293b1f40** (round 1, decided by `rule-engine`): ruling = `needs_more_evidence`, confidence 0.38. Contradiction unresolved: performance_agent=needs_more_evidence, code_quality_agent=needs_more_evidence
- **correlation cf46f22c** (round 1, decided by `rule-engine`): ruling = `verified`, confidence 0.89. 2 of 2 member findings verified
- **correlation 078d4455** (round 1, decided by `rule-engine`): ruling = `verified`, confidence 0.88. 4 of 4 member findings verified
- **correlation 24d03ce4** (round 1, decided by `rule-engine`): ruling = `verified`, confidence 0.51. 4 of 4 member findings verified
- **correlation 82aca656** (round 1, decided by `rule-engine`): ruling = `needs_more_evidence`, confidence 0.46. awaiting verification of 1 member(s)
- **Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED** (round 2, decided by `policy`): ruling = `verified`, confidence 1.00. Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. benchmark executed: query count grows linearly with rows (51 queries at n=50 -> 2001 at n=2000); N+1 confirmed.
- **Data-access function list_orders_with_items() assessed acceptable for maintainability (shopfront/services/orders.py)** (round 2, decided by `policy`): ruling = `rejected`, confidence 0.67. Rejected: measured evidence from performance_agent contradicts this assessment (query count grows linearly with rows (51 queries at n=50 -> 2001 at n=2000); N+1 confirmed).
- **correlation 293b1f40** (round 2, decided by `rule-engine`): ruling = `verified`, confidence 0.37. Resolved in favour of performance_agent: Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED. code_quality_agent's position was rejected by evidence.
- **correlation 82aca656** (round 2, decided by `rule-engine`): ruling = `needs_more_evidence`, confidence 0.46. awaiting verification of 1 member(s)

## 4. Risk Assessment (verified findings and compound risks only)
- **P0** · score `94.5` · Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests: P0 compound risk: most severe verified member is critical (PyJWT 1.7.1 is affected by 11 known vulnerabilities); correlation confidence 0.94; max member impact 1.00; max exploitability 0.80; multiplier 1.75 because 4 independently verified dimensions (api_compatibility, dependency, security, testing) reinforce each other. raw 1.317 -> score 94.5.
- **P0** · score `82.5` · PyJWT 1.7.1 is affected by 11 known vulnerabilities: P0 because: severity critical (1.0) x confidence 0.99 x impact 1.00 (affects security-critical component (authentication)) x exploitability 0.80 (reachable from request handlers / entrypoints) x correlation 1.00 = raw 0.792 -> score 82.5.
- **P1** · score `72.9` · Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py): P1 because: severity high (0.75) x confidence 0.99 x impact 1.00 (affects security-critical component (authentication)) x exploitability 0.80 (reachable from request handlers / entrypoints) x correlation 1.00 = raw 0.594 -> score 72.9.
- **P1** · score `66.9` · Concentrated weaknesses in the authentication component (3 security findings, untested): P1 compound risk: most severe verified member is high (JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py); correlation confidence 0.65; max member impact 1.00; max exploitability 0.80; multiplier 1.30 because 2 independently verified dimensions (security, testing) reinforce each other. raw 0.503 -> score 66.9.
- **P1** · score `63.0` · JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py: P1 because: severity high (0.75) x confidence 0.75 x impact 1.00 (affects security-critical component (authentication)) x exploitability 0.80 (reachable from request handlers / entrypoints) x correlation 1.00 = raw 0.452 -> score 63.0.
- **P1** · score `63.0` · Passwords hashed with MD5 (fast, unsalted) in shopfront/auth/passwords.py: P1 because: severity high (0.75) x confidence 0.75 x impact 1.00 (affects security-critical component (authentication)) x exploitability 0.80 (reachable from request handlers / entrypoints) x correlation 1.00 = raw 0.452 -> score 63.0.
- **P2** · score `55.8` · Security-critical authentication code has no tests (shopfront/auth/middleware.py, shopfront/auth/passwords.py): P2 because: severity high (0.75) x confidence 0.99 x impact 1.00 (affects security-critical component (authentication)) x exploitability 0.50 (likelihood that an untested/failing path ships a regression) x correlation 1.00 = raw 0.371 -> score 55.8.
- **P2** · score `50.2` · PyJWT 1.7.1 is a major version behind latest 2.15.1, released 7 year(s) ago: P2 because: severity medium (0.5) x confidence 0.99 x impact 0.80 (affects production dependency / code) x exploitability 0.80 (reachable from request handlers / entrypoints) x correlation 1.00 = raw 0.317 -> score 50.2.
- **P2** · score `48.5` · Hardcoded fallback value for secret SHOPFRONT_SECRET in shopfront/auth/middleware.py: P2 because: severity medium (0.5) x confidence 0.75 x impact 1.00 (affects security-critical component (authentication)) x exploitability 0.80 (reachable from request handlers / entrypoints) x correlation 1.00 = raw 0.301 -> score 48.5.
- **P2** · score `42.0` · Upgrading pyjwt 1.7.1 -> 2.14.0 breaks 2 call site(s) in shopfront/auth/middleware.py: P2 because: severity medium (0.5) x confidence 0.99 x impact 1.00 (affects security-critical component (authentication)) x exploitability 0.50 (default likelihood) x correlation 1.00 = raw 0.247 -> score 42.0.
- **P2** · score `36.7` · Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED: P2 because: severity medium (0.5) x confidence 0.99 x impact 0.70 (affects production code) x exploitability 0.60 (measured by benchmark) x correlation 1.00 = raw 0.208 -> score 36.7.
- **P3** · score `34.7` · GPL-3.0 licensed source in a MIT project (shopfront/vendor/fastcsv.py): P3 because: severity high (0.75) x confidence 0.72 x impact 0.60 (legal / distribution exposure) x exploitability 0.60 (obligations trigger on distribution) x correlation 1.00 = raw 0.194 -> score 34.7.
- **P3** · score `31.5` · License metadata mismatch: pyproject.toml declares Apache-2.0 but LICENSE is MIT: P3 because: severity medium (0.5) x confidence 0.95 x impact 0.60 (legal / distribution exposure) x exploitability 0.60 (obligations trigger on distribution) x correlation 1.00 = raw 0.172 -> score 31.5.
- **P3** · score `30.3` · Overall line coverage is 20%: P3 because: severity medium (0.5) x confidence 0.94 x impact 0.70 (affects production code) x exploitability 0.50 (likelihood that an untested/failing path ships a regression) x correlation 1.00 = raw 0.164 -> score 30.3.
- **P3** · score `25.7` · build_sales_report() has cyclomatic complexity 17 (shopfront/services/reports.py): P3 because: severity medium (0.5) x confidence 0.77 x impact 0.70 (affects production code) x exploitability 0.50 (default likelihood) x correlation 1.00 = raw 0.135 -> score 25.7.
- **P3** · score `17.2` · Deprecated legacy_price_lookup() is still called from 1 production site(s): P3 because: severity low (0.25) x confidence 0.98 x impact 0.70 (affects production code) x exploitability 0.50 (default likelihood) x correlation 1.00 = raw 0.086 -> score 17.2.
- **P3** · score `17.2` · 1 runtime dependency is not pinned to exact versions (requests>=2.20): P3 because: severity low (0.25) x confidence 0.86 x impact 0.80 (affects production dependency / code) x exploitability 0.50 (reachability unknown) x correlation 1.00 = raw 0.086 -> score 17.2.
- **P3** · score `16.8` · AI-directed instructions (possible prompt injection) in README.md: P3 because: severity low (0.25) x confidence 0.84 x impact 0.80 (affects production dependency / code) x exploitability 0.50 (reachability unknown) x correlation 1.00 = raw 0.084 -> score 16.8.
- **P3** · score `15.1` · Failing test: tests/test_pricing.py::test_format_price_pads_single_digit_cents: P3 because: severity medium (0.5) x confidence 0.99 x impact 0.30 (affects test code only) x exploitability 0.50 (likelihood that an untested/failing path ships a regression) x correlation 1.00 = raw 0.074 -> score 15.1.
- **P3** · score `12.9` · Broad exception silently swallowed in shopfront/services/reports.py (1x): P3 because: severity low (0.25) x confidence 0.72 x impact 0.70 (affects production code) x exploitability 0.50 (default likelihood) x correlation 1.00 = raw 0.063 -> score 12.9.
- **P4** · score `8.3` · python-dateutil appears unmaintained (latest release 2+ years ago): P4 because: severity low (0.25) x confidence 0.78 x impact 0.80 (affects production dependency / code) x exploitability 0.25 (not reachable from production code) x correlation 1.00 = raw 0.039 -> score 8.3.
- **P4** · score `5.5` · 1 test(s) in tests/test_orders.py only make weak assertions: P4 because: severity low (0.25) x confidence 0.69 x impact 0.30 (affects test code only) x exploitability 0.50 (likelihood that an untested/failing path ships a regression) x correlation 1.00 = raw 0.026 -> score 5.5.

## 5. Ask the agents: questions routed to the responsible agent (same run)

**Q:** What should I fix first?  
**Routed to:** `recommendation_agent` (Recommendation Agent owns this topic (matched 'fix', 'what should').) · routed by `policy` · answered by `policy`  
**Cited findings:** PyJWT 1.7.1 is affected by 11 known vulnerabilities (critical); Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py) (high); Upgrading pyjwt 1.7.1 -> 2.14.0 breaks 2 call site(s) in shopfront/auth/middleware.py (medium); Security-critical authentication code has no tests (shopfront/auth/middleware.py, shopfront/auth/passwords.py) (high); Hardcoded fallback value for secret SHOPFRONT_SECRET in shopfront/auth/middleware.py (medium); JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py (high)

> **Fix compound risk: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests** — P0, medium to implement
> 
> _Problem:_ PyJWT 1.7.1 is affected by 11 known vulnerabilities | Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py) | Upgrading pyjwt 1.7.1 -> 2.14.0 breaks 2 call site(s) in shopfront/auth/middleware.py…
> 
> 1. Upgrade PyJWT from 1.7.1 to 2.14.0 or later (resolves 11 advisories).
> 2. In the same change, update the breaking call sites (shopfront/auth/middleware.py:17, shopfront/auth/middleware.py:26): Drop the .decode('utf-8') call on the token. Pass an explicit allow-list, e.g. algorithms=["HS256"].
> 3. Add regression tests for shopfront/auth/middleware.py, shopfront/auth/passwords.py before merging (valid/expired/tampered tokens, wrong algorithm).
> 4. Re-run Skopeo to confirm the compound risk is closed.
> 
> _Expected benefit:_ Closes a P0 risk (score 94.5) and makes the upgrade path safe.
> 
> Also recommended:
> 
> - **Fix compound risk: Concentrated weaknesses in the authentication component (3 security findings, untested)** (P1, medium)
> - **PyJWT 1.7.1 is a major version behind latest 2.15.1, released 7 year(s) ago** (P2, medium)
> - **Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED** (P2, low)

**Q:** Is the JWT handling in this repository safe?  
**Routed to:** `security_agent` (Security Agent owns this topic (matched 'jwt', 'safe').) · routed by `policy` · answered by `policy`  
**Cited findings:** Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py) (high); JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py (high); Passwords hashed with MD5 (fast, unsalted) in shopfront/auth/passwords.py (high); Hardcoded fallback value for secret SHOPFRONT_SECRET in shopfront/auth/middleware.py (medium); AI-directed instructions (possible prompt injection) in README.md (low); Possible credential exposure: AWS access key ID in tests/fixtures/README.md (high)

> I (Security Agent) recorded **7 findings** (5 high, 1 medium, 1 low). Most relevant to your question:
> 
> - **Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py)** (high, verified, confidence 99%) — `shopfront/auth/middleware.py`. Fix: Prioritise upgrading pyjwt; review the listed call sites.
> - **JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py** (high, verified, confidence 75%) — `shopfront/auth/middleware.py`. Fix: Pass an explicit allow-list, e.g. jwt.decode(token, key, algorithms=['HS256']).
> - **Passwords hashed with MD5 (fast, unsalted) in shopfront/auth/passwords.py** (high, verified, confidence 75%) — `shopfront/auth/passwords.py`. Fix: Use a slow, salted password KDF (argon2id, bcrypt or scrypt) and migrate stored hashes.
> - **Hardcoded fallback value for secret SHOPFRONT_SECRET in shopfront/auth/middleware.py** (medium, verified, confidence 75%) — `shopfront/auth/middleware.py`. Fix: Remove the literal fallback; fail fast when the secret is not configured, then rotate it.

**Q:** Which findings did the red team reject, and why?  
**Routed to:** `verification_agent` (Verification Agent owns this topic (matched 'reject', 'red team').) · routed by `policy` · answered by `policy`  
**Cited findings:** Possible credential exposure: AWS access key ID and AWS secret access key in tests/fixtures/example_credentials.txt (high); Possible credential exposure: AWS access key ID in tests/fixtures/README.md (high); Data-access function list_orders_with_items() assessed acceptable for maintainability (shopfront/services/orders.py) (info); PyJWT 1.7.1 is affected by 11 known vulnerabilities (critical); Security-critical authentication code has no tests (shopfront/auth/middleware.py, shopfront/auth/passwords.py) (high); JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py (high)

> I made 33 rulings on findings and correlations, across all verification rounds: 24 verified, 3 rejected, 6 needs more evidence.
> 
> - **Possible credential exposure: AWS access key ID and AWS secret access key in tests/fixtures/example_credentials.txt** — rejected (80%). The detected string occurs in tests/fixtures/example_credentials.txt and matches a documented placeholder pattern. AKIA************MPLE: value matches a documented placeholder (AWS documentation example access key ID); wJal********************************EKEY: value matches a documented placeholder (AWS documentation example secret access key)…
> - **Possible credential exposure: AWS access key ID in tests/fixtures/README.md** — rejected (70%). The detected string occurs in tests/fixtures/README.md and matches a documented placeholder pattern. AKIA************MPLE: value matches a documented placeholder (AWS documentation example access key ID). all affected files are tests/fixtures/docs: tests/fixtures/README.md. No production credential exposure established.
> - **Data-access function list_orders_with_items() assessed acceptable for maintainability (shopfront/services/orders.py)** — rejected (67%). Rejected: measured evidence from performance_agent contradicts this assessment (query count grows linearly with rows (51 queries at n=50 -> 2001 at n=2000); N+1 confirmed).
> - **PyJWT 1.7.1 is affected by 11 known vulnerabilities** — verified (100%). Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. `jwt` imported by shopfront/auth/middleware.py; imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. claimed critical matches the highest advisory severity in the evidence (critical) for the exact pinned version.
> - **Security-critical authentication code has no tests (shopfront/auth/middleware.py, shopfront/auth/passwords.py)** — verified (100%). Verified: re-hashed 5 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. independently rebuilt import graph: no test imports shopfront/auth/middleware.py, shopfront/auth/passwords.py. shopfront/auth/middleware.py: 0% line coverage (0/23 statements) during the executed test run.

**Q:** Is the project's license compatible with its dependencies?  
**Routed to:** `license_agent` (License Compliance Agent owns this topic (matched 'license').) · routed by `policy` · answered by `policy`  
**Cited findings:** GPL-3.0 licensed source in a MIT project (shopfront/vendor/fastcsv.py) (high); License metadata mismatch: pyproject.toml declares Apache-2.0 but LICENSE is MIT (medium)

> I (License Compliance Agent) recorded **2 findings** (1 high, 1 medium). Most relevant to your question:
> 
> - **GPL-3.0 licensed source in a MIT project (shopfront/vendor/fastcsv.py)** (high, verified, confidence 72%) — `shopfront/vendor/fastcsv.py`. Fix: Replace the GPL-3.0 code, obtain it under a compatible license, or relicense consciously.
> - **License metadata mismatch: pyproject.toml declares Apache-2.0 but LICENSE is MIT** (medium, verified, confidence 95%) — `pyproject.toml`. Fix: Make pyproject.toml and LICENSE agree (decide which license is intended).
