import type { AgentRun, InvestigationBundle } from "../../types/api";

export interface AgentState {
  agent: string;
  runs: AgentRun[];
  state: string; // a key understood by StatusBadge
  label: string;
}

/** Derive an agent's state from its persisted runs, e.g. "Failed → retrying" or "Recovered". */
export function agentState(agent: string, data: InvestigationBundle): AgentState {
  const runs = data.agents.filter((r) => r.agent === agent);
  const terminal = !["queued", "running"].includes(data.detail.status);
  const skipped = data.detail.plan?.skipped?.find((s) => s.agent === agent);
  const cov = data.detail.coverage?.agents?.[agent];
  if (!runs.length) {
    if (skipped) return { agent, runs, state: "skipped", label: "Skipped" };
    return terminal ? { agent, runs, state: "not_run", label: "Not run" } : { agent, runs, state: "waiting", label: "Waiting" };
  }
  const last = runs[runs.length - 1];
  const failedBefore = runs.slice(0, -1).some((r) => r.status === "failed" || r.status === "timeout");
  if (last.status === "running" || last.status === "pending") {
    return { agent, runs, state: failedBefore ? "retrying" : "running", label: failedBefore ? "Failed → retrying" : "Running" };
  }
  if (last.status === "failed" || last.status === "timeout") {
    return { agent, runs, state: "failed", label: terminal ? "Failed · unavailable" : "Failed" };
  }
  if (last.status === "cancelled") return { agent, runs, state: "cancelled", label: "Cancelled" };
  if (terminal && cov?.status === "partial") {
    return { agent, runs, state: "partial", label: failedBefore ? "Recovered · partial" : "Done · partial" };
  }
  return { agent, runs, state: "completed", label: failedBefore ? "Recovered" : "Done" };
}
