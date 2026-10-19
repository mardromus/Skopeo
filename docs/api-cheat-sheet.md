# Skopeo API Cheat Sheet & cURL Reference

A quick-reference guide with copy-pasteable `curl` commands to inspect, run, and query Skopeo investigations locally or in production.

---

## 1. Setup & Environment Variables

```bash
# Target base URL (default local development port is 8000)
export BASE_URL="http://localhost:8000"

# Optional: Set access token if authentication is enabled
export TOKEN="your_api_key_or_firebase_jwt"
```

---

## 2. Health & Agent Catalog

### Check System Health
Inspect server mode, LLM provider, execution sandbox, and offline status:
```bash
curl -fsS "${BASE_URL}/api/health" | jq .
```

### List Specialist & Coordination Agents
List all 13 agents, their display names, descriptions, and supported modes:
```bash
curl -fsS "${BASE_URL}/api/agents" | jq .
```

---

## 3. Running Investigations

### Start Reference Demo Case
Triggers the bundled reference repository investigation (`examples/vulnerable-demo-repo`):
```bash
curl -fsS -X POST "${BASE_URL}/api/demo/investigations" \
  -H "Content-Type: application/json" \
  -d '{"analysis_depth": "standard", "step_delay_ms": 0}' | jq .
```
*Note the returned `investigation_id` for subsequent queries.*

### Start a Live GitHub Repository Investigation
Analyze an external GitHub repository:
```bash
curl -fsS -X POST "${BASE_URL}/api/investigations" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "repository_url": "https://github.com/owner/repository",
    "branch": "main",
    "analysis_depth": "standard",
    "enable_github_actions": false
  }' | jq .
```

---

## 4. Monitoring & Investigation Details

### Check Investigation Status
Query execution status (`queued`, `running`, `completed`, `completed_with_limitations`):
```bash
export ID="your-investigation-id-here"

curl -fsS "${BASE_URL}/api/investigations/${ID}" | jq '{
  status: .status,
  overall_risk: .overall_risk,
  execution_summary: .execution_summary,
  agent_runs_count: (.agent_runs | length)
}'
```

### List Agent Runs & Budget Consumption
Inspect individual agent attempts, statuses, iterations, and timings:
```bash
curl -fsS "${BASE_URL}/api/investigations/${ID}/agents" | jq '.[] | {
  agent: .agent,
  mode: .mode,
  status: .status,
  iterations_used: .iterations_used,
  duration_ms: .duration_ms
}'
```

### Incremental Event Polling (Execution Trace)
Poll blackboard and orchestrator events after sequence number `N`:
```bash
curl -fsS "${BASE_URL}/api/investigations/${ID}/events?after_seq=0" | jq .
```

---

## 5. Findings, Verification & Risk Results

### Filter Findings by Severity or Verification Status
```bash
# Query verified critical findings
curl -fsS "${BASE_URL}/api/investigations/${ID}/findings?severity=critical&status=verified" | jq .

# Query rejected false-positive findings
curl -fsS "${BASE_URL}/api/investigations/${ID}/findings?status=rejected" | jq .
```

### View Red-Team Verification Rulings
See how each finding was challenged and the verification rationale:
```bash
curl -fsS "${BASE_URL}/api/investigations/${ID}/verifications" | jq '.[] | {
  finding_id: .finding_id,
  status: .status,
  rationale: .rationale,
  checks_run: (.checks | length)
}'
```

### Cross-Domain Compound Correlations
Inspect linked findings connected by the correlation agent:
```bash
curl -fsS "${BASE_URL}/api/investigations/${ID}/correlations" | jq .
```

### Prioritized Risk Assessment & Remediation
```bash
# Prioritized risks (P0 - P4)
curl -fsS "${BASE_URL}/api/investigations/${ID}/risks" | jq .

# Actionable recommendations
curl -fsS "${BASE_URL}/api/investigations/${ID}/recommendations" | jq .
```

---

## 6. Audit Reports & Human Action Approval

### Export Complete Audit Report
```bash
# Export JSON report
curl -fsS "${BASE_URL}/api/investigations/${ID}/report?format=json" > report.json

# Export Markdown executive report
curl -fsS "${BASE_URL}/api/investigations/${ID}/report?format=markdown" > report.md
```

### Approve or Reject an Action Proposal
When human review is requested for GitHub PR / issue proposals:
```bash
curl -fsS -X POST "${BASE_URL}/api/investigations/${ID}/approve-action" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "action_id": "action-uuid-here",
    "decision": "approve",
    "approved_by": "Security Lead",
    "note": "Verified locally against dry run"
  }' | jq .
```

### Cancel an Active Investigation
```bash
curl -fsS -X POST "${BASE_URL}/api/investigations/${ID}/cancel" | jq .
```
