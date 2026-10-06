import type {
  ActionProposal,
  AgentRun,
  Correlation,
  Evidence,
  ExecutionEvent,
  Finding,
  Health,
  InvestigationDetail,
  InvestigationRequest,
  InvestigationSummary,
  Recommendation,
  Risk,
  Verification,
} from "../types/api";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : (body.detail ?? []).map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/health"),
  list: () => request<InvestigationSummary[]>("/investigations?limit=30"),
  create: (body: { repository_url: string; branch: string; analysis_depth: string; enable_github_actions: boolean }) =>
    request<InvestigationSummary>("/investigations", { method: "POST", body: JSON.stringify(body) }),
  createDemo: (body: { fault_injection: boolean; analysis_depth?: string }) =>
    request<InvestigationSummary>("/demo/investigations", { method: "POST", body: JSON.stringify(body) }),
  detail: (id: string) => request<InvestigationDetail>(`/investigations/${id}`),
  agents: (id: string) => request<AgentRun[]>(`/investigations/${id}/agents`),
  findings: (id: string) => request<Finding[]>(`/investigations/${id}/findings`),
  evidence: (id: string) => request<Evidence[]>(`/investigations/${id}/evidence`),
  correlations: (id: string) => request<Correlation[]>(`/investigations/${id}/correlations`),
  verifications: (id: string) => request<Verification[]>(`/investigations/${id}/verifications`),
  risks: (id: string) => request<Risk[]>(`/investigations/${id}/risks`),
  recommendations: (id: string) => request<Recommendation[]>(`/investigations/${id}/recommendations`),
  actions: (id: string) => request<ActionProposal[]>(`/investigations/${id}/actions`),
  requests: (id: string) => request<InvestigationRequest[]>(`/investigations/${id}/requests`),
  events: (id: string, afterSeq = 0) => request<ExecutionEvent[]>(`/investigations/${id}/events?after_seq=${afterSeq}`),
  cancel: (id: string) => request<{ cancel_requested: boolean }>(`/investigations/${id}/cancel`, { method: "POST" }),
  approve: (id: string, body: { action_id: string; decision: "approve" | "reject"; approved_by: string; note?: string }) =>
    request<ActionProposal>(`/investigations/${id}/approve-action`, { method: "POST", body: JSON.stringify(body) }),
  reportUrl: (id: string, format: "json" | "markdown") => `${BASE}/api/investigations/${id}/report?format=${format}`,
};
