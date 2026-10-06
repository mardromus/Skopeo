# Architecture

Skopeo is an orchestrator–worker system built on a shared blackboard (the Evidence Store).
Every arrow below is a real code path; the names match modules under `backend/app/`.

## System and data flow

```mermaid
flowchart TB
    User([User]) --> UI["Frontend<br/>React + Vite<br/>frontend/src"]
    UI -- "REST /api (poll)" --> API["FastAPI<br/>app/api/routes.py"]
    API -- "create / start / cancel" --> SVC["InvestigationService<br/>background thread per case"]
    SVC --> ORCH

    subgraph GRAPH["LangGraph state machine · app/graph/builder.py"]
        direction TB
        ORCH{{"Orchestrator Agent<br/>plan · review · replan · retry"}}

        subgraph PAR["Specialists — fanned out with Send(), run in parallel"]
            direction LR
            SEC["Security"]
            DEP["Dependency Health"]
            CQ["Code Quality"]
            APIC["API Compatibility"]
            TST["Test Reliability"]
            LIC["License Compliance"]
            MNT["Maintenance Activity"]
            PRF["Performance"]
        end

        CORR["Correlation Agent"]
        VER["Verification / Red-Team Agent"]
        RISK["Risk Assessment Agent"]
        REC["Recommendation Agent"]
        HUM["Human review gate"]
    end

    ES[("Evidence Store · blackboard<br/>SQLite / SQLAlchemy<br/>findings · evidence · requests<br/>correlations · verifications<br/>risks · recommendations · actions<br/>execution_events")]

    ORCH -- "AgentTask (plan / follow-up / retry)" --> PAR
    PAR -- "findings + evidence + investigation requests" --> ES
    PAR -- "agent_completed / agent_failed" --> ORCH
    ES -- "blackboard state (findings, requests, version)" --> ORCH
    ORCH -- "route: correlate" --> CORR
    CORR -- "reads all findings" --> ES
    CORR -- "correlations (compound / contradiction / ...)" --> ES
    CORR --> ORCH
    ORCH -- "route: verify" --> VER
    VER -- "independent checks: re-hash, import graph,<br/>re-run tests, recompute metrics" --> ES
    VER -- "verified / rejected / needs_more_evidence" --> ES
    VER -- "investigation_requested (e.g. benchmark)" --> ORCH
    VER --> ORCH
    ORCH -- "route: assess (only verified evidence)" --> RISK
    RISK -- "P0–P4 risks" --> ES
    RISK --> REC
    REC -- "recommendations + action proposals" --> ES
    REC --> HUM
    HUM -- "approve / reject (DRY_RUN by default)" --> GH["GitHub issue / draft PR"]

    PAR -. "Agent failure (exception, timeout, budget)" .-> FAIL["Fault boundary<br/>app/graph/runtime.py<br/>AgentRun FAILED, evidence kept"]
    FAIL -. "agent_failed event" .-> ORCH
    ORCH -. "retry with fallback strategy<br/>or mark coverage unavailable" .-> PAR

    TOOLS["Safe tool layer · app/tools<br/>allowlisted git / pytest / coverage / benchmarks<br/>OSV · PyPI · npm · GitHub REST"]
    PAR --- TOOLS
    VER --- TOOLS
    LLM["LLMProvider · app/llm<br/>OpenAI · OpenAI-compatible · Mock"]
    ORCH --- LLM
    CORR --- LLM
    VER --- LLM
    REC --- LLM
```

Notes on the diagram:

* **Specialists never call each other.** They communicate only through the blackboard (findings,
  evidence, investigation requests) and through events the orchestrator reads.
* **The orchestrator decides every route** out of `review`; there is no unconditional edge from
  the specialists to correlation or from correlation to risk.
* **Failure path (dotted):** any exception inside an agent is caught at the fault boundary, the
  run is marked `FAILED`/`TIMEOUT`, its evidence stays on the blackboard, and the orchestrator
  decides to retry (possibly with a degraded strategy) or to report partial coverage.

## LangGraph state machine

```mermaid
stateDiagram-v2
    [*] --> prepare
    prepare --> plan: repository cloned / fixture copied
    prepare --> finalize: ingestion failed
    plan --> specialist: Send() x N (parallel)
    specialist --> review: superstep complete (fan-in)
    review --> specialist: dispatch follow-ups / retries (Send x N)
    review --> correlate: blackboard version changed
    review --> verify: findings not yet challenged
    review --> assess: everything ruled on, or budget exhausted
    review --> finalize: cancelled
    correlate --> review
    verify --> review: rulings + investigation requests
    assess --> recommend
    recommend --> human_review
    human_review --> finalize
    finalize --> [*]
```

The graph state (`app/graph/state.py`) carries only control information: the task queue, round
counters, which results were reviewed, and the blackboard version at the last correlation and
verification. All knowledge lives in the database.

## Evidence Store (blackboard) data model

```mermaid
erDiagram
    INVESTIGATIONS ||--o{ AGENT_RUNS : "runs"
    INVESTIGATIONS ||--o{ FINDINGS : "has"
    INVESTIGATIONS ||--o{ EXECUTION_EVENTS : "trace"
    INVESTIGATIONS ||--o{ INVESTIGATION_REQUESTS : "follow-up asks"
    FINDINGS ||--o{ EVIDENCE : "backed by"
    FINDINGS ||--o{ VERIFICATIONS : "ruled on"
    CORRELATIONS ||--o{ VERIFICATIONS : "ruled on"
    INVESTIGATIONS ||--o{ CORRELATIONS : "links findings"
    INVESTIGATIONS ||--o{ RISKS : "scores"
    RISKS ||--o| RECOMMENDATIONS : "remediated by"
    RECOMMENDATIONS ||--o{ ACTION_PROPOSALS : "proposes"
```

Tables are created by Alembic (`backend/migrations/versions/0001_initial_schema.py`) with UUID
primary keys and indexes on `investigation_id`, `agent`, `severity`, `status` and `created_at`.
Only portable column types are used, so `DATABASE_URL` can point at PostgreSQL.

## Concurrency model

* Each investigation runs in its own thread with its own asyncio loop (`InvestigationService`).
* Specialists in the same superstep run concurrently: each agent body executes in a worker thread
  (`asyncio.to_thread`) under `asyncio.wait_for(AGENT_TIMEOUT_SECONDS)`.
* SQLite allows one writer, so every blackboard write goes through one lock
  (`app/database/session.py`); reads stay concurrent (WAL mode).
* The demo run reaches 8 agents executing at the same time (`execution_summary.parallelism`).
