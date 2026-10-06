# API

Base path `/api`. Interactive OpenAPI docs are served by FastAPI at `/docs` and `/redoc`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | mode, provider, DRY_RUN, offline, sandbox execution, token presence |
| `GET` | `/agents` | the 13 agents with descriptions and modes |
| `POST` | `/investigations` | start an investigation of a GitHub repository (202) |
| `POST` | `/demo/investigations` | start the bundled reference case (requires `SKOPEO_DEMO_MODE=true`) |
| `GET` | `/investigations` | recent investigations |
| `GET` | `/investigations/{id}` | detail: status, profile, plan (with revisions), coverage, execution summary, counts |
| `GET` | `/investigations/{id}/agents` | agent runs (trigger, mode, strategy, attempt, round, status, timings, budgets used) |
| `GET` | `/investigations/{id}/findings` | findings; filters `severity`, `category`, `status`, `agent`, `min_confidence`, `file` |
| `GET` | `/investigations/{id}/evidence` | evidence, optionally `?finding_id=` |
| `GET` | `/investigations/{id}/correlations` | correlations |
| `GET` | `/investigations/{id}/verifications` | red-team rulings with every check |
| `GET` | `/investigations/{id}/risks` | verified risks, highest first |
| `GET` | `/investigations/{id}/recommendations` | remediation, by priority |
| `GET` | `/investigations/{id}/actions` | GitHub action proposals |
| `GET` | `/investigations/{id}/requests` | investigation requests and their decisions |
| `GET` | `/investigations/{id}/events` | execution trace; `?after_seq=` for incremental polling |
| `POST` | `/investigations/{id}/cancel` | request cancellation |
| `POST` | `/investigations/{id}/approve-action` | approve or reject a proposal |
| `GET` | `/investigations/{id}/report` | `?format=json` (output schema) or `?format=markdown` |

## Input

```json
POST /api/investigations
{
  "repository_url": "https://github.com/owner/repository",
  "branch": "main",
  "analysis_depth": "standard",
  "enable_github_actions": false
}
```

* `repository_url` — only `https://github.com/<owner>/<repo>` (optional `.git`). Anything else is a 422.
* `branch` — validated ref name.
* `analysis_depth` — `quick` (security, dependencies, tests) · `standard` · `deep` (every agent).
* Unknown fields are rejected.

```json
POST /api/demo/investigations
{ "fault_injection": true, "analysis_depth": "standard", "step_delay_ms": 120 }
```

```json
POST /api/investigations/{id}/approve-action
{ "action_id": "…", "decision": "approve", "approved_by": "reviewer name", "note": "optional" }
```
Returns the updated proposal. With `DRY_RUN=true` the status becomes `approved_dry_run` and nothing
is sent. Deciding the same proposal twice returns 409.

## Output (`GET /report?format=json`)

```json
{
  "investigation_id": "…",
  "repository": "examples/vulnerable-demo-repo",
  "status": "completed_with_limitations",
  "overall_risk": { "score": 97.8, "level": "critical" },
  "agent_summary": { "performance_agent": { "runs": 4, "statuses": ["failed (ToolUnavailableError)", "completed", "completed", "completed"], "findings": 2 } },
  "plan": { "assessment": "…", "initial_tasks": [], "skipped": [], "revisions": [] },
  "findings": [],
  "correlations": [],
  "verified_findings": [],
  "rejected_findings": [],
  "insufficient_evidence_findings": [],
  "verifications": [],
  "risks": [],
  "recommendations": [],
  "actions": [],
  "requests": [],
  "coverage": { "agents": { "performance_agent": { "status": "partial", "limitations": ["attempt 1 … FAILED …"] } } },
  "execution_summary": { "rounds": 3, "replans": 2, "agent_runs": 21, "agent_failures": 1, "retries": 1, "parallelism": 8, "llm": {} },
  "events": []
}
```

### Finding

```json
{
  "finding_id": "uuid", "agent": "security_agent", "category": "security", "rule_id": "security.hardcoded_secret",
  "title": "…", "description": "…", "severity": "high", "confidence": 0.1,
  "confidence_factors": [{ "factor": "evidence_strength", "delta": 0.82, "detail": "2 evidence item(s): static_analysis" }],
  "status": "rejected", "subject": "file:tests/fixtures/example_credentials.txt",
  "affected_files": ["tests/fixtures/example_credentials.txt"], "affected_components": ["tests", "fixtures", "secrets"],
  "evidence_ids": ["uuid"], "tool_results": [], "attributes": { "masked_values": ["AKIA************MPLE"] },
  "reasoning_summary": "…", "recommended_action": "…", "is_hypothesis": false,
  "created_at": "…", "updated_at": "…"
}
```

### Evidence

```json
{
  "evidence_id": "uuid", "finding_id": "uuid", "source_type": "static_analysis",
  "source": "tests/fixtures/example_credentials.txt:4", "file": "tests/fixtures/example_credentials.txt",
  "line_start": 4, "line_end": 4, "excerpt": "aws_access_key_id = AKIA************MPLE",
  "tool": "skopeo-secret-scanner", "raw_reference": "", "confidence": 0.8,
  "created_by": "security_agent", "content_hash": "sha256 of the cited lines"
}
```
`source_type` is one of `static_analysis | git | github | test | dependency | llm_analysis | benchmark`.

### Correlation · Verification · Event

```json
{ "correlation_id": "uuid", "finding_ids": ["…"], "relationship_type": "compound_risk",
  "description": "…", "risk_multiplier": 1.75, "confidence": 0.94, "status": "verified" }

{ "verification_id": "uuid", "finding_id": "uuid", "round": 1, "decision": "rejected", "confidence": 0.8,
  "challenge": "Is this a live credential, or a documented dummy value in a fixture?",
  "checks": [{ "check": "placeholder", "outcome": "fail", "detail": "…", "supports": "rejection" }],
  "evidence_checked": ["…"], "additional_tests": [], "counter_evidence": [], "reasoning_summary": "…",
  "decided_by": "policy", "verified_at": "…" }

{ "event_id": "uuid", "investigation_id": "uuid", "seq": 102, "sender": "verification_agent",
  "receiver": "security_agent", "event_type": "finding_rejected", "severity": "warning",
  "message": "REJECTED: …", "payload": {}, "timestamp": "…" }
```
