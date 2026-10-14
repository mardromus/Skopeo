# Input Definition — Skopeo

Skopeo accepts a **GitHub repository to investigate**, and afterwards **natural-language questions** about that investigation. Every input is a JSON body validated by a Pydantic schema; unknown fields, non-GitHub URLs and invalid values are rejected with HTTP 422 before any agent runs.

## 1. Start an investigation — `POST /api/investigations`

Schema (`InvestigationCreate`, `backend/app/schemas/investigation.py`):

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `repository_url` | string | yes | `https://github.com/<owner>/<repo>` only (no other hosts, no `http://`, no query string, no credentials); normalised to the canonical URL |
| `branch` | string | no, default `"main"` | valid git ref name; no `..`, no leading `-`, no control characters |
| `analysis_depth` | enum | no, default `"standard"` | `"quick"` (security, dependencies, tests) · `"standard"` (every relevant agent) · `"deep"` (every agent, always) |
| `enable_github_actions` | boolean | no, default `false` | allow approved issues / draft PRs to be proposed for GitHub (still human-approved; `DRY_RUN` on by default) |

Authentication: a signed-in user's Firebase ID token (`Authorization: Bearer <token>`, Google or GitHub sign-in), or the server access key (`X-Skopeo-Key`). The bundled reference case needs neither.

**Real sample input** (sent to the running API on 15 Oct 2026; accepted with `202 Accepted`):

```json
{
  "repository_url": "https://github.com/pallets/itsdangerous",
  "branch": "main",
  "analysis_depth": "standard",
  "enable_github_actions": false
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

## 5. Invalid input is rejected (real responses from the running API)

| Input | Response (HTTP 422) |
| --- | --- |
| `{"repository_url": "https://github.com/psf/requests", "analysis_depth": "full"}` | `Input should be 'quick', 'standard' or 'deep'` |
| `{"repository_url": "http://evil.example/a/b"}` | `Value error, only https:// GitHub URLs are supported` |
| `{"repository_url": "https://github.com/psf/requests", "extra": 1}` | `Extra inputs are not permitted` |
| chat question for an unknown investigation id | `404 investigation not found` |

Repository content itself is also an input, and is treated strictly as **untrusted data**: it is never executed unless sandboxed execution is enabled, and text passed to the LLM is wrapped as untrusted so instructions inside the repository (prompt injection) are not followed.
