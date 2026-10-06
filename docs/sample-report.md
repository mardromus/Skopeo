# Skopeo Investigation — examples/vulnerable-demo-repo

- **Repository:** bundled://examples/vulnerable-demo-repo (branch `main`, commit `5eda3b9ec3`)
- **Status:** `completed_with_limitations`
- **Overall risk:** 97.8 (critical)
- **Findings:** 24 — 20 verified, 3 rejected, 1 insufficient evidence
- **Agent runs:** 21 (1 failed, 1 retries, 5 follow-ups, 2 replans, max parallelism 8)
- **Duration:** 45.86 s · LLM provider `mock` (0 model calls, 58 decisions)

## Agent Activity

| Agent | Runs | Statuses | Findings | Duration (ms) |
| --- | --- | --- | --- | --- |
| orchestrator | 1 | completed | 0 | 45899 |
| security_agent | 2 | completed, completed | 7 | 2059 |
| dependency_agent | 1 | completed | 4 | 1373 |
| test_reliability_agent | 2 | completed, completed | 4 | 17080 |
| api_compatibility_agent | 2 | completed, completed | 2 | 1503 |
| performance_agent | 4 | failed (ToolUnavailableError), completed, completed, completed | 2 | 3364 |
| code_quality_agent | 1 | completed | 3 | 1324 |
| license_agent | 1 | completed | 2 | 1111 |
| maintenance_agent | 1 | completed | 0 | 804 |
| correlation_agent | 2 | completed, completed | 0 | 2434 |
| verification_agent | 2 | completed, completed | 0 | 15806 |
| risk_agent | 1 | completed | 0 | 706 |
| recommendation_agent | 1 | completed | 0 | 3298 |

### Coverage

| Specialist | Coverage | Notes |
| --- | --- | --- |
| security_agent | **PARTIAL** | Dependabot alerts not queried (no GITHUB_TOKEN or not a GitHub source); Semgrep not installed — built-in AST/regex rules used instead |
| dependency_agent | **PARTIAL** | No Python lockfile: transitive dependencies were not resolved |
| code_quality_agent | **COMPLETE** |  |
| api_compatibility_agent | **PARTIAL** | INSUFFICIENT EVIDENCE for breaking-change detection: git history has 1 commit(s) |
| test_reliability_agent | **COMPLETE** |  |
| license_agent | **COMPLETE** |  |
| maintenance_agent | **PARTIAL** | GitHub metadata unavailable (offline or bundled fixture) — issues/PRs/releases not assessed; INSUFFICIENT EVIDENCE: only 1 commit(s) available — activity metrics would be meaningless |
| performance_agent | **PARTIAL** | attempt 1 (full/default) FAILED: ToolUnavailableError: benchmark harness unavailable [controlled fault injection: SKOPEO_FAULT_INJECTION=performance_agent@1]; Degraded strategy 'static_only': no benchmarks or profiling in this run; No benchmark harness for notify_customers() (shopfront/services/notifications.py) |

## Verified Risks

| Priority | Score | Risk | Rationale |
| --- | --- | --- | --- |
| P0 | 94.5 | Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests | P0 compound risk: most severe verified member is critical (PyJWT 1.7.1 is affected by 11 known vulnerabilities); correlation confidence 0.94; max member impact 1.00; max exploitability 0.80; multiplier 1.75 because 4 independently verified dimensions (api_compatibility, dependency, security, testing) reinforce each other. raw 1.317 -> score 94.5. |
| P0 | 82.5 | PyJWT 1.7.1 is affected by 11 known vulnerabilities | P0 because: severity critical (1.0) x confidence 0.99 x impact 1.00 (affects security-critical component (authentication)) x exploitability 0.80 (reachable from request handlers / entrypoints) x correlation 1.00 = raw 0.792 -> score 82.5. |
| P1 | 72.9 | Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py) | P1 because: severity high (0.75) x confidence 0.99 x impact 1.00 (affects security-critical component (authentication)) x exploitability 0.80 (reachable from request handlers / entrypoints) x correlation 1.00 = raw 0.594 -> score 72.9. |
| P1 | 66.9 | Concentrated weaknesses in the authentication component (3 security findings, untested) | P1 compound risk: most severe verified member is high (JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py); correlation confidence 0.65; max member impact 1.00; max exploitability 0.80; multiplier 1.30 because 2 independently verified dimensions (security, testing) reinforce each other. raw 0.503 -> score 66.9. |
| P1 | 63.0 | JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py | P1 because: severity high (0.75) x confidence 0.75 x impact 1.00 (affects security-critical component (authentication)) x exploitability 0.80 (reachable from request handlers / entrypoints) x correlation 1.00 = raw 0.452 -> score 63.0. |
| P1 | 63.0 | Passwords hashed with MD5 (fast, unsalted) in shopfront/auth/passwords.py | P1 because: severity high (0.75) x confidence 0.75 x impact 1.00 (affects security-critical component (authentication)) x exploitability 0.80 (reachable from request handlers / entrypoints) x correlation 1.00 = raw 0.452 -> score 63.0. |
| P2 | 55.8 | Security-critical authentication code has no tests (shopfront/auth/middleware.py, shopfront/auth/passwords.py) | P2 because: severity high (0.75) x confidence 0.99 x impact 1.00 (affects security-critical component (authentication)) x exploitability 0.50 (likelihood that an untested/failing path ships a regression) x correlation 1.00 = raw 0.371 -> score 55.8. |
| P2 | 50.2 | PyJWT 1.7.1 is a major version behind latest 2.15.1, released 7 year(s) ago | P2 because: severity medium (0.5) x confidence 0.99 x impact 0.80 (affects production dependency / code) x exploitability 0.80 (reachable from request handlers / entrypoints) x correlation 1.00 = raw 0.317 -> score 50.2. |
| P2 | 48.5 | Hardcoded fallback value for secret SHOPFRONT_SECRET in shopfront/auth/middleware.py | P2 because: severity medium (0.5) x confidence 0.75 x impact 1.00 (affects security-critical component (authentication)) x exploitability 0.80 (reachable from request handlers / entrypoints) x correlation 1.00 = raw 0.301 -> score 48.5. |
| P2 | 42.0 | Upgrading pyjwt 1.7.1 -> 2.14.0 breaks 2 call site(s) in shopfront/auth/middleware.py | P2 because: severity medium (0.5) x confidence 0.99 x impact 1.00 (affects security-critical component (authentication)) x exploitability 0.50 (default likelihood) x correlation 1.00 = raw 0.247 -> score 42.0. |
| P2 | 36.7 | Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED | P2 because: severity medium (0.5) x confidence 0.99 x impact 0.70 (affects production code) x exploitability 0.60 (measured by benchmark) x correlation 1.00 = raw 0.208 -> score 36.7. |
| P3 | 34.7 | GPL-3.0 licensed source in a MIT project (shopfront/vendor/fastcsv.py) | P3 because: severity high (0.75) x confidence 0.72 x impact 0.60 (legal / distribution exposure) x exploitability 0.60 (obligations trigger on distribution) x correlation 1.00 = raw 0.194 -> score 34.7. |
| P3 | 31.5 | License metadata mismatch: pyproject.toml declares Apache-2.0 but LICENSE is MIT | P3 because: severity medium (0.5) x confidence 0.95 x impact 0.60 (legal / distribution exposure) x exploitability 0.60 (obligations trigger on distribution) x correlation 1.00 = raw 0.172 -> score 31.5. |
| P3 | 30.3 | Overall line coverage is 20% | P3 because: severity medium (0.5) x confidence 0.94 x impact 0.70 (affects production code) x exploitability 0.50 (likelihood that an untested/failing path ships a regression) x correlation 1.00 = raw 0.164 -> score 30.3. |
| P3 | 25.7 | build_sales_report() has cyclomatic complexity 17 (shopfront/services/reports.py) | P3 because: severity medium (0.5) x confidence 0.77 x impact 0.70 (affects production code) x exploitability 0.50 (default likelihood) x correlation 1.00 = raw 0.135 -> score 25.7. |
| P3 | 17.2 | Deprecated legacy_price_lookup() is still called from 1 production site(s) | P3 because: severity low (0.25) x confidence 0.98 x impact 0.70 (affects production code) x exploitability 0.50 (default likelihood) x correlation 1.00 = raw 0.086 -> score 17.2. |
| P3 | 17.2 | 1 runtime dependency is not pinned to exact versions (requests>=2.20) | P3 because: severity low (0.25) x confidence 0.86 x impact 0.80 (affects production dependency / code) x exploitability 0.50 (reachability unknown) x correlation 1.00 = raw 0.086 -> score 17.2. |
| P3 | 16.8 | AI-directed instructions (possible prompt injection) in README.md | P3 because: severity low (0.25) x confidence 0.84 x impact 0.80 (affects production dependency / code) x exploitability 0.50 (reachability unknown) x correlation 1.00 = raw 0.084 -> score 16.8. |
| P3 | 15.1 | Failing test: tests/test_pricing.py::test_format_price_pads_single_digit_cents | P3 because: severity medium (0.5) x confidence 0.99 x impact 0.30 (affects test code only) x exploitability 0.50 (likelihood that an untested/failing path ships a regression) x correlation 1.00 = raw 0.074 -> score 15.1. |
| P3 | 12.9 | Broad exception silently swallowed in shopfront/services/reports.py (1x) | P3 because: severity low (0.25) x confidence 0.72 x impact 0.70 (affects production code) x exploitability 0.50 (default likelihood) x correlation 1.00 = raw 0.063 -> score 12.9. |
| P4 | 8.3 | python-dateutil appears unmaintained (latest release 2+ years ago) | P4 because: severity low (0.25) x confidence 0.78 x impact 0.80 (affects production dependency / code) x exploitability 0.25 (not reachable from production code) x correlation 1.00 = raw 0.039 -> score 8.3. |
| P4 | 5.5 | 1 test(s) in tests/test_orders.py only make weak assertions | P4 because: severity low (0.25) x confidence 0.69 x impact 0.30 (affects test code only) x exploitability 0.50 (likelihood that an untested/failing path ships a regression) x correlation 1.00 = raw 0.026 -> score 5.5. |

## Correlations

- **[contradiction · resolved · x1.0]** Agents disagree about list_orders_with_items() — performance_agent reports 'Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED' while code_quality_agent assessed the same function as acceptable. Benchmark evidence now supports performance_agent; the 'acceptable' assessment relied on the small seed dataset. _Resolution: Resolved in favour of performance_agent: Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED. code_quality_agent's position was rejected by evidence._
- **[shared_root_cause · verified · x1.0]** Shared root cause: stale pin of pyjwt 1.7.1 — 2 dependency findings (dependency.vulnerable, dependency.outdated) stem from the same pinned version pyjwt==1.7.1; one upgrade resolves all of them.
- **[compound_risk · verified · x1.75]** Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests — These findings form a compound risk: dependency_agent: PyJWT 1.7.1 is affected by 11 known vulnerabilities | api_compatibility_agent: Upgrading pyjwt 1.7.1 -> 2.14.0 breaks 2 call site(s) in shopfront/auth/middleware.py | security_agent: Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py) | test_reliability_agent: Security-critical authentication code has no tests (shopfront/auth/middleware.py, shopfront/auth/passwords.py). A vulnerable dependency is used in security-critical authentication code whose upgrade is insufficiently tested and the upgrade breaks existing call sites.
- **[compound_risk · verified · x1.3]** Concentrated weaknesses in the authentication component (3 security findings, untested) — 3 independent security weaknesses affect authentication code (Hardcoded fallback value for secret SHOPFRONT_SECRET in shopfront/auth/middleware.py; JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py; Passwords hashed with MD5 (fast, unsalted) in shopfront/auth/passwords.py), and security-critical authentication code has no tests (shopfront/auth/middleware.py, shopfront/auth/passwords.py). Fixing them in isolation without tests risks regressions.
- **[dependency · proposed · x1.05]** Unpinned requests is used on a hot path — requests has no exact version pin and is used by: Blocking network call inside a loop in notify_customers() (shopfront/services/notifications.py) — STATIC SUSPECT. Behaviour of that path can change with any new release.

## Verification (Red-Team)

### Possible credential exposure: AWS access key ID in tests/fixtures/README.md
- Proposed by `security_agent` · severity high · final status **REJECTED** · confidence 0.10
- Challenge: Is this a live credential, or a documented dummy value in a fixture? Is it used by production code?
  - `evidence_integrity` → pass: re-hashed 1 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `location_context` → fail: all affected files are tests/fixtures/docs: tests/fixtures/README.md
  - `placeholder` → fail: AKIA************MPLE: value matches a documented placeholder (AWS documentation example access key ID)
  - `production_reference` → pass: README.md referenced by production files pyproject.toml
- Decision: **REJECTED** — The detected string occurs in tests/fixtures/README.md and matches a documented placeholder pattern. AKIA************MPLE: value matches a documented placeholder (AWS documentation example access key ID). all affected files are tests/fixtures/docs: tests/fixtures/README.md. No production credential exposure established.

### build_sales_report() has cyclomatic complexity 17 (shopfront/services/reports.py)
- Proposed by `code_quality_agent` · severity medium · final status **VERIFIED** · confidence 0.77
- Challenge: Is the evidence real, current and reachable, and is the severity justified?
  - `evidence_integrity` → pass: re-hashed 2 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `recompute` → pass: recomputed independently: complexity 17, 43 lines, nesting 5
- Decision: **VERIFIED** — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. recomputed independently: complexity 17, 43 lines, nesting 5.

### Possible credential exposure: AWS access key ID and AWS secret access key in tests/fixtures/example_credentials.txt
- Proposed by `security_agent` · severity high · final status **REJECTED** · confidence 0.10
- Challenge: Is this a live credential, or a documented dummy value in a fixture? Is it used by production code?
  - `evidence_integrity` → pass: re-hashed 2 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `location_context` → fail: all affected files are tests/fixtures/docs: tests/fixtures/example_credentials.txt
  - `placeholder` → fail: AKIA************MPLE: value matches a documented placeholder (AWS documentation example access key ID); wJal********************************EKEY: value matches a documented placeholder (AWS documentation example secret access key)
  - `production_reference` → fail: example_credentials.txt is only referenced by tests (tests/test_config.py); no production code loads it
- Decision: **REJECTED** — The detected string occurs in tests/fixtures/example_credentials.txt and matches a documented placeholder pattern. AKIA************MPLE: value matches a documented placeholder (AWS documentation example access key ID); wJal********************************EKEY: value matches a documented placeholder (AWS documentation example secret access key). example_credentials.txt is only referenced by tests (tests/test_config.py); no production code loads it. all affected files are tests/fixtures/docs: tests/fixtures/example_credentials.txt. No production credential exposure established.

### Deprecated legacy_price_lookup() is still called from 1 production site(s)
- Proposed by `api_compatibility_agent` · severity low · final status **VERIFIED** · confidence 0.98
- Challenge: Is the evidence real, current and reachable, and is the severity justified?
  - `evidence_integrity` → pass: re-hashed 2 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `reachability` → pass: shopfront/api/routes.py is itself an entrypoint
  - `location_context` → pass: affected files are production code
- Decision: **VERIFIED** — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. shopfront/api/routes.py is itself an entrypoint. affected files are production code.

### 1 test(s) in tests/test_orders.py only make weak assertions
- Proposed by `test_reliability_agent` · severity low · final status **VERIFIED** · confidence 0.69
- Challenge: Do tests really not exercise this code? Re-derive the mapping independently.
  - `evidence_integrity` → pass: re-hashed 1 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `recheck` → pass: test-quality claim re-derived from the test AST
- Decision: **VERIFIED** — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. test-quality claim re-derived from the test AST.

### Broad exception silently swallowed in shopfront/services/reports.py (1x)
- Proposed by `code_quality_agent` · severity low · final status **VERIFIED** · confidence 0.72
- Challenge: Is the evidence real, current and reachable, and is the severity justified?
  - `evidence_integrity` → pass: re-hashed 1 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
- Decision: **VERIFIED** — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3.

### PyJWT 1.7.1 is affected by 11 known vulnerabilities
- Proposed by `dependency_agent` · severity critical · final status **VERIFIED** · confidence 0.99
- Challenge: Is pyjwt actually imported and reachable, and is the critical severity backed by the advisory data?
  - `evidence_integrity` → pass: re-hashed 1 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `dependency_used` → pass: `jwt` imported by shopfront/auth/middleware.py; imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py
  - `severity_justified` → pass: claimed critical matches the highest advisory severity in the evidence (critical) for the exact pinned version
- Decision: **VERIFIED** — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. `jwt` imported by shopfront/auth/middleware.py; imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. claimed critical matches the highest advisory severity in the evidence (critical) for the exact pinned version.

### License metadata mismatch: pyproject.toml declares Apache-2.0 but LICENSE is MIT
- Proposed by `license_agent` · severity medium · final status **VERIFIED** · confidence 0.95
- Challenge: Is the evidence real, current and reachable, and is the severity justified?
  - `evidence_integrity` → pass: re-hashed 2 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `false_positive` → pass: 'Apache-2.0' and 'MIT' are distinct licenses with different obligations
- Decision: **VERIFIED** — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. 'Apache-2.0' and 'MIT' are distinct licenses with different obligations.

### Hardcoded fallback value for secret SHOPFRONT_SECRET in shopfront/auth/middleware.py
- Proposed by `security_agent` · severity medium · final status **VERIFIED** · confidence 0.75
- Challenge: Is the evidence real, current and reachable, and is the severity justified?
  - `evidence_integrity` → pass: re-hashed 1 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `reachability` → pass: imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py
  - `location_context` → pass: affected files are production code
  - `mitigation` → pass: no deployment configuration sets the variable; the literal fallback is used whenever it is absent (os.environ.get)
- Decision: **VERIFIED** — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.

### Security-critical authentication code has no tests (shopfront/auth/middleware.py, shopfront/auth/passwords.py)
- Proposed by `test_reliability_agent` · severity high · final status **VERIFIED** · confidence 0.99
- Challenge: Do tests really not exercise this code? Re-derive the mapping independently.
  - `evidence_integrity` → pass: re-hashed 5 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `independent_mapping` → pass: independently rebuilt import graph: no test imports shopfront/auth/middleware.py, shopfront/auth/passwords.py
  - `coverage_measurement` → pass: shopfront/auth/middleware.py: 0% line coverage (0/23 statements) during the executed test run
- Decision: **VERIFIED** — Verified: re-hashed 5 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. independently rebuilt import graph: no test imports shopfront/auth/middleware.py, shopfront/auth/passwords.py. shopfront/auth/middleware.py: 0% line coverage (0/23 statements) during the executed test run.

### GPL-3.0 licensed source in a MIT project (shopfront/vendor/fastcsv.py)
- Proposed by `license_agent` · severity high · final status **VERIFIED** · confidence 0.72
- Challenge: Is the evidence real, current and reachable, and is the severity justified?
  - `evidence_integrity` → pass: re-hashed 1 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `reachability` → pass: copyleft-licensed file is part of shipped code: imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py
  - `location_context` → pass: affected files are production code
- Decision: **VERIFIED** — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. copyleft-licensed file is part of shipped code: imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.

### PyJWT 1.7.1 is a major version behind latest 2.15.1, released 7 year(s) ago
- Proposed by `dependency_agent` · severity medium · final status **VERIFIED** · confidence 0.99
- Challenge: Is the evidence real, current and reachable, and is the severity justified?
  - `evidence_integrity` → pass: re-hashed 1 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `dependency_used` → pass: `jwt` imported by shopfront/auth/middleware.py; imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py
- Decision: **VERIFIED** — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. `jwt` imported by shopfront/auth/middleware.py; imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py.

### JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py
- Proposed by `security_agent` · severity high · final status **VERIFIED** · confidence 0.75
- Challenge: Is the evidence real, current and reachable, and is the severity justified?
  - `evidence_integrity` → pass: re-hashed 1 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `reachability` → pass: imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py
  - `location_context` → pass: affected files are production code
  - `mitigation` → pass: no mitigation: PyJWT 1.7.1 (<2.0) accepts the algorithm named in the token header when algorithms is omitted
- Decision: **VERIFIED** — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.

### python-dateutil appears unmaintained (latest release 2+ years ago)
- Proposed by `dependency_agent` · severity low · final status **VERIFIED** · confidence 0.78
- Challenge: Is the evidence real, current and reachable, and is the severity justified?
  - `evidence_integrity` → pass: re-hashed 1 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `dependency_used` → fail: no production module imports `dateutil` — theoretical risk only
- Decision: **VERIFIED** — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. Severity downgraded medium -> low: no production module imports `dateutil` — theoretical risk only

### Data-access function list_orders_with_items() assessed acceptable for maintainability (shopfront/services/orders.py)
- Proposed by `code_quality_agent` · severity info · final status **REJECTED** · confidence 0.10
- Challenge: Does measured evidence contradict this 'acceptable' assessment?
  - `evidence_integrity` → pass: re-hashed 1 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `contradiction` → fail: measured evidence from performance_agent contradicts this assessment (query count grows linearly with rows (51 queries at n=50 -> 2001 at n=2000); N+1 confirmed)
- Decision: **REJECTED** — Rejected: measured evidence from performance_agent contradicts this assessment (query count grows linearly with rows (51 queries at n=50 -> 2001 at n=2000); N+1 confirmed).

### Passwords hashed with MD5 (fast, unsalted) in shopfront/auth/passwords.py
- Proposed by `security_agent` · severity high · final status **VERIFIED** · confidence 0.75
- Challenge: Is the evidence real, current and reachable, and is the severity justified?
  - `evidence_integrity` → pass: re-hashed 1 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `reachability` → pass: imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py
  - `location_context` → pass: affected files are production code
- Decision: **VERIFIED** — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.

### 1 runtime dependency is not pinned to exact versions (requests>=2.20)
- Proposed by `dependency_agent` · severity low · final status **VERIFIED** · confidence 0.86
- Challenge: Is the evidence real, current and reachable, and is the severity justified?
  - `evidence_integrity` → pass: re-hashed 1 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `source_quality` → pass: derived from deterministic git / GitHub data
- Decision: **VERIFIED** — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. derived from deterministic git / GitHub data.

### AI-directed instructions (possible prompt injection) in README.md
- Proposed by `security_agent` · severity low · final status **VERIFIED** · confidence 0.84
- Challenge: Is the evidence real, current and reachable, and is the severity justified?
  - `evidence_integrity` → pass: re-hashed 2 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `reachability` → not_applicable: no Python module to trace
  - `location_context` → pass: affected files are production code
- Decision: **VERIFIED** — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. affected files are production code.

### Failing test: tests/test_pricing.py::test_format_price_pads_single_digit_cents
- Proposed by `test_reliability_agent` · severity medium · final status **VERIFIED** · confidence 0.99
- Challenge: Does the failure reproduce on an independent re-run?
  - `evidence_integrity` → pass: re-hashed 1 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `reproduction` → pass: reproduction confirmed: `python -B -m pytest -q -p no:cacheprovider --no-header --color=no tests/test_pricing.py::test_format_price_pads_single_digit_cents` failed again (exit 1, 8420 ms)
- Decision: **VERIFIED** — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. reproduction confirmed: `python -B -m pytest -q -p no:cacheprovider --no-header --color=no tests/test_pricing.py::test_format_price_pads_single_digit_cents` failed again (exit 1, 8420 ms).

### Overall line coverage is 20%
- Proposed by `test_reliability_agent` · severity medium · final status **VERIFIED** · confidence 0.94
- Challenge: Do tests really not exercise this code? Re-derive the mapping independently.
  - `evidence_integrity` → not_applicable: 1 evidence item(s) reference external/tool data rather than file lines
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `recheck` → pass: test-quality claim re-derived from the test AST
- Decision: **VERIFIED** — Verified: evidence captured at the analysed commit 5eda3b9ec3. test-quality claim re-derived from the test AST.

### Blocking network call inside a loop in notify_customers() (shopfront/services/notifications.py) — STATIC SUSPECT
- Proposed by `performance_agent` · severity medium · final status **NEEDS_MORE_EVIDENCE** · confidence 0.34
- Challenge: Has this been measured, or is it a theoretical static suspect? Is the code on a reachable path?
  - `evidence_integrity` → pass: re-hashed 1 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `reachability` → pass: imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py
  - `theoretical_vs_actual` → inconclusive: STATIC SUSPECT only — no benchmark has measured the impact; a medium+ performance claim needs measurement
- Decision: **NEEDS_MORE_EVIDENCE** — Needs more evidence: STATIC SUSPECT only — no benchmark has measured the impact; a medium+ performance claim needs measurement.

### Upgrading pyjwt 1.7.1 -> 2.14.0 breaks 2 call site(s) in shopfront/auth/middleware.py
- Proposed by `api_compatibility_agent` · severity medium · final status **VERIFIED** · confidence 0.99
- Challenge: Is the evidence real, current and reachable, and is the severity justified?
  - `evidence_integrity` → pass: re-hashed 2 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `reachability` → pass: imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py
  - `location_context` → pass: affected files are production code
- Decision: **VERIFIED** — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.

### Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py)
- Proposed by `security_agent` · severity high · final status **VERIFIED** · confidence 0.99
- Challenge: Is the evidence real, current and reachable, and is the severity justified?
  - `evidence_integrity` → pass: re-hashed 3 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `reachability` → pass: imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py
  - `location_context` → pass: affected files are production code
  - `usage_claim` → pass: call sites: shopfront/auth/middleware.py:16, shopfront/auth/middleware.py:26
- Decision: **VERIFIED** — Verified: re-hashed 3 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. affected files are production code.

### Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED
- Proposed by `performance_agent` · severity medium · final status **VERIFIED** · confidence 0.99
- Challenge: Has this been measured, or is it a theoretical static suspect? Is the code on a reachable path?
  - `evidence_integrity` → pass: re-hashed 2 referenced line range(s); all match the repository
  - `staleness` → pass: evidence captured at the analysed commit 5eda3b9ec3
  - `reachability` → pass: imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py
  - `reproduction` → pass: benchmark executed: query count grows linearly with rows (51 queries at n=50 -> 2001 at n=2000); N+1 confirmed
  - `contradiction` → pass: contradicting assessment by code_quality_agent is not backed by measurement; this finding is
- Decision: **VERIFIED** — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. imported (transitively) by entrypoint(s) shopfront/api/routes.py, shopfront/app.py. benchmark executed: query count grows linearly with rows (51 queries at n=50 -> 2001 at n=2000); N+1 confirmed.

## Rejected Findings

- ~~Possible credential exposure: AWS access key ID in tests/fixtures/README.md~~ — The detected string occurs in tests/fixtures/README.md and matches a documented placeholder pattern. AKIA************MPLE: value matches a documented placeholder (AWS documentation example access key ID). all affected files are tests/fixtures/docs: tests/fixtures/README.md. No production credential exposure established.
- ~~Possible credential exposure: AWS access key ID and AWS secret access key in tests/fixtures/example_credentials.txt~~ — The detected string occurs in tests/fixtures/example_credentials.txt and matches a documented placeholder pattern. AKIA************MPLE: value matches a documented placeholder (AWS documentation example access key ID); wJal********************************EKEY: value matches a documented placeholder (AWS documentation example secret access key). example_credentials.txt is only referenced by tests (tests/test_config.py); no production code loads it. all affected files are tests/fixtures/docs: tests/fixtures/example_credentials.txt. No production credential exposure established.
- ~~Data-access function list_orders_with_items() assessed acceptable for maintainability (shopfront/services/orders.py)~~ — Rejected: measured evidence from performance_agent contradicts this assessment (query count grows linearly with rows (51 queries at n=50 -> 2001 at n=2000); N+1 confirmed).

## Insufficient Evidence (excluded from risk)

- Blocking network call inside a loop in notify_customers() (shopfront/services/notifications.py) — STATIC SUSPECT — Needs more evidence: STATIC SUSPECT only — no benchmark has measured the impact; a medium+ performance claim needs measurement.

## Recommendations

### [P0] Fix compound risk: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests
- **Problem:** Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests. PyJWT 1.7.1 is affected by 11 known vulnerabilities | Upgrading pyjwt 1.7.1 -> 2.14.0 breaks 2 call site(s) in shopfront/auth/middleware.py | Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py) | Security-critical authentication code has no tests (shopfront/auth/middleware.py, shopfront/auth/passwords.py)
- **Affected component:** authentication
- **Why it matters:** Independent agents verified 4 linked problems across 4 dimensions; together they are worse than each alone (multiplier 1.75).
- **Proposed fix:**

1. Upgrade PyJWT from 1.7.1 to 2.14.0 or later (resolves 11 advisories).
2. In the same change, update the breaking call sites (shopfront/auth/middleware.py:17, shopfront/auth/middleware.py:26): Drop the .decode('utf-8') call on the token. Pass an explicit allow-list, e.g. algorithms=["HS256"].
3. Add regression tests for shopfront/auth/middleware.py, shopfront/auth/passwords.py before merging (valid/expired/tampered tokens, wrong algorithm).
4. Re-run Skopeo to confirm the compound risk is closed.

- **Estimated risk:** {'priority': 'P0', 'score': 94.5} · **Verification:** verified · **Difficulty:** medium
- **Expected benefit:** Closes a P0 risk (score 94.5) and makes the upgrade path safe.

### [P1] Fix compound risk: Concentrated weaknesses in the authentication component (3 security findings, untested)
- **Problem:** Concentrated weaknesses in the authentication component (3 security findings, untested). Hardcoded fallback value for secret SHOPFRONT_SECRET in shopfront/auth/middleware.py | JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py | Passwords hashed with MD5 (fast, unsalted) in shopfront/auth/passwords.py | Security-critical authentication code has no tests (shopfront/auth/middleware.py, shopfront/auth/passwords.py)
- **Affected component:** authentication
- **Why it matters:** Independent agents verified 4 linked problems across 2 dimensions; together they are worse than each alone (multiplier 1.3).
- **Proposed fix:**

1. Add regression tests for shopfront/auth/middleware.py, shopfront/auth/passwords.py before merging (valid/expired/tampered tokens, wrong algorithm).
2. Hardcoded fallback value for secret SHOPFRONT_SECRET in shopfront/auth/middleware.py: Remove the literal fallback and fail fast at start-up when the secret is not configured. Rotating the existing secret is a human action outside Skopeo's authority.
3. JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py: Pass algorithms=['HS256'] (or the single algorithm you issue) to every jwt.decode call; add tests that tokens with other algorithms are rejected.
4. Passwords hashed with MD5 (fast, unsalted) in shopfront/auth/passwords.py: Hash passwords with argon2id (argon2-cffi) or bcrypt; re-hash on next successful login and expire legacy hashes.
5. Re-run Skopeo to confirm the compound risk is closed.

- **Estimated risk:** {'priority': 'P1', 'score': 66.9} · **Verification:** verified · **Difficulty:** medium
- **Expected benefit:** Closes a P1 risk (score 66.9) and makes the upgrade path safe.

### [P2] PyJWT 1.7.1 is a major version behind latest 2.15.1, released 7 year(s) ago
- **Problem:** PyJWT is pinned at 1.7.1; the registry's latest release is 2.15.1 (2026-09-28T18:40:41.429003Z). A major-version gap usually means accumulated fixes and API changes.
- **Affected component:** requirements.txt
- **Why it matters:** Verified dependency risk with priority P2.
- **Proposed fix:**

Plan an upgrade of PyJWT to 2.15.1.

- **Estimated risk:** {'priority': 'P2', 'score': 50.2} · **Verification:** verified · **Difficulty:** medium
- **Expected benefit:** Reduces a P2 risk (score 50.2).

### [P2] Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED
- **Problem:** `conn.execute().fetchall` at line 10 runs once per iteration of the loop at line 9. Cost grows linearly with the number of iterations. Not measured yet.
- **Affected component:** services
- **Why it matters:** Query count grows linearly with rows, so latency and database load grow with every new order.
- **Proposed fix:**

Load items for all orders in one query (WHERE order_id IN (...) or a JOIN) and group them in memory.

- **Estimated risk:** {'priority': 'P2', 'score': 36.7} · **Verification:** verified · **Difficulty:** low
- **Expected benefit:** Constant query count per request instead of the measured query count grows linearly with rows (51 queries at n=50 -> 2001 at n=2000); N+1 confirmed.

### [P3] GPL-3.0 licensed source in a MIT project (shopfront/vendor/fastcsv.py)
- **Problem:** GPL-3.0 (strong copyleft) code inside a MIT project forces the combined work to be distributed under GPL-3.0. Files: shopfront/vendor/fastcsv.py:1
- **Affected component:** legal, vendored
- **Why it matters:** Strong-copyleft code inside a permissive project changes the distribution terms of the combined work.
- **Proposed fix:**

Replace the vendored copyleft code with a permissively licensed or stdlib implementation (e.g. Python's csv module).

- **Estimated risk:** {'priority': 'P3', 'score': 34.7} · **Verification:** verified · **Difficulty:** low
- **Expected benefit:** Removes copyleft obligations from distribution.

### [P3] License metadata mismatch: pyproject.toml declares Apache-2.0 but LICENSE is MIT
- **Problem:** Package metadata (pyproject.toml) says 'Apache-2.0' while the license text in LICENSE is MIT. Downstream users and scanners receive contradictory terms.
- **Affected component:** legal, packaging
- **Why it matters:** Contradictory license metadata creates legal ambiguity for every downstream user and fails compliance scanners.
- **Proposed fix:**

Decide the intended license and make the LICENSE file and package metadata identical.

- **Estimated risk:** {'priority': 'P3', 'score': 31.5} · **Verification:** verified · **Difficulty:** low
- **Expected benefit:** Clear, consistent licensing.

### [P3] Overall line coverage is 20%
- **Problem:** The executed suite covers 37 of 181 statements in shopfront.
- **Affected component:** repository
- **Why it matters:** Verified testing risk with priority P3.
- **Proposed fix:**

Raise coverage on critical modules first.

- **Estimated risk:** {'priority': 'P3', 'score': 30.3} · **Verification:** verified · **Difficulty:** medium
- **Expected benefit:** Reduces a P3 risk (score 30.3).

### [P3] build_sales_report() has cyclomatic complexity 17 (shopfront/services/reports.py)
- **Problem:** build_sales_report spans 43 lines with complexity 17 and nesting depth 5. Threshold: >10 medium, >20 high. Complex functions are harder to test and review.
- **Affected component:** services
- **Why it matters:** High cyclomatic complexity correlates with defects and makes changes risky to review and test.
- **Proposed fix:**

Extract filtering and per-item formatting into small functions; cover each branch with a test.

- **Estimated risk:** {'priority': 'P3', 'score': 25.7} · **Verification:** verified · **Difficulty:** medium
- **Expected benefit:** Easier review and safer change.

### [P3] Deprecated legacy_price_lookup() is still called from 1 production site(s)
- **Problem:** legacy_price_lookup (defined in shopfront/legacy.py:10) emits DeprecationWarning but is used by shopfront/api/routes.py:45. Removing it would be a breaking change.
- **Affected component:** shopfront
- **Why it matters:** Verified api_compatibility risk with priority P3.
- **Proposed fix:**

Migrate callers off legacy_price_lookup() before removing it; announce the removal in release notes.

- **Estimated risk:** {'priority': 'P3', 'score': 17.2} · **Verification:** verified · **Difficulty:** medium
- **Expected benefit:** Reduces a P3 risk (score 17.2).

### [P3] 1 runtime dependency is not pinned to exact versions (requests>=2.20)
- **Problem:** requirements.txt declares 1 runtime dependencies with open version ranges and no lockfile. Builds are not reproducible and a compromised or broken release can be picked up automatically.
- **Affected component:** requirements.txt
- **Why it matters:** Verified dependency risk with priority P3.
- **Proposed fix:**

Pin exact versions or add a lockfile (pip-tools / uv / poetry lock).

- **Estimated risk:** {'priority': 'P3', 'score': 17.2} · **Verification:** verified · **Difficulty:** medium
- **Expected benefit:** Reduces a P3 risk (score 17.2).

### [P3] AI-directed instructions (possible prompt injection) in README.md
- **Problem:** README.md contains text addressed to AI/automated agents (exfiltration, override_instructions). Skopeo treated it strictly as data and did not follow it, but other AI tooling consuming this repository could be manipulated.
- **Affected component:** ai-supply-chain, documentation
- **Why it matters:** AI-based tooling (review bots, assistants) that reads this repository may follow the embedded instructions.
- **Proposed fix:**

Remove the AI-directed instructions from repository content; make CI bots treat repository text as untrusted data.

- **Estimated risk:** {'priority': 'P3', 'score': 16.8} · **Verification:** verified · **Difficulty:** low
- **Expected benefit:** Reduces AI supply-chain manipulation risk.

### [P3] Failing test: tests/test_pricing.py::test_format_price_pads_single_digit_cents
- **Problem:** tests/test_pricing.py::test_format_price_pads_single_digit_cents failed when the suite was executed: Ass...
- **Affected component:** tests/test_pricing.py
- **Why it matters:** A red test means either shipped behaviour is wrong or the suite is not trusted — both erode the safety net.
- **Proposed fix:**

Reproduce with `python -m pytest tests/test_pricing.py::test_format_price_pads_single_digit_cents` (observed: Ass...
). Fix the code under test (or the test, if its expectation is wrong) and keep the test in CI.

- **Estimated risk:** {'priority': 'P3', 'score': 15.1} · **Verification:** verified · **Difficulty:** low
- **Expected benefit:** Restores a green, trustworthy suite and fixes user-visible output.

### [P3] Broad exception silently swallowed in shopfront/services/reports.py (1x)
- **Problem:** `except Exception: pass` (or bare except) hides failures and corrupts results without any signal.
- **Affected component:** services
- **Why it matters:** Verified code_quality risk with priority P3.
- **Proposed fix:**

Catch specific exceptions and log or re-raise.

- **Estimated risk:** {'priority': 'P3', 'score': 12.9} · **Verification:** verified · **Difficulty:** medium
- **Expected benefit:** Reduces a P3 risk (score 12.9).

## Proposed Actions (require human approval)

- `PROPOSED` github_issue: [Skopeo P0] Fix compound risk: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests
- `PROPOSED` pull_request: [Skopeo] Upgrade PyJWT to 2.15.1 (draft)
- `PROPOSED` github_issue: [Skopeo P1] Fix compound risk: Concentrated weaknesses in the authentication component (3 security findings, untested)

## Agent Timeline

| # | Time (UTC) | From → To | Event | Message |
| --- | --- | --- | --- | --- |
| 1 | 10:32:53.251 | orchestrator → all_agents | investigation_started | Orchestrator created investigation of examples/vulnerable-demo-repo (main, depth=standard, mode=mock, DRY_RUN=True) |
| 2 | 10:32:56.351 | orchestrator → blackboard | repository_prepared | Repository prepared (demo_fixture) at 5eda3b9ec3: 28 files, primary language Python |
| 3 | 10:32:56.369 | orchestrator → blackboard | agent_message | Repository detected as Python project (19 source files, 3 test files, ecosystems: PyPI, 1 commit(s) of history). |
| 4 | 10:32:56.374 | orchestrator → all_agents | plan_created | Plan created: 8 specialist(s) in parallel — security_agent, dependency_agent, test_reliability_agent, api_compatibility_agent, performance_agent, code_quality_agent, license_agent, maintenance_agent |
| 5 | 10:32:56.393 | security_agent → orchestrator | agent_started | Security Agent started: Find secrets, insecure patterns and prompt-injection content |
| 6 | 10:32:56.403 | security_agent → orchestrator | agent_message | Security Agent plan (full/default): scan for committed secrets, analyse insecure code patterns (AST), scan for prompt-injection content, run Semgrep ruleset if available |
| 7 | 10:32:56.414 | dependency_agent → orchestrator | agent_started | Dependency Health Agent started: Assess dependency health for PyPI |
| 8 | 10:32:56.423 | dependency_agent → orchestrator | agent_message | Dependency Health Agent plan (full/default): detect ecosystems & parse manifests, query vulnerability database, check freshness & maintenance via registry, check version pinning & conflicts |
| 9 | 10:32:56.433 | test_reliability_agent → orchestrator | agent_started | Test Reliability Agent started: Assess test coverage and reliability (execute suite) |
| 10 | 10:32:56.437 | test_reliability_agent → orchestrator | agent_message | Test Reliability Agent plan (full/default): discover test framework & suites, analyse assertion quality & flakiness indicators, map tests to production modules, execute test suite with coverage |
| 11 | 10:32:56.451 | api_compatibility_agent → orchestrator | agent_started | API Compatibility Agent started: Review public API surface, deprecations and breaking changes |
| 12 | 10:32:56.453 | api_compatibility_agent → orchestrator | agent_message | API Compatibility Agent plan (full/default): extract public API surface, find deprecated APIs still in use, compare public API across git history |
| 13 | 10:32:56.467 | performance_agent → orchestrator | agent_started | Performance Agent started: Find performance bottlenecks (static + benchmarks) |
| 14 | 10:32:56.473 | performance_agent → orchestrator | agent_message | Performance Agent plan (full/default): initialise benchmark/profiling harness, detect static performance suspects (AST) |
| 15 | 10:32:56.488 | code_quality_agent → orchestrator | agent_started | Code Quality Agent started: Measure maintainability and code smells |
| 16 | 10:32:56.492 | code_quality_agent → orchestrator | agent_message | Code Quality Agent plan (full/default): compute function metrics (AST), detect silent exception handling, detect duplicated code blocks, review data-access functions |
| 17 | 10:32:56.505 | license_agent → orchestrator | agent_started | License Compliance Agent started: Check license and dependency license compliance |
| 18 | 10:32:56.511 | license_agent → orchestrator | agent_message | License Compliance Agent plan (full/default): identify repository license, check package metadata consistency, scan SPDX headers in source files, check dependency licenses |
| 19 | 10:32:56.525 | maintenance_agent → orchestrator | agent_started | Maintenance Activity Agent started: Assess maintenance activity |
| 20 | 10:32:56.535 | maintenance_agent → orchestrator | agent_message | Maintenance Activity Agent plan (full/default): analyse git history |
| 21 | 10:32:56.561 | dependency_agent → orchestrator | agent_message | Detected ecosystem(s) PyPI; 3 dependencies in requirements.txt |
| 22 | 10:32:56.592 | test_reliability_agent → orchestrator | agent_message | Discovered 3 Python test module(s); frameworks: pytest |
| 23 | 10:32:56.667 | performance_agent → orchestrator | agent_failed | Performance Agent FAILED: ToolUnavailableError: benchmark harness unavailable [controlled fault injection: SKOPEO_FAULT_INJECTION=performance_agent@1] |
| 24 | 10:32:56.673 | security_agent → blackboard | finding_created | HIGH security: Possible credential exposure: AWS access key ID in tests/fixtures/README.md |
| 25 | 10:32:56.691 | code_quality_agent → blackboard | finding_created | MEDIUM code_quality: build_sales_report() has cyclomatic complexity 17 (shopfront/services/reports.py) |
| 26 | 10:32:56.698 | security_agent → blackboard | finding_created | HIGH security: Possible credential exposure: AWS access key ID and AWS secret access key in tests/fixtures/example_credentials.txt |
| 27 | 10:32:56.698 | code_quality_agent → orchestrator | agent_message | Code Quality Agent extended its plan after 'compute function metrics (AST)': LLM maintainability review of most complex functions |
| 28 | 10:32:57.167 | test_reliability_agent → blackboard | finding_created | LOW testing: 1 test(s) in tests/test_orders.py only make weak assertions |
| 29 | 10:32:57.214 | api_compatibility_agent → blackboard | finding_created | LOW api_compatibility: Deprecated legacy_price_lookup() is still called from 1 production site(s) |
| 30 | 10:32:57.228 | code_quality_agent → blackboard | finding_created | LOW code_quality: Broad exception silently swallowed in shopfront/services/reports.py (1x) |
| 31 | 10:32:57.234 | dependency_agent → blackboard | finding_created | CRITICAL dependency: PyJWT 1.7.1 is affected by 11 known vulnerabilities |
| 32 | 10:32:57.242 | maintenance_agent → orchestrator | agent_message | Maintenance analysis limited: 1 commit(s) of history available |
| 33 | 10:32:57.255 | license_agent → blackboard | finding_created | MEDIUM license: License metadata mismatch: pyproject.toml declares Apache-2.0 but LICENSE is MIT |
| 34 | 10:32:57.272 | dependency_agent → orchestrator | investigation_requested | Requests impact analysis: Assess real-world impact of vulnerable PyJWT 1.7.1 (usage, upgrade compatibility, test coverage) |
| 35 | 10:32:57.339 | maintenance_agent → orchestrator | agent_completed | Maintenance Activity Agent completed in 804 ms: 0 finding(s) published, 0 enriched |
| 36 | 10:32:57.380 | security_agent → blackboard | finding_created | MEDIUM security: Hardcoded fallback value for secret SHOPFRONT_SECRET in shopfront/auth/middleware.py |
| 37 | 10:32:57.442 | test_reliability_agent → blackboard | finding_created | HIGH testing: Security-critical authentication code has no tests (shopfront/auth/middleware.py, shopfront/auth/passwords.py) |
| 38 | 10:32:57.464 | license_agent → blackboard | finding_created | HIGH license: GPL-3.0 licensed source in a MIT project (shopfront/vendor/fastcsv.py) |
| 39 | 10:32:57.475 | dependency_agent → blackboard | finding_created | MEDIUM dependency: PyJWT 1.7.1 is a major version behind latest 2.15.1, released 7 year(s) ago |
| 40 | 10:32:57.485 | security_agent → blackboard | finding_created | HIGH security: JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py |
| 41 | 10:32:57.537 | code_quality_agent → blackboard | finding_created | INFO code_quality: Data-access function list_orders_with_items() assessed acceptable for maintainability (shopfront/services/orders.py) |
| 42 | 10:32:57.568 | dependency_agent → blackboard | finding_created | MEDIUM dependency: python-dateutil appears unmaintained (latest release 2+ years ago) |
| 43 | 10:32:57.573 | api_compatibility_agent → orchestrator | agent_completed | API Compatibility Agent completed in 1110 ms: 1 finding(s) published, 0 enriched |
| 44 | 10:32:57.578 | security_agent → blackboard | finding_created | HIGH security: Passwords hashed with MD5 (fast, unsalted) in shopfront/auth/passwords.py |
| 45 | 10:32:57.620 | license_agent → orchestrator | agent_completed | License Compliance Agent completed in 1111 ms: 2 finding(s) published, 0 enriched |
| 46 | 10:32:57.768 | dependency_agent → blackboard | finding_created | LOW dependency: 1 runtime dependency is not pinned to exact versions (requests>=2.20) |
| 47 | 10:32:57.772 | code_quality_agent → blackboard | evidence_added | Maintainability review attached to build_sales_report (policy) |
| 48 | 10:32:57.788 | security_agent → blackboard | finding_created | LOW security: AI-directed instructions (possible prompt injection) in README.md |
| 49 | 10:32:57.796 | dependency_agent → orchestrator | agent_completed | Dependency Health Agent completed in 1373 ms: 4 finding(s) published, 0 enriched |
| 50 | 10:32:57.801 | security_agent → orchestrator | agent_message | Prompt-injection content detected in README.md; handled as untrusted data (no instructions followed) |
| 51 | 10:32:57.814 | code_quality_agent → orchestrator | agent_completed | Code Quality Agent completed in 1324 ms: 3 finding(s) published, 1 enriched |
| 52 | 10:32:58.081 | security_agent → orchestrator | agent_completed | Security Agent completed in 1641 ms: 6 finding(s) published, 0 enriched |
| 53 | 10:33:12.992 | test_reliability_agent → blackboard | tool_executed | test_reliability_agent executed python -B -m coverage run --data-file=<workspace>\82686e93-967b-4cf1-b7e2-5966701b9513\artifacts\.coverage --source=shopfront -m pytest -q -rfE -p |
| 54 | 10:33:13.044 | test_reliability_agent → orchestrator | agent_message | Executed test suite: 1 failed, 6 passed in 0.76s (exit code 1, 14109 ms) |
| 55 | 10:33:13.079 | test_reliability_agent → blackboard | finding_created | MEDIUM testing: Failing test: tests/test_pricing.py::test_format_price_pads_single_digit_cents |
| 56 | 10:33:13.108 | test_reliability_agent → blackboard | evidence_added | Coverage run confirms shopfront/auth/middleware.py at 0% coverage |
| 57 | 10:33:13.129 | test_reliability_agent → blackboard | evidence_added | Coverage run confirms shopfront/auth/passwords.py at 0% coverage |
| 58 | 10:33:13.147 | test_reliability_agent → blackboard | finding_created | MEDIUM testing: Overall line coverage is 20% |
| 59 | 10:33:13.161 | test_reliability_agent → orchestrator | agent_completed | Test Reliability Agent completed in 16725 ms: 4 finding(s) published, 2 enriched |
| 60 | 10:33:13.197 | orchestrator → performance_agent | agent_retry_scheduled | performance_agent FAILED -> RETRYING (attempt 2, strategy 'static_only'): ToolUnavailableError: benchmark harness unavailable [controlled fault injection: SKOPEO_FAULT_INJECTION=performance_agent@1]; retry 2 with strateg |
| 61 | 10:33:13.244 | orchestrator → dependency_agent | request_decided | Accepted request from dependency_agent: assigning security_agent:dependency_usage, api_compatibility_agent:upgrade_compatibility, test_reliability_agent:dependency_coverage |
| 62 | 10:33:13.278 | orchestrator → all_agents | replan | Replanned: +security_agent (dependency_usage), +api_compatibility_agent (upgrade_compatibility), +test_reliability_agent (dependency_coverage); performance follow-up not required (pyjwt is not on a performance-sensitive  |
| 63 | 10:33:13.284 | orchestrator → all_agents | orchestrator_decision | Review round 1: performance_agent failed (ToolUnavailableError); retrying with 'static_only'; 3 follow-up(s) scheduled Next: dispatch. |
| 64 | 10:33:13.323 | performance_agent → orchestrator | agent_started | Performance Agent started: Retry: performance_agent (static_only) (attempt 2, strategy static_only) |
| 65 | 10:33:13.326 | performance_agent → orchestrator | agent_message | Performance Agent plan (full/static_only): detect static performance suspects (AST) |
| 66 | 10:33:13.341 | security_agent → orchestrator | agent_started | Security Agent started: Inspect how pyjwt is used and whether it reaches security-critical code [dependency_usage] |
| 67 | 10:33:13.355 | security_agent → orchestrator | agent_message | Security Agent plan (dependency_usage/default): trace dependency usage & reachability |
| 68 | 10:33:13.358 | api_compatibility_agent → orchestrator | agent_started | API Compatibility Agent started: Check whether upgrading pyjwt 1.7.1 -> 2.14.0 breaks APIs [upgrade_compatibility] |
| 69 | 10:33:13.375 | api_compatibility_agent → orchestrator | agent_message | API Compatibility Agent plan (upgrade_compatibility/default): check upgrade compatibility against migration knowledge base |
| 70 | 10:33:13.383 | test_reliability_agent → orchestrator | agent_started | Test Reliability Agent started: Identify tests covering code that uses pyjwt [dependency_coverage] |
| 71 | 10:33:13.391 | test_reliability_agent → orchestrator | agent_message | Test Reliability Agent plan (dependency_coverage/default): map tests to code using the dependency |
| 72 | 10:33:13.637 | performance_agent → blackboard | finding_created | MEDIUM performance: Blocking network call inside a loop in notify_customers() (shopfront/services/notifications.py) — STATIC SUSPECT |
| 73 | 10:33:13.669 | test_reliability_agent → blackboard | evidence_added | Linked untested authentication code to dependency pyjwt |
| 74 | 10:33:13.677 | api_compatibility_agent → blackboard | finding_created | MEDIUM api_compatibility: Upgrading pyjwt 1.7.1 -> 2.14.0 breaks 2 call site(s) in shopfront/auth/middleware.py |
| 75 | 10:33:13.685 | performance_agent → blackboard | finding_created | MEDIUM performance: Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — STATIC SUSPECT |
| 76 | 10:33:13.694 | security_agent → blackboard | finding_created | HIGH security: Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py) |
| 77 | 10:33:13.694 | test_reliability_agent → orchestrator | agent_message | Code using pyjwt (shopfront/auth/middleware.py) is not exercised by any test — an upgrade of pyjwt would ship without regression tests (evidence added to existing finding) |
| 78 | 10:33:13.704 | api_compatibility_agent → orchestrator | agent_message | Upgrade of pyjwt is not drop-in: 2 call site(s) need changes |
| 79 | 10:33:13.712 | security_agent → orchestrator | agent_message | Confirmed pyjwt is used by authentication code (shopfront/auth/middleware.py); reachable from entrypoints: yes |
| 80 | 10:33:13.723 | performance_agent → orchestrator | agent_completed | Performance Agent completed in 395 ms: 2 finding(s) published, 0 enriched |
| 81 | 10:33:13.738 | test_reliability_agent → orchestrator | agent_completed | Test Reliability Agent completed in 355 ms: 0 finding(s) published, 1 enriched |
| 82 | 10:33:13.750 | api_compatibility_agent → orchestrator | agent_completed | API Compatibility Agent completed in 393 ms: 1 finding(s) published, 0 enriched |
| 83 | 10:33:13.761 | security_agent → orchestrator | agent_completed | Security Agent completed in 418 ms: 1 finding(s) published, 0 enriched |
| 84 | 10:33:13.784 | orchestrator → all_agents | orchestrator_decision | Review round 2: 4 task(s) completed, 4 new finding(s) Next: correlate. |
| 85 | 10:33:13.834 | correlation_agent → orchestrator | agent_started | Correlation Agent started: Correlate findings across agents |
| 86 | 10:33:13.973 | correlation_agent → orchestrator | agent_message | Correlation pass over 24 findings from 7 agents: 5 candidate relationship(s) |
| 87 | 10:33:14.171 | correlation_agent → blackboard | correlation_created | Contradiction: Agents disagree about list_orders_with_items() |
| 88 | 10:33:14.214 | correlation_agent → verification_agent | agent_message | Contradiction requires adjudication: Agents disagree about list_orders_with_items(). Disagreement on py:shopfront/services/orders.py::list_orders_with_items: performance_agent flags a potential issue ('Database query exe |
| 89 | 10:33:14.392 | correlation_agent → blackboard | correlation_created | Shared Root Cause: Shared root cause: stale pin of pyjwt 1.7.1 |
| 90 | 10:33:14.628 | correlation_agent → blackboard | correlation_created | Compound Risk: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests |
| 91 | 10:33:14.905 | correlation_agent → blackboard | correlation_created | Compound Risk: Concentrated weaknesses in the authentication component (3 security findings, untested) |
| 92 | 10:33:15.149 | correlation_agent → blackboard | correlation_created | Dependency: Unpinned requests is used on a hot path |
| 93 | 10:33:15.176 | correlation_agent → orchestrator | agent_completed | Correlation Agent completed in 1346 ms: 5 new and 0 updated correlation(s) from 5 candidates |
| 94 | 10:33:15.199 | orchestrator → all_agents | orchestrator_decision | Review round 2: phase complete Next: verify. |
| 95 | 10:33:15.226 | verification_agent → orchestrator | agent_started | Verification / Red-Team Agent started: Red-team verification round 1 |
| 96 | 10:33:15.258 | verification_agent → orchestrator | verification_started | Red-team round 1: challenging 24 finding(s) and pending correlations |
| 97 | 10:33:15.398 | verification_agent → dependency_agent | challenge | Challenge to dependency_agent: Is pyjwt actually imported and reachable, and is the critical severity backed by the advisory data? |
| 98 | 10:33:15.442 | verification_agent → dependency_agent | finding_verified | VERIFIED: PyJWT 1.7.1 is affected by 11 known vulnerabilities — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. `jwt` imported by shopfront/a |
| 99 | 10:33:15.624 | verification_agent → security_agent | challenge | Challenge to security_agent: Is this a live credential, or a documented dummy value in a fixture? Is it used by production code? |
| 100 | 10:33:15.675 | verification_agent → security_agent | finding_rejected | REJECTED: Possible credential exposure: AWS access key ID in tests/fixtures/README.md — The detected string occurs in tests/fixtures/README.md and matches a documented placeholder pattern. AKIA************MPLE: value mat |
| 101 | 10:33:15.854 | verification_agent → security_agent | challenge | Challenge to security_agent: Is this a live credential, or a documented dummy value in a fixture? Is it used by production code? |
| 102 | 10:33:15.905 | verification_agent → security_agent | finding_rejected | REJECTED: Possible credential exposure: AWS access key ID and AWS secret access key in tests/fixtures/example_credentials.txt — The detected string occurs in tests/fixtures/example_credentials.txt and matches a documente |
| 103 | 10:33:16.325 | verification_agent → test_reliability_agent | challenge | Challenge to test_reliability_agent: Do tests really not exercise this code? Re-derive the mapping independently. |
| 104 | 10:33:16.482 | verification_agent → test_reliability_agent | finding_verified | VERIFIED: Security-critical authentication code has no tests (shopfront/auth/middleware.py, shopfront/auth/passwords.py) — Verified: re-hashed 5 referenced line range(s); all match the repository. evidence captured at th |
| 105 | 10:33:16.691 | verification_agent → license_agent | challenge | Challenge to license_agent: Is the evidence real, current and reachable, and is the severity justified? |
| 106 | 10:33:16.758 | verification_agent → license_agent | finding_verified | VERIFIED: GPL-3.0 licensed source in a MIT project (shopfront/vendor/fastcsv.py) — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. copyleft-l |
| 107 | 10:33:16.938 | verification_agent → security_agent | challenge | Challenge to security_agent: Is the evidence real, current and reachable, and is the severity justified? |
| 108 | 10:33:16.977 | verification_agent → security_agent | finding_verified | VERIFIED: JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9 |
| 109 | 10:33:17.158 | verification_agent → security_agent | challenge | Challenge to security_agent: Is the evidence real, current and reachable, and is the severity justified? |
| 110 | 10:33:17.197 | verification_agent → security_agent | finding_verified | VERIFIED: Passwords hashed with MD5 (fast, unsalted) in shopfront/auth/passwords.py — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. importe |
| 111 | 10:33:17.376 | verification_agent → security_agent | challenge | Challenge to security_agent: Is the evidence real, current and reachable, and is the severity justified? |
| 112 | 10:33:17.408 | verification_agent → security_agent | finding_verified | VERIFIED: Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py) — Verified: re-hashed 3 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3 |
| 113 | 10:33:17.585 | verification_agent → code_quality_agent | challenge | Challenge to code_quality_agent: Is the evidence real, current and reachable, and is the severity justified? |
| 114 | 10:33:17.709 | verification_agent → code_quality_agent | finding_verified | VERIFIED: build_sales_report() has cyclomatic complexity 17 (shopfront/services/reports.py) — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. |
| 115 | 10:33:17.918 | verification_agent → license_agent | challenge | Challenge to license_agent: Is the evidence real, current and reachable, and is the severity justified? |
| 116 | 10:33:17.948 | verification_agent → license_agent | finding_verified | VERIFIED: License metadata mismatch: pyproject.toml declares Apache-2.0 but LICENSE is MIT — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3.  |
| 117 | 10:33:18.127 | verification_agent → security_agent | challenge | Challenge to security_agent: Is the evidence real, current and reachable, and is the severity justified? |
| 118 | 10:33:18.159 | verification_agent → security_agent | finding_verified | VERIFIED: Hardcoded fallback value for secret SHOPFRONT_SECRET in shopfront/auth/middleware.py — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9e |
| 119 | 10:33:18.338 | verification_agent → dependency_agent | challenge | Challenge to dependency_agent: Is the evidence real, current and reachable, and is the severity justified? |
| 120 | 10:33:18.384 | verification_agent → dependency_agent | finding_verified | VERIFIED: PyJWT 1.7.1 is a major version behind latest 2.15.1, released 7 year(s) ago — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. `jwt` |
| 121 | 10:33:18.562 | verification_agent → dependency_agent | challenge | Challenge to dependency_agent: Is the evidence real, current and reachable, and is the severity justified? |
| 122 | 10:33:18.601 | verification_agent → dependency_agent | finding_verified | VERIFIED: python-dateutil appears unmaintained (latest release 2+ years ago) — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. Severity downg |
| 123 | 10:33:18.777 | verification_agent → test_reliability_agent | challenge | Challenge to test_reliability_agent: Does the failure reproduce on an independent re-run? |
| 124 | 10:33:18.788 | verification_agent → test_reliability_agent | challenge | Requested reproduction: re-running tests/test_pricing.py::test_format_price_pads_single_digit_cents |
| 125 | 10:33:27.228 | verification_agent → blackboard | tool_executed | verification_agent executed python -B -m pytest -q -p no:cacheprovider --no-header --color=no tests/test_pricing.py::test_format_price_pads_single_digit_cents |
| 126 | 10:33:27.311 | verification_agent → test_reliability_agent | finding_verified | VERIFIED: Failing test: tests/test_pricing.py::test_format_price_pads_single_digit_cents — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. re |
| 127 | 10:33:27.454 | verification_agent → test_reliability_agent | challenge | Challenge to test_reliability_agent: Do tests really not exercise this code? Re-derive the mapping independently. |
| 128 | 10:33:27.491 | verification_agent → test_reliability_agent | finding_verified | VERIFIED: Overall line coverage is 20% — Verified: evidence captured at the analysed commit 5eda3b9ec3. test-quality claim re-derived from the test AST. |
| 129 | 10:33:27.625 | verification_agent → performance_agent | challenge | Challenge to performance_agent: Has this been measured, or is it a theoretical static suspect? Is the code on a reachable path? |
| 130 | 10:33:27.658 | verification_agent → performance_agent | verification_completed | NEEDS MORE EVIDENCE: Blocking network call inside a loop in notify_customers() (shopfront/services/notifications.py) — STATIC SUSPECT — Needs more evidence: STATIC SUSPECT only — no benchmark has measured the impact; a m |
| 131 | 10:33:27.667 | verification_agent → orchestrator | investigation_requested | Requests benchmark: Run a benchmark for notify_customers() to measure the suspected network in loop |
| 132 | 10:33:27.808 | verification_agent → api_compatibility_agent | challenge | Challenge to api_compatibility_agent: Is the evidence real, current and reachable, and is the severity justified? |
| 133 | 10:33:27.839 | verification_agent → api_compatibility_agent | finding_verified | VERIFIED: Upgrading pyjwt 1.7.1 -> 2.14.0 breaks 2 call site(s) in shopfront/auth/middleware.py — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9 |
| 134 | 10:33:27.970 | verification_agent → performance_agent | challenge | Challenge to performance_agent: Has this been measured, or is it a theoretical static suspect? Is the code on a reachable path? |
| 135 | 10:33:28.007 | verification_agent → performance_agent | verification_completed | NEEDS MORE EVIDENCE: Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — STATIC SUSPECT — Needs more evidence: STATIC SUSPECT only — no benchmark has measured  |
| 136 | 10:33:28.020 | verification_agent → orchestrator | investigation_requested | Requests benchmark: Run a benchmark for list_orders_with_items() to measure the suspected n plus one |
| 137 | 10:33:28.199 | verification_agent → api_compatibility_agent | challenge | Challenge to api_compatibility_agent: Is the evidence real, current and reachable, and is the severity justified? |
| 138 | 10:33:28.234 | verification_agent → api_compatibility_agent | finding_verified | VERIFIED: Deprecated legacy_price_lookup() is still called from 1 production site(s) — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. shopfr |
| 139 | 10:33:28.410 | verification_agent → test_reliability_agent | challenge | Challenge to test_reliability_agent: Do tests really not exercise this code? Re-derive the mapping independently. |
| 140 | 10:33:28.507 | verification_agent → test_reliability_agent | finding_verified | VERIFIED: 1 test(s) in tests/test_orders.py only make weak assertions — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. test-quality claim re |
| 141 | 10:33:28.707 | verification_agent → code_quality_agent | challenge | Challenge to code_quality_agent: Is the evidence real, current and reachable, and is the severity justified? |
| 142 | 10:33:28.743 | verification_agent → code_quality_agent | finding_verified | VERIFIED: Broad exception silently swallowed in shopfront/services/reports.py (1x) — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. |
| 143 | 10:33:28.921 | verification_agent → dependency_agent | challenge | Challenge to dependency_agent: Is the evidence real, current and reachable, and is the severity justified? |
| 144 | 10:33:28.956 | verification_agent → dependency_agent | finding_verified | VERIFIED: 1 runtime dependency is not pinned to exact versions (requests>=2.20) — Verified: re-hashed 1 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. derived fro |
| 145 | 10:33:29.092 | verification_agent → security_agent | challenge | Challenge to security_agent: Is the evidence real, current and reachable, and is the severity justified? |
| 146 | 10:33:29.126 | verification_agent → security_agent | finding_verified | VERIFIED: AI-directed instructions (possible prompt injection) in README.md — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence captured at the analysed commit 5eda3b9ec3. affected files  |
| 147 | 10:33:29.315 | verification_agent → code_quality_agent | challenge | Challenge to code_quality_agent: Does measured evidence contradict this 'acceptable' assessment? |
| 148 | 10:33:29.358 | verification_agent → code_quality_agent | verification_completed | NEEDS MORE EVIDENCE: Data-access function list_orders_with_items() assessed acceptable for maintainability (shopfront/services/orders.py) — Needs more evidence: contested by performance_agent; neither side measured. |
| 149 | 10:33:29.371 | verification_agent → orchestrator | investigation_requested | Requests benchmark: Run a benchmark for list_orders_with_items() to measure the suspected n plus one |
| 150 | 10:33:29.523 | verification_agent → orchestrator | correlation_updated | Correlation needs more evidence: Agents disagree about list_orders_with_items() — Contradiction unresolved: performance_agent=needs_more_evidence, code_quality_agent=needs_more_evidence |
| 151 | 10:33:29.667 | verification_agent → orchestrator | correlation_updated | Correlation verified: Shared root cause: stale pin of pyjwt 1.7.1 — 2 of 2 member findings verified |
| 152 | 10:33:29.874 | verification_agent → orchestrator | correlation_updated | Correlation verified: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests — 4 of 4 member findings verified |
| 153 | 10:33:30.066 | verification_agent → orchestrator | correlation_updated | Correlation verified: Concentrated weaknesses in the authentication component (3 security findings, untested) — 4 of 4 member findings verified |
| 154 | 10:33:30.252 | verification_agent → orchestrator | correlation_updated | Correlation needs more evidence: Unpinned requests is used on a hot path — awaiting verification of 1 member(s) |
| 155 | 10:33:30.267 | verification_agent → orchestrator | agent_completed | Verification / Red-Team Agent completed in 15043 ms: Round 1: 3 needs_more_evidence, 2 rejected, 19 verified |
| 156 | 10:33:30.316 | orchestrator → verification_agent | request_decided | Accepted request from verification_agent: assigning performance_agent:benchmark |
| 157 | 10:33:30.323 | orchestrator → verification_agent | request_decided | Accepted request from verification_agent: assigning performance_agent:benchmark |
| 158 | 10:33:30.329 | orchestrator → verification_agent | request_decided | Accepted request from verification_agent: assigning performance_agent:benchmark |
| 159 | 10:33:30.341 | orchestrator → all_agents | replan | Replanned: +performance_agent (benchmark), +performance_agent (benchmark) |
| 160 | 10:33:30.347 | orchestrator → all_agents | orchestrator_decision | Review round 2: phase complete; 3 follow-up(s) scheduled Next: dispatch. |
| 161 | 10:33:30.364 | performance_agent → orchestrator | agent_started | Performance Agent started: Run a benchmark for notify_customers() to measure the suspected network in loop [benchmark] |
| 162 | 10:33:30.372 | performance_agent → orchestrator | agent_message | Performance Agent plan (benchmark/default): run benchmarks for requested suspects |
| 163 | 10:33:30.388 | performance_agent → orchestrator | agent_started | Performance Agent started: Run a benchmark for list_orders_with_items() to measure the suspected n plus one [benchmark] |
| 164 | 10:33:30.392 | performance_agent → orchestrator | agent_message | Performance Agent plan (benchmark/default): run benchmarks for requested suspects |
| 165 | 10:33:30.505 | performance_agent → verification_agent | agent_message | INSUFFICIENT EVIDENCE: no benchmark harness exercises notify_customers() in shopfront/services/notifications.py; finding stays a static suspect |
| 166 | 10:33:30.564 | performance_agent → orchestrator | agent_completed | Performance Agent completed in 189 ms: 0 finding(s) published, 0 enriched |
| 167 | 10:33:32.889 | performance_agent → blackboard | tool_executed | performance_agent executed python -B benchmarks/bench_orders.py --json |
| 168 | 10:33:32.961 | performance_agent → blackboard | evidence_added | Benchmark benchmarks/bench_orders.py: query count grows linearly with rows (51 queries at n=50 -> 2001 at n=2000); N+1 confirmed |
| 169 | 10:33:32.977 | performance_agent → verification_agent | agent_message | Benchmark for list_orders_with_items(): query count grows linearly with rows (51 queries at n=50 -> 2001 at n=2000); N+1 confirmed |
| 170 | 10:33:32.987 | performance_agent → orchestrator | agent_completed | Performance Agent completed in 2597 ms: 0 finding(s) published, 1 enriched |
| 171 | 10:33:33.011 | orchestrator → all_agents | orchestrator_decision | Review round 3: 2 task(s) completed, 0 new finding(s) Next: correlate. |
| 172 | 10:33:33.045 | correlation_agent → orchestrator | agent_started | Correlation Agent started: Correlate findings across agents |
| 173 | 10:33:33.187 | correlation_agent → orchestrator | agent_message | Correlation pass over 22 findings from 7 agents: 5 candidate relationship(s) |
| 174 | 10:33:33.378 | correlation_agent → blackboard | correlation_updated | Re-assessed contradiction: Agents disagree about list_orders_with_items() |
| 175 | 10:33:34.132 | correlation_agent → orchestrator | agent_completed | Correlation Agent completed in 1088 ms: 0 new and 1 updated correlation(s) from 5 candidates |
| 176 | 10:33:34.154 | orchestrator → all_agents | orchestrator_decision | Review round 3: phase complete Next: verify. |
| 177 | 10:33:34.182 | verification_agent → orchestrator | agent_started | Verification / Red-Team Agent started: Red-team verification round 2 |
| 178 | 10:33:34.220 | verification_agent → orchestrator | verification_started | Red-team round 2: challenging 2 finding(s) and pending correlations |
| 179 | 10:33:34.361 | verification_agent → performance_agent | challenge | Challenge to performance_agent: Has this been measured, or is it a theoretical static suspect? Is the code on a reachable path? |
| 180 | 10:33:34.402 | verification_agent → performance_agent | finding_verified | VERIFIED: Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED — Verified: re-hashed 2 referenced line range(s); all match the repository. evidence cap |
| 181 | 10:33:34.543 | verification_agent → code_quality_agent | challenge | Challenge to code_quality_agent: Does measured evidence contradict this 'acceptable' assessment? |
| 182 | 10:33:34.579 | verification_agent → code_quality_agent | finding_rejected | REJECTED: Data-access function list_orders_with_items() assessed acceptable for maintainability (shopfront/services/orders.py) — Rejected: measured evidence from performance_agent contradicts this assessment (query count |
| 183 | 10:33:34.785 | verification_agent → orchestrator | correlation_updated | Correlation verified: Agents disagree about list_orders_with_items() — Resolved in favour of performance_agent: Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.p |
| 184 | 10:33:34.926 | verification_agent → orchestrator | correlation_updated | Correlation needs more evidence: Unpinned requests is used on a hot path — awaiting verification of 1 member(s) |
| 185 | 10:33:34.938 | verification_agent → orchestrator | agent_completed | Verification / Red-Team Agent completed in 763 ms: Round 2: 1 rejected, 1 verified |
| 186 | 10:33:34.959 | orchestrator → all_agents | orchestrator_decision | Review round 3: phase complete Next: assess. |
| 187 | 10:33:34.983 | risk_agent → orchestrator | agent_started | Risk Assessment Agent started: Assess and prioritise verified risks |
| 188 | 10:33:35.176 | risk_agent → recommendation_agent | risk_assessed | P3 (score 25.7): build_sales_report() has cyclomatic complexity 17 (shopfront/services/reports.py) |
| 189 | 10:33:35.187 | risk_agent → recommendation_agent | risk_assessed | P3 (score 17.2): Deprecated legacy_price_lookup() is still called from 1 production site(s) |
| 190 | 10:33:35.215 | risk_agent → recommendation_agent | risk_assessed | P4 (score 5.5): 1 test(s) in tests/test_orders.py only make weak assertions |
| 191 | 10:33:35.237 | risk_agent → recommendation_agent | risk_assessed | P3 (score 12.9): Broad exception silently swallowed in shopfront/services/reports.py (1x) |
| 192 | 10:33:35.255 | risk_agent → recommendation_agent | risk_assessed | P0 (score 82.5): PyJWT 1.7.1 is affected by 11 known vulnerabilities |
| 193 | 10:33:35.268 | risk_agent → recommendation_agent | risk_assessed | P3 (score 31.5): License metadata mismatch: pyproject.toml declares Apache-2.0 but LICENSE is MIT |
| 194 | 10:33:35.291 | risk_agent → recommendation_agent | risk_assessed | P2 (score 48.5): Hardcoded fallback value for secret SHOPFRONT_SECRET in shopfront/auth/middleware.py |
| 195 | 10:33:35.316 | risk_agent → recommendation_agent | risk_assessed | P2 (score 55.8): Security-critical authentication code has no tests (shopfront/auth/middleware.py, shopfront/auth/passwords.py) |
| 196 | 10:33:35.335 | risk_agent → recommendation_agent | risk_assessed | P3 (score 34.7): GPL-3.0 licensed source in a MIT project (shopfront/vendor/fastcsv.py) |
| 197 | 10:33:35.347 | risk_agent → recommendation_agent | risk_assessed | P2 (score 50.2): PyJWT 1.7.1 is a major version behind latest 2.15.1, released 7 year(s) ago |
| 198 | 10:33:35.357 | risk_agent → recommendation_agent | risk_assessed | P1 (score 63.0): JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py |
| 199 | 10:33:35.377 | risk_agent → recommendation_agent | risk_assessed | P4 (score 8.3): python-dateutil appears unmaintained (latest release 2+ years ago) |
| 200 | 10:33:35.391 | risk_agent → recommendation_agent | risk_assessed | P1 (score 63.0): Passwords hashed with MD5 (fast, unsalted) in shopfront/auth/passwords.py |
| 201 | 10:33:35.400 | risk_agent → recommendation_agent | risk_assessed | P3 (score 17.2): 1 runtime dependency is not pinned to exact versions (requests>=2.20) |
| 202 | 10:33:35.408 | risk_agent → recommendation_agent | risk_assessed | P3 (score 16.8): AI-directed instructions (possible prompt injection) in README.md |
| 203 | 10:33:35.416 | risk_agent → recommendation_agent | risk_assessed | P3 (score 15.1): Failing test: tests/test_pricing.py::test_format_price_pads_single_digit_cents |
| 204 | 10:33:35.429 | risk_agent → recommendation_agent | risk_assessed | P3 (score 30.3): Overall line coverage is 20% |
| 205 | 10:33:35.436 | risk_agent → recommendation_agent | risk_assessed | P2 (score 42.0): Upgrading pyjwt 1.7.1 -> 2.14.0 breaks 2 call site(s) in shopfront/auth/middleware.py |
| 206 | 10:33:35.445 | risk_agent → recommendation_agent | risk_assessed | P1 (score 72.9): Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py) |
| 207 | 10:33:35.458 | risk_agent → recommendation_agent | risk_assessed | P2 (score 36.7): Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED |
| 208 | 10:33:35.631 | risk_agent → recommendation_agent | risk_assessed | P0 (score 94.5) compound: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests |
| 209 | 10:33:35.665 | risk_agent → recommendation_agent | risk_assessed | P1 (score 66.9) compound: Concentrated weaknesses in the authentication component (3 security findings, untested) |
| 210 | 10:33:35.678 | risk_agent → orchestrator | agent_message | Risk assessment: 22 verified risk(s); overall 97.8 (critical); 3 finding(s) excluded |
| 211 | 10:33:35.689 | risk_agent → orchestrator | agent_completed | Risk Assessment Agent completed in 706 ms: 22 risks scored; overall 97.8 (critical) |
| 212 | 10:33:35.706 | recommendation_agent → orchestrator | agent_started | Recommendation Agent started: Generate remediation recommendations |
| 213 | 10:33:35.853 | recommendation_agent → human | recommendation_created | P0 recommendation: Fix compound risk: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests |
| 214 | 10:33:35.862 | recommendation_agent → human | github_action_proposed | ACTION PROPOSED: GitHub issue '[Skopeo P0] Fix compound risk: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests' |
| 215 | 10:33:35.877 | recommendation_agent → human | github_action_proposed | ACTION PROPOSED: draft PR '[Skopeo] Upgrade PyJWT to 2.15.1 (draft)' |
| 216 | 10:33:36.058 | recommendation_agent → human | recommendation_created | P1 recommendation: Fix compound risk: Concentrated weaknesses in the authentication component (3 security findings, untested) |
| 217 | 10:33:36.070 | recommendation_agent → human | github_action_proposed | ACTION PROPOSED: GitHub issue '[Skopeo P1] Fix compound risk: Concentrated weaknesses in the authentication component (3 security findings, untested)' |
| 218 | 10:33:36.855 | recommendation_agent → human | recommendation_created | P2 recommendation: PyJWT 1.7.1 is a major version behind latest 2.15.1, released 7 year(s) ago |
| 219 | 10:33:37.233 | recommendation_agent → human | recommendation_created | P2 recommendation: Database query executed inside a loop (N+1 pattern) in list_orders_with_items() (shopfront/services/orders.py) — MEASURED |
| 220 | 10:33:37.410 | recommendation_agent → human | recommendation_created | P3 recommendation: GPL-3.0 licensed source in a MIT project (shopfront/vendor/fastcsv.py) |
| 221 | 10:33:37.587 | recommendation_agent → human | recommendation_created | P3 recommendation: License metadata mismatch: pyproject.toml declares Apache-2.0 but LICENSE is MIT |
| 222 | 10:33:37.766 | recommendation_agent → human | recommendation_created | P3 recommendation: Overall line coverage is 20% |
| 223 | 10:33:37.948 | recommendation_agent → human | recommendation_created | P3 recommendation: build_sales_report() has cyclomatic complexity 17 (shopfront/services/reports.py) |
| 224 | 10:33:38.136 | recommendation_agent → human | recommendation_created | P3 recommendation: Deprecated legacy_price_lookup() is still called from 1 production site(s) |
| 225 | 10:33:38.275 | recommendation_agent → human | recommendation_created | P3 recommendation: 1 runtime dependency is not pinned to exact versions (requests>=2.20) |
| 226 | 10:33:38.451 | recommendation_agent → human | recommendation_created | P3 recommendation: AI-directed instructions (possible prompt injection) in README.md |
| 227 | 10:33:38.661 | recommendation_agent → human | recommendation_created | P3 recommendation: Failing test: tests/test_pricing.py::test_format_price_pads_single_digit_cents |
| 228 | 10:33:38.914 | recommendation_agent → human | recommendation_created | P3 recommendation: Broad exception silently swallowed in shopfront/services/reports.py (1x) |
| 229 | 10:33:39.006 | recommendation_agent → orchestrator | agent_completed | Recommendation Agent completed in 3298 ms: 13 recommendation(s) generated |
| 230 | 10:33:39.013 | orchestrator → human | human_approval_required | Human approval required before '[Skopeo P0] Fix compound risk: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests' (github_issue). Status: ACTION PROPOSED (DRY_RUN |
| 231 | 10:33:39.021 | orchestrator → human | human_approval_required | Human approval required before '[Skopeo] Upgrade PyJWT to 2.15.1 (draft)' (pull_request). Status: ACTION PROPOSED (DRY_RUN). |
| 232 | 10:33:39.029 | orchestrator → human | human_approval_required | Human approval required before '[Skopeo P1] Fix compound risk: Concentrated weaknesses in the authentication component (3 security findings, untested)' (github_issue). Status: ACTION PROPOSED (DRY_RUN). |
| 233 | 10:33:39.167 | orchestrator → human | investigation_completed | Investigation COMPLETED_WITH_LIMITATIONS: 20 verified, 3 rejected, 1 insufficient evidence; overall risk 97.8 (critical); partial coverage: security_agent, dependency_agent, api_compatibility_agent, maintenance_agent, pe |

_Generated by Skopeo from persisted execution events — nothing in this report is synthesised._