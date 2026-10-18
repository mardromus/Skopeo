# ADR-0001: Blackboard Pattern over Linear Pipeline

## Status
Accepted

## Context
Traditional static analysis tools and early multi-agent code scanners chain analysis sequentially:
`Linter → Dependency Scanner → Security Scanner → Summary`.

In software repository intelligence, this linear pipeline (DAG) breaks down because:
1. **Unpredictable dependencies between specialist findings:** A vulnerable dependency discovered by the Dependency Health agent only becomes high risk if the Security agent confirms it is reachable from public API entrypoints, and the Test Reliability agent discovers no tests cover that code path.
2. **Dynamic follow-up requests:** When an agent discovers an anomaly (e.g., an unmeasured database loop claim or an undocumented JWT decoder), it must request follow-up investigation (e.g., dispatching benchmarks or AST inspection).
3. **Partial failure resilience:** In a fixed pipeline, an exception or timeout in one tool halts execution or produces truncated results.

## Decision
We adopted an **Orchestrator–Blackboard Architecture** implemented via LangGraph and an Evidence Store:
- **Central Blackboard (Evidence Store):** All specialist agents write structured findings, raw evidence, and investigation requests to a shared store.
- **Dynamic Orchestrator:** Instead of traversing a predetermined graph, the orchestrator inspects the current state of the blackboard after every phase, evaluates open requests, retries failed specialists using degraded fallback strategies, and decides the next phase (`dispatch`, `correlate`, `verify`, `assess`).
- **Autonomous Specialist Steps:** Each specialist agent plans its own internal step list based on the repository profile and can dynamically append steps as intermediate evidence warrants.

## Consequences

### Positive
- **Compound Risk Detection:** Agents correlate findings across security, dependency, performance, and testing domains.
- **Resilient Execution:** Failures in individual agents are isolated. The orchestrator can retry with fallbacks (e.g., static AST fallback when dynamic tools are unavailable) without aborting the investigation.
- **Adaptive Planning:** The system only runs agents and deep follow-ups relevant to the repository's profile (e.g., benchmarks run only when performance-sensitive packages or unmeasured claims exist).

### Negative
- **State Complexity:** Coordinating state transitions, request lifecycles, and blackboard revisions requires robust concurrency control and schema validation.
- **Variable Latency:** Because the orchestrator may trigger re-planning rounds, run durations vary based on repository findings rather than a fixed number of pipeline steps.
