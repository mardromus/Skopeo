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
import type {
  AccountUser,
  AuthConfig,
  Channel,
  ChatAgent,
  ChatMessage,
  GitHubConnection,
  GitHubRepoPage,
  ChannelCreated,
  Delivery,
  Frequency,
  NotificationCatalog,
  Project,
  ProjectFileInfo,
  ReportSummary,
  Rule,
  Watch,
  WatchReport,
} from "../types/account";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const KEY_STORAGE = "skopeo-access-key";

/** Access key for servers started with SKOPEO_API_KEY; kept in this browser only. */
export function getAccessKey(): string {
  try {
    return localStorage.getItem(KEY_STORAGE) ?? "";
  } catch {
    return "";
  }
}

export function setAccessKey(key: string): void {
  try {
    if (key) localStorage.setItem(KEY_STORAGE, key);
    else localStorage.removeItem(KEY_STORAGE);
  } catch {
    /* storage unavailable: the key is not remembered */
  }
}

/** Supplies the signed-in user's Firebase ID token (refreshed by the SDK); null when signed out. */
let idTokenProvider: (() => Promise<string | null>) | null = null;

export function setIdTokenProvider(provider: (() => Promise<string | null>) | null): void {
  idTokenProvider = provider;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const key = getAccessKey();
  const token = idTokenProvider ? await idTokenProvider().catch(() => null) : null;
  const res = await fetch(`${BASE}/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(key ? { "X-Skopeo-Key": key } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
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
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (method: string, body?: unknown): RequestInit => ({ method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });

export const api = {
  health: () => request<Health>("/health"),
  list: (mine = false) => request<InvestigationSummary[]>(`/investigations?limit=30${mine ? "&mine=true" : ""}`),
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

export const accountApi = {
  config: () => request<AuthConfig>("/auth/config"),
  me: () => request<AccountUser>("/auth/me"),
  deleteMe: () => request<void>("/auth/me", json("DELETE")),
};

export const githubApi = {
  connection: () => request<GitHubConnection>("/github/connection"),
  connect: (access_token: string, source: "oauth" | "pat") => request<GitHubConnection>("/github/connect", json("POST", { access_token, source })),
  disconnect: () => request<void>("/github/connection", json("DELETE")),
  repos: (q = "", page = 1) => request<GitHubRepoPage>(`/github/repos?q=${encodeURIComponent(q)}&page=${page}`),
  importRepo: (body: { full_name: string; target: "investigation" | "project"; branch?: string; analysis_depth?: string; project_name?: string }) =>
    request<{ target: "investigation"; investigation: InvestigationSummary } | { target: "project"; project: Project }>("/github/import", json("POST", body)),
};

export const chatApi = {
  agents: () => request<ChatAgent[]>("/chat/agents"),
  history: (id: string) => request<{ messages: ChatMessage[] }>(`/investigations/${id}/chat`),
  ask: (id: string, question: string, agent?: string) =>
    request<{ question: ChatMessage; answer: ChatMessage }>(`/investigations/${id}/chat`, json("POST", { question, ...(agent ? { agent } : {}) })),
  clear: (id: string) => request<void>(`/investigations/${id}/chat`, json("DELETE")),
};

export const notificationsApi = {
  catalog: () => request<NotificationCatalog>("/notifications/catalog"),
  channels: () => request<Channel[]>("/notifications/channels"),
  createChannel: (body: { kind: string; name: string; target: string; events: string[] }) =>
    request<ChannelCreated>("/notifications/channels", json("POST", body)),
  updateChannel: (id: string, body: { name?: string; enabled?: boolean; events?: string[] }) =>
    request<Channel>(`/notifications/channels/${id}`, json("PATCH", body)),
  deleteChannel: (id: string) => request<void>(`/notifications/channels/${id}`, json("DELETE")),
  verify: (id: string, code: string) => request<Channel>(`/notifications/channels/${id}/verify`, json("POST", { code })),
  resend: (id: string) => request<{ verification_sent: boolean; verification_error?: string; dev_verification_code?: string }>(`/notifications/channels/${id}/resend`, json("POST")),
  test: (id: string) => request<{ status: string; error?: string }>(`/notifications/channels/${id}/test`, json("POST")),
  rotateSecret: (id: string) => request<{ channel: Channel; signing_secret: string }>(`/notifications/channels/${id}/rotate-secret`, json("POST")),
  rules: () => request<Rule[]>("/notifications/rules"),
  createRule: (body: { event: string; channel_ids: string[]; filters: Record<string, string>; enabled?: boolean }) =>
    request<Rule>("/notifications/rules", json("POST", body)),
  updateRule: (id: string, body: { channel_ids?: string[]; filters?: Record<string, string>; enabled?: boolean }) =>
    request<Rule>(`/notifications/rules/${id}`, json("PATCH", body)),
  deleteRule: (id: string) => request<void>(`/notifications/rules/${id}`, json("DELETE")),
  deliveries: () => request<Delivery[]>("/notifications/deliveries?limit=60"),
};

export interface ProjectFileUpload {
  path: string;
  content: string;
}

export const projectsApi = {
  list: () => request<Project[]>("/projects"),
  get: (id: string) => request<Project>(`/projects/${id}`),
  create: (body: { name: string; notes: string; source: "github" | "upload"; repository_url?: string; branch?: string; files: ProjectFileUpload[] }) =>
    request<Project>("/projects", json("POST", body)),
  update: (id: string, body: { name?: string; notes?: string; repository_url?: string; branch?: string }) => request<Project>(`/projects/${id}`, json("PATCH", body)),
  remove: (id: string) => request<void>(`/projects/${id}`, json("DELETE")),
  files: (id: string) => request<ProjectFileInfo[]>(`/projects/${id}/files`),
  putFiles: (id: string, files: ProjectFileUpload[], replace = false) => request<Project>(`/projects/${id}/files`, json("PUT", { files, replace })),
  deleteFile: (id: string, path: string) => request<Project>(`/projects/${id}/files?path=${encodeURIComponent(path)}`, json("DELETE")),
  createWatch: (
    projectId: string,
    body: { upstream_url: string; branch?: string; package_name?: string; import_names?: string[]; ecosystem?: string; frequency: Frequency },
  ) => request<Watch>(`/projects/${projectId}/watches`, json("POST", body)),
  watch: (id: string) => request<Watch>(`/watches/${id}`),
  updateWatch: (id: string, body: { frequency?: Frequency; enabled?: boolean; package_name?: string; import_names?: string[]; branch?: string }) =>
    request<Watch>(`/watches/${id}`, json("PATCH", body)),
  deleteWatch: (id: string) => request<void>(`/watches/${id}`, json("DELETE")),
  check: (id: string, fromPinned = false) => request<{ queued: boolean; watch: Watch }>(`/watches/${id}/check${fromPinned ? "?from_pinned=true" : ""}`, json("POST")),
  reports: (id: string) => request<ReportSummary[]>(`/watches/${id}/reports`),
  report: (id: string) => request<WatchReport>(`/watch-reports/${id}`),
};
