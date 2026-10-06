import type { Severity } from "../types/api";

export const AGENT_NAMES: Record<string, string> = {
  orchestrator: "Orchestrator",
  security_agent: "Security Agent",
  dependency_agent: "Dependency Health Agent",
  code_quality_agent: "Code Quality Agent",
  api_compatibility_agent: "API Compatibility Agent",
  test_reliability_agent: "Test Reliability Agent",
  license_agent: "License Compliance Agent",
  maintenance_agent: "Maintenance Activity Agent",
  performance_agent: "Performance Agent",
  correlation_agent: "Correlation Agent",
  verification_agent: "Verification / Red-Team Agent",
  risk_agent: "Risk Assessment Agent",
  recommendation_agent: "Recommendation Agent",
  human: "Human reviewer",
  blackboard: "Evidence Store",
  all_agents: "All agents",
};

export const SPECIALISTS = [
  "security_agent",
  "dependency_agent",
  "code_quality_agent",
  "api_compatibility_agent",
  "test_reliability_agent",
  "license_agent",
  "maintenance_agent",
  "performance_agent",
];

export const COORDINATORS = ["orchestrator", "correlation_agent", "verification_agent", "risk_agent", "recommendation_agent"];

export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"];

export const SEV_COLOR: Record<Severity, string> = {
  critical: "var(--crit)",
  high: "var(--high)",
  medium: "var(--med)",
  low: "var(--low)",
  info: "var(--info)",
};

export function agentName(id: string): string {
  return AGENT_NAMES[id] ?? id.replace(/_/g, " ");
}

export function shortAgent(id: string): string {
  return agentName(id).replace(" Agent", "").replace("Verification / Red-Team", "Red-Team");
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function fmtTimeMs(iso: string): string {
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return `${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}.${String(d.getMilliseconds()).padStart(3, "0")}`;
}

export function toMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  return new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`).getTime();
}

export function fmtDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

export function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

export function statusLabel(s: string): string {
  return s.replace(/_/g, " ").toUpperCase();
}

/** Trace colouring by event family (text colour only; the event name is always printed). */
export const EVENT_COLORS: Record<string, string> = {
  plan_created: "var(--signal)",
  replan: "var(--signal)",
  orchestrator_decision: "var(--signal)",
  request_decided: "var(--signal)",
  investigation_requested: "var(--signal)",
  agent_failed: "var(--bad)",
  agent_retry_scheduled: "var(--warn)",
  finding_rejected: "var(--bad)",
  finding_verified: "var(--ok)",
  verification_completed: "var(--warn)",
  challenge: "var(--warn)",
  correlation_created: "var(--ink)",
  investigation_completed: "var(--ok)",
  investigation_failed: "var(--bad)",
  human_approval_required: "var(--warn)",
};

/** Short case number derived from the investigation UUID. */
export function caseNo(id: string): string {
  return `SK-${id.slice(0, 4).toUpperCase()}`;
}
