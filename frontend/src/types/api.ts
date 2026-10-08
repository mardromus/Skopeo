// Types mirror the backend's Pydantic response schemas (app/schemas/*).

export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type FindingStatus = "proposed" | "correlated" | "challenged" | "verified" | "rejected" | "needs_more_evidence";
export type InvestigationStatus = "queued" | "running" | "completed" | "completed_with_limitations" | "failed" | "cancelled";
export type Priority = "P0" | "P1" | "P2" | "P3" | "P4";

export interface OverallRisk {
  score: number | null;
  level: string | null;
}

export interface InvestigationSummary {
  investigation_id: string;
  repository: string;
  repository_url: string;
  branch: string;
  source: string;
  analysis_depth: string;
  status: InvestigationStatus;
  overall_risk: OverallRisk | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
}

export interface AgentCoverage {
  status: "complete" | "partial" | "unavailable" | "skipped";
  runs: number;
  failures?: number;
  findings?: number;
  analyzed?: string[];
  limitations: string[];
  reason?: string;
}

export interface InvestigationDetail extends InvestigationSummary {
  commit_sha: string | null;
  repo_profile: Record<string, unknown>;
  plan: {
    assessment?: string;
    rationale?: string;
    decided_by?: string;
    initial_tasks?: { agent: string; objective: string; rationale: string; priority: number }[];
    skipped?: { agent: string; reason: string }[];
    revisions?: { round: number; added: { agent: string; mode: string; objective: string; rationale: string }[] }[];
  };
  coverage: { agents?: Record<string, AgentCoverage>; summary?: Record<string, number> };
  execution_summary: Record<string, unknown> & {
    rounds?: number;
    replans?: number;
    agent_runs?: number;
    agent_failures?: number;
    retries?: number;
    follow_ups?: number;
    verified?: number;
    rejected?: number;
    insufficient_evidence?: number;
    parallelism?: number;
    duration_seconds?: number;
    llm?: { provider?: string; llm_calls?: number; decisions?: number; policy_fallbacks?: number };
  };
  enable_github_actions: boolean;
  error: string | null;
  counts: Record<string, unknown> & { findings?: number; evidence?: number; events?: number; correlations?: number };
}

export interface AgentRun {
  run_id: string;
  agent: string;
  task_id: string;
  objective: string;
  mode: string;
  strategy: string;
  attempt: number;
  trigger: string;
  round: number;
  status: "pending" | "running" | "completed" | "failed" | "timeout" | "skipped" | "cancelled";
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  iterations: number;
  tool_calls: number;
  llm_calls: number;
  findings_count: number;
  error_type: string | null;
  error_message: string | null;
  summary: string | null;
  coverage: { limitations?: string[]; analyzed?: string[] } & Record<string, unknown>;
}

export interface ConfidenceFactor {
  factor: string;
  delta: number;
  detail: string;
}

export interface Finding {
  finding_id: string;
  agent: string;
  category: string;
  rule_id: string;
  title: string;
  description: string;
  severity: Severity;
  confidence: number;
  confidence_factors: ConfidenceFactor[];
  status: FindingStatus;
  subject: string | null;
  affected_files: string[];
  affected_components: string[];
  evidence_ids: string[];
  tool_results: Record<string, unknown>[];
  attributes: Record<string, unknown>;
  reasoning_summary: string;
  recommended_action: string;
  is_hypothesis: boolean;
  created_at: string;
  updated_at: string;
}

export interface Evidence {
  evidence_id: string;
  finding_id: string | null;
  source_type: string;
  source: string;
  file: string | null;
  line_start: number | null;
  line_end: number | null;
  excerpt: string;
  tool: string;
  raw_reference: string;
  confidence: number;
  created_by: string;
  created_at: string;
}

export interface Correlation {
  correlation_id: string;
  finding_ids: string[];
  relationship_type: "compound_risk" | "duplicate" | "contradiction" | "dependency" | "causal" | "shared_root_cause";
  title: string;
  description: string;
  risk_multiplier: number;
  confidence: number;
  status: "proposed" | "verified" | "rejected" | "resolved";
  links: Record<string, unknown>[];
  reasoning_summary: string;
  resolution: string | null;
  created_at: string;
}

export interface VerificationCheck {
  check: string;
  question: string;
  outcome: "pass" | "fail" | "inconclusive" | "not_applicable";
  detail: string;
  supports: string | null;
}

export interface Verification {
  verification_id: string;
  finding_id: string | null;
  correlation_id: string | null;
  round: number;
  decision: "verified" | "rejected" | "needs_more_evidence";
  confidence: number;
  challenge: string;
  checks: VerificationCheck[];
  counter_evidence: { check: string; detail: string }[];
  adjusted_severity: Severity | null;
  reasoning_summary: string;
  decided_by: string;
  verified_at: string;
}

export interface Risk {
  risk_id: string;
  finding_id: string | null;
  correlation_id: string | null;
  kind: "finding" | "compound";
  title: string;
  category: string;
  severity: Severity;
  score: number;
  priority: Priority;
  confidence: number;
  impact: number;
  exploitability: number;
  correlation_multiplier: number;
  member_finding_ids: string[];
  rationale: string;
}

export interface Recommendation {
  recommendation_id: string;
  risk_id: string | null;
  finding_ids: string[];
  title: string;
  problem: string;
  affected_component: string;
  why_it_matters: string;
  proposed_fix: string;
  estimated_risk: { priority?: Priority; score?: number };
  verification_status: string;
  expected_benefit: string;
  implementation_difficulty: string;
  priority: Priority;
}

export interface ActionProposal {
  action_id: string;
  recommendation_id: string | null;
  action_type: "github_issue" | "pull_request";
  title: string;
  body: string;
  patch: string | null;
  target_repository: string;
  status: string;
  requires_approval: boolean;
  approved_by: string | null;
  decision_note: string | null;
  result: Record<string, unknown>;
  risk_score: number | null;
  decided_at: string | null;
}

export interface ExecutionEvent {
  event_id: string;
  seq: number;
  sender: string;
  receiver: string;
  event_type: string;
  severity: "info" | "warning" | "error";
  message: string;
  correlation_id: string | null;
  payload: Record<string, unknown>;
  timestamp: string;
}

export interface InvestigationRequest {
  request_id: string;
  requested_by: string;
  target_agent: string | null;
  objective: string;
  reason: string;
  required_evidence: string;
  status: string;
  decision_reason: string | null;
  created_at: string;
}

export interface Health {
  status: string;
  version: string;
  mode: string;
  llm_provider: string;
  demo_mode: boolean;
  dry_run: boolean;
  offline: boolean;
  sandbox_execution: boolean;
  github_token_configured: boolean;
  auth_required?: boolean;
  demo_public?: boolean;
  rate_limit_per_minute?: number;
}

export interface InvestigationBundle {
  detail: InvestigationDetail;
  agents: AgentRun[];
  findings: Finding[];
  evidence: Evidence[];
  correlations: Correlation[];
  verifications: Verification[];
  risks: Risk[];
  recommendations: Recommendation[];
  actions: ActionProposal[];
  events: ExecutionEvent[];
  requests: InvestigationRequest[];
}
