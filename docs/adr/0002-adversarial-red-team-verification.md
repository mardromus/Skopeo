# ADR-0002: Adversarial Red-Team Verification

## Status
Accepted

## Context
LLM-based code analysis and automated scanning suffer from high false-positive rates and hallucinations. Common failure modes include:
1. Identifying sample API keys or test fixtures (e.g., in `tests/fixtures/`) as critical production secrets.
2. Flagging deprecated function calls without verifying whether the containing module is actually imported or exposed.
3. Trusting speculative agent assertions without objective execution or proof artifacts.

If unverified findings are fed directly into risk scoring and pull request generation, developer trust in the tool collapses rapidly due to noise fatigue.

## Decision
We implemented an **Adversarial Verification Stage** powered by a dedicated Red-Team Agent before risk assessment:
- **Mandatory Challenge Phase:** No finding can proceed to Risk Assessment (`P0`–`P4` scoring) without undergoing red-team scrutiny.
- **Independent Validation Checks:** The verification agent performs orthogonal checks:
  - Re-evaluating file paths against test/fixture directories.
  - Inspecting AST import graphs to check call-site reachability.
  - Re-running tests or isolated benchmarks to disprove performance claims.
- **Explicit Verdicts:** Every finding receives one of three formal statuses:
  - `verified`: Grounded in tangible evidence and survived counter-evidence scrutiny.
  - `rejected`: Proven to be a false positive, mock fixture, or unreachable dead code (with documented rebuttal rationale).
  - `insufficient_evidence`: Plausible but lacking proof; enqueues follow-up investigation tasks.

## Consequences

### Positive
- **High Signal-to-Noise Ratio:** Documented example values, test mocks, and dead code alerts are systematically eliminated before risk scoring.
- **Auditability:** Rejected findings remain in the persisted execution trace with detailed rationale, proving why alerts were dismissed.
- **Hallucination Suppression:** Unverified speculative claims made by LLM specialists cannot graduate to actionable issue reports.

### Negative
- **Additional Compute & Latency:** Every finding requires verification reasoning and independent AST/tool execution.
- **Risk of Over-rejection:** Overly conservative verification rules could dismiss subtle, low-frequency security flaws if evidence extraction heuristics are too strict.
