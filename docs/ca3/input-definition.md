# Input Definition — Skopeo

Skopeo accepts a **GitHub repository to investigate**, and afterwards **natural-language questions** about that investigation. Every input is a JSON body validated by a Pydantic schema; unknown fields, non-GitHub URLs and invalid values are rejected with HTTP 422 before any agent runs.

## 1. Start an investigation — `POST /api/investigations`

Schema (`InvestigationCreate`, `backend/app/schemas/investigation.py`):

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `repository_url` | string | yes | `https://github.com/<owner>/<repo>` only (no other hosts, no `http://`, no query string, no credentials); normalised to the canonical URL |
| `branch` | string | no, default `"main"` | valid git ref name; no `..`, no leading `-`, no control characters |
| `analysis_depth` | enum | no, default `"standard"` | `"quick"` (security, dependencies, tests) · `"standard"` (every relevant agent) · `"deep"` (every agent, always) |
| `enable_github_actions` | boolean | no, default `false` | allow approved issues / draft PRs to be proposed for GitHub (still human-approved) |
| `dry_run` | boolean or null | no, default `null` | `true`: approvals are only recorded; `false`: approved actions are sent to GitHub. `null` uses the user's saved default, then the server's `DRY_RUN` |
| `sandbox_execution` | boolean or null | no, default `null` | allow this case to run the repository's own tests/benchmarks. `true` is refused (HTTP 400) unless the server sets `SKOPEO_ALLOW_CASE_EXECUTION`; the UI asks for confirmation twice |

Authentication: a signed-in user's Firebase ID token (`Authorization: Bearer <token>`, Google or GitHub sign-in), or the server access key (`X-Skopeo-Key`). The bundled reference case needs neither.

**Real sample input** (sent to the running API on 15 Oct 2026; accepted with `202 Accepted`):

```json
{
  "repository_url": "https://github.com/pallets/itsdangerous",
  "branch": "main",
  "analysis_depth": "standard",
  "enable_github_actions": false,
  "dry_run": true
}
```

## 2. Reference case — `POST /api/demo/investigations`

Runs the same agents on the bundled repository `examples/vulnerable-demo-repo` (offline, reproducible). Schema: `analysis_depth` (enum above), `fault_injection` (boolean: make the performance agent fail once to demonstrate recovery), `step_delay_ms` (0–3000, pacing for live viewing).

**Real sample input** (the run in the submitted execution trace):

```json
{ "fault_injection": true }
```

## 3. Import one of your GitHub repositories — `POST /api/github/import`

After "Sign in with GitHub" (or connecting a personal access token), the user picks a repository from their list.

| Field | Type | Rules |
| --- | --- | --- |
| `full_name` | string | `owner/repo`, 3–140 chars, must be visible to the user's GitHub account |
| `target` | enum | `"investigation"` (start a case) or `"project"` (add to Projects for upstream watching) |
| `branch` | string, optional | defaults to the repository's default branch |
| `analysis_depth` | enum, optional | as above |
| `enable_github_actions`, `dry_run`, `sandbox_execution` | optional | as in section 1 (chosen in the pop-up shown before the case starts) |

Sample: `{ "full_name": "mardromus/Skopeo", "target": "investigation", "analysis_depth": "standard" }`

## 4. Ask the agents — `POST /api/investigations/{id}/chat`

| Field | Type | Rules |
| --- | --- | --- |
| `question` | string | 2–2000 characters |
| `agent` | string, optional | force a specific agent (`security_agent`, `dependency_agent`, `code_quality_agent`, `api_compatibility_agent`, `test_reliability_agent`, `license_agent`, `maintenance_agent`, `performance_agent`, `verification_agent`, `correlation_agent`, `risk_agent`, `recommendation_agent`, `orchestrator`); omitted = routed automatically |

**Real sample input** (asked of the traced investigation):

```json
{ "question": "Is the JWT handling in this repository safe?" }
```

## 5. Guardrails during and across cases

| Endpoint | Body | Effect |
| --- | --- | --- |
| `PATCH /api/investigations/{id}/options` | `{ "dry_run": false }` | switch dry run for one case at any time, even while it runs; only the case owner may change it |
| `PUT /api/auth/preferences` | `{ "dry_run": false }` (or `null` to clear) | the signed-in user's default for new cases |

Real response to the PATCH above: `200 { "investigation_id": "aa224829-…", "status": "running", "options": { "dry_run": false, "sandbox_execution": null } }`.

## 6. Invalid input is rejected (real responses from the running API)

| Input | Response (HTTP 422) |
| --- | --- |
| `{"repository_url": "https://github.com/psf/requests", "analysis_depth": "full"}` | `Input should be 'quick', 'standard' or 'deep'` |
| `{"repository_url": "http://evil.example/a/b"}` | `Value error, only https:// GitHub URLs are supported` |
| `{"repository_url": "https://github.com/psf/requests", "extra": 1}` | `Extra inputs are not permitted` |
| `{"repository_url": "https://github.com/pallets/itsdangerous", "dry_run": "maybe"}` | `Input should be a valid boolean, unable to interpret input` |
| `{"repository_url": "https://github.com/pallets/itsdangerous", "sandbox_execution": true}` on a server that does not allow it | HTTP 400 `this server does not allow running repository code; set SKOPEO_ALLOW_CASE_EXECUTION=true to permit it per case` |
| chat question for an unknown investigation id | `404 investigation not found` |

Repository content itself is also an input, and is treated strictly as **untrusted data**: it is never executed unless execution is both allowed by the server and chosen for the case, and text passed to the LLM is wrapped as untrusted so instructions inside the repository (prompt injection) are not followed.
