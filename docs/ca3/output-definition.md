# Output Definition — Skopeo

For every investigation Skopeo produces a **risk report**: findings backed by evidence, the red team's rulings on each, cross-agent correlations (compound risks), prioritised risks (P0–P4), fixes, a coverage table, and the full execution trace. It is shown in the web UI and returned by `GET /api/investigations/{id}/report` (JSON, or `?format=markdown`). Questions asked in **Ask the agents** return an answer from the responsible agent with the findings it cited.

## 1. Report schema — `GET /api/investigations/{id}/report`

| Field | Type | Content |
| --- | --- | --- |
| `investigation_id`, `repository`, `repository_url`, `branch`, `commit_sha` | string | what was analysed (exact commit) |
| `status` | enum | `completed` · `completed_with_limitations` (some capability unavailable, stated in `coverage`) · `failed` · `cancelled` |
| `overall_risk` | `{score: 0–100, level}` | `level` ∈ `critical, high, medium, low, minimal` |
| `findings[]` | Finding | `finding_id`, `agent`, `category` (security, dependency, code_quality, api_compatibility, testing, license, maintenance, performance), `rule_id`, `title`, `description`, `severity` (critical…info), `confidence` 0–1 with `confidence_factors[]`, `status` (proposed, correlated, challenged, verified, rejected, needs_more_evidence), `affected_files[]`, `evidence_ids[]`, `reasoning_summary`, `recommended_action` |
| `verified_findings[]`, `rejected_findings[]`, `insufficient_evidence_findings[]` | Finding | the same findings split by the red team's ruling |
| `verifications[]` | Verification | `finding_id` or `correlation_id`, `round`, `decision` (verified, rejected, needs_more_evidence), `confidence`, `challenge`, `checks[]` (`check`, `question`, `outcome`, `detail`), `decided_by` |
| `correlations[]` | Correlation | `relationship_type` (compound_risk, shared_root_cause, causal, dependency, duplicate, contradiction), `title`, `finding_ids[]`, `risk_multiplier`, `status` |
| `risks[]` | Risk | `kind` (finding, compound), `title`, `severity`, `score` 0–100, `priority` P0–P4, `factors` (severity × confidence × impact × exploitability × correlation multiplier), `rationale` — verified findings only |
| `recommendations[]` | Recommendation | `title`, `problem`, `proposed_fix`, `priority`, `implementation_difficulty`, `expected_benefit`, `verification_status` |
| `actions[]` | ActionProposal | GitHub issue / draft PR proposals awaiting human approval |
| `requests[]` | InvestigationRequest | follow-up work agents asked for, and the orchestrator's decision |
| `coverage.agents{}` | per agent | `status` (complete, partial, unavailable, skipped), `analyzed[]`, `limitations[]` |
| `execution_summary` | object | rounds, replans, agent runs, failures, retries, follow-ups, counts, LLM usage |
| `events[]` | ExecutionEvent | `seq`, `timestamp`, `sender`, `receiver`, `event_type`, `message`, `payload` — the execution trace |

## 2. Real sample output

From the traced run (investigation `a2d2d2d9-32ba-420e-af12-d187dee772af`, reference repository, 15 Oct 2026). Each list shows one real item; the complete 538 KB report is `docs/ca3/sample-output-full.json` in the repository.

```json
{
  "investigation_id": "a2d2d2d9-32ba-420e-af12-d187dee772af",
  "repository": "examples/vulnerable-demo-repo",
  "status": "completed_with_limitations",
  "overall_risk": {
    "score": 97.8,
    "level": "critical"
  },
  "execution_summary": {
    "agent_runs": 21,
    "agent_failures": 1,
    "retries": 1,
    "follow_ups": 5,
    "replans": 2,
    "findings": 24,
    "verified": 20,
    "rejected": 3,
    "insufficient_evidence": 1
  },
  "findings": [
    {
      "finding_id": "88cd8dcb-830f-408a-9c9b-ebf5fb89e608",
      "agent": "dependency_agent",
      "category": "dependency",
      "title": "PyJWT 1.7.1 is affected by 11 known vulnerabilities",
      "severity": "critical",
      "confidence": 0.99,
      "status": "verified",
      "affected_files": [
        "requirements.txt"
      ],
      "evidence_ids": [
        "cb6d0009-677a-43de-86dd-a861856bde99",
        "1f9084b5-66e1-49a7-96e5-6941c046b776",
        "3602378c-2eb6-4a0b-a27f-46cc72a8b647",
        "5d63cc55-8600-4b45-95f2-d59e473ce780",
        "703780b4-10e1-45ba-81dc-1b0e3cf3e115",
        "0503ae33-a491-4c64-8d3e-b1c379e9d185",
        "5da4db64-2ca9-4c95-a4d4-c162ad67755c",
        "28f88d4f-5717-4be6-a780-dd2ea6df85d3",
        "20a707aa-caf7-4cdb-a1cb-40ca0ee2e0c0",
        "b155ad81-1441-4f99-820a-a463f0f20232",
        "07dc98c8-1778-4977-bc86-6456fbb31bd1",
        "2939e54e-1cda-4547-970b-29cf6ef4ae3b"
      ],
      "recommended_action": "Upgrade PyJWT to 2.14.0 or later."
    }
  ],
  "correlations": [
    {
      "correlation_id": "078d4455-2f90-477a-9d2f-a16990a9a51d",
      "relationship_type": "compound_risk",
      "title": "Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests",
      "finding_ids": [
        "88cd8dcb-830f-408a-9c9b-ebf5fb89e608",
        "139d3a2a-042f-4737-a2ad-6ce9ba52fc94",
        "6ae50d21-e98c-49f2-9694-bfa2d7a1feb1",
        "cd40835a-8603-4dbb-a2c8-d8f8f1f8349d"
      ],
      "risk_multiplier": 1.75,
      "status": "verified"
    }
  ],
  "verifications": [
    {
      "finding_id": "b0604fe7-fe3a-44d4-9755-cd437f206cc1",
      "round": 1,
      "decision": "rejected",
      "confidence": 0.7,
      "challenge": "Is this a live credential, or a documented dummy value in a fixture? Is it used by production code?",
      "decided_by": "policy",
      "checks": [
        {
          "check": "evidence_integrity",
          "question": "Is the evidence real?",
          "outcome": "pass",
          "detail": "re-hashed 1 referenced line range(s); all match the repository",
          "supports": null
        },
        {
          "check": "staleness",
          "question": "Is the evidence stale?",
          "outcome": "pass",
          "detail": "evidence captured at the analysed commit 5eda3b9ec3",
          "supports": null
        }
      ]
    }
  ],
  "risks": [
    {
      "kind": "compound",
      "title": "Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests",
      "severity": "critical",
      "score": 94.5,
      "priority": "P0",
      "correlation_multiplier": 1.75,
      "member_finding_ids": [
        "88cd8dcb-830f-408a-9c9b-ebf5fb89e608",
        "139d3a2a-042f-4737-a2ad-6ce9ba52fc94",
        "6ae50d21-e98c-49f2-9694-bfa2d7a1feb1",
        "cd40835a-8603-4dbb-a2c8-d8f8f1f8349d"
      ]
    }
  ],
  "recommendations": [
    {
      "title": "Fix compound risk: Compound authentication upgrade risk: vulnerable PyJWT 1.7.1 in authentication code with insufficient tests",
      "priority": "P0",
      "implementation_difficulty": "medium",
      "verification_status": "verified",
      "proposed_fix": "1. Upgrade PyJWT from 1.7.1 to 2.14.0 or later (resolves 11 advisories).\n2. In the same change, update the breaking call sites (shopfront/auth/middleware.py:17, shopfront/auth/middleware.py:26): Drop the .decode('utf-8') call on the token. Pass an explicit allow-list, e.g. algorithms=[\"HS256\"].\n3. A\u2026"
    }
  ],
  "coverage": {
    "agents": {
      "performance_agent": {
        "status": "partial",
        "runs": 4,
        "failures": 1
      }
    }
  },
  "events": [
    {
      "seq": 40,
      "sender": "performance_agent",
      "receiver": "orchestrator",
      "event_type": "agent_failed",
      "message": "Performance Agent FAILED: ToolUnavailableError: benchmark harness unavailable [controlled fault injection: SKOPEO_FAULT_INJECTION=performance_agent@1]"
    },
    {
      "seq": 60,
      "sender": "orchestrator",
      "receiver": "performance_agent",
      "event_type": "agent_retry_scheduled",
      "message": "performance_agent FAILED -> RETRYING (attempt 2, strategy 'static_only'): ToolUnavailableError: benchmark harness unavailable [controlled fault injection: SKOPEO_FAULT_INJECTION=performance_agent@1]; retry 2 with strategy 'static_only'"
    },
    {
      "seq": 62,
      "sender": "orchestrator",
      "receiver": "all_agents",
      "event_type": "replan",
      "message": "Replanned: +security_agent (dependency_usage), +api_compatibility_agent (upgrade_compatibility), +test_reliability_agent (dependency_coverage); performance follow-up not required (pyjwt is not on a performance-sensitive path)"
    }
  ]
}```

## 3. Ask the agents — `POST /api/investigations/{id}/chat`

Response: the stored `question` and `answer` messages. The answer carries `agent` (who answered), `routing_reason` and `routed_by` (keyword policy or `llm:<model>`), `content` (Markdown, grounded only in that agent's findings and evidence), `citations[]` (only finding ids that exist in the case), `follow_ups[]` and `decided_by` (`llm:<model>` in live mode, `policy` when built from recorded results).

**Real sample output** (same investigation):

```json
{
  "question": "Is the JWT handling in this repository safe?",
  "answer": {
    "agent": "security_agent",
    "agent_display_name": "Security Agent",
    "routing_reason": "Security Agent owns this topic (matched 'jwt', 'safe').",
    "routed_by": "policy",
    "decided_by": "policy",
    "content": "I (Security Agent) recorded **7 findings** (5 high, 1 medium, 1 low). Most relevant to your question:\n\n- **Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py)** (high, verified, confidence 99%) \u2014 `shopfront/auth/middleware.p\u2026",
    "citations": [
      {
        "finding_id": "139d3a2a-042f-4737-a2ad-6ce9ba52fc94",
        "title": "Vulnerable pyjwt is used by the authentication component (shopfront/auth/middleware.py)",
        "severity": "high",
        "agent": "security_agent",
        "file": "shopfront/auth/middleware.py"
      },
      {
        "finding_id": "59fd753e-cc91-4ef3-aa71-e7ba7ea2375d",
        "title": "JWT decoded without an explicit algorithms allow-list in shopfront/auth/middleware.py",
        "severity": "high",
        "agent": "security_agent",
        "file": "shopfront/auth/middleware.py"
      }
    ],
    "follow_ups": [
      "Which security finding is the most severe?",
      "Is any of these reachable from user input?",
      "How do I fix the most serious issue?"
    ]
  }
}```

Other outputs: a Markdown report (`?format=markdown`), notifications (email, Slack, Discord, webhook) when a case finishes, and — for Projects — upstream impact reports that list the exact lines of the user's code affected by changes in a watched open-source dependency.
