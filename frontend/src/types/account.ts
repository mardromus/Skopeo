export interface FirebaseWebConfig {
  apiKey: string;
  authDomain: string;
  projectId: string;
  appId: string | null;
  sdkVersion: string;
}

export interface AuthConfig {
  mode: "firebase" | "local";
  firebase: FirebaseWebConfig | null;
  require_login: boolean;
  email_configured: boolean;
  public_base_url: string | null;
  providers?: AuthProviderId[];
  github?: { enabled: boolean; private_repos: boolean };
}

export type AuthProviderId = "google" | "github";

export interface GitHubConnection {
  connected: boolean;
  login?: string;
  avatar_url?: string | null;
  scopes?: string[];
  source?: "oauth" | "pat";
  private_repos?: boolean;
  connected_at?: string;
  private_repos_enabled?: boolean;
}

export interface GitHubRepo {
  full_name: string;
  html_url: string;
  description: string;
  private: boolean;
  fork: boolean;
  archived: boolean;
  default_branch: string;
  language: string | null;
  stars: number;
  pushed_at: string | null;
}

export interface GitHubRepoPage {
  repos: GitHubRepo[];
  page: number;
  has_more: boolean;
  private_repos: boolean;
}

export interface ChatCitation {
  finding_id: string;
  title: string;
  severity: string;
  agent: string;
  file: string | null;
}

export interface ChatMessage {
  message_id: string;
  role: "user" | "agent";
  agent: string | null;
  agent_display_name: string | null;
  content: string;
  citations: ChatCitation[];
  routing_reason: string | null;
  routed_by: string | null;
  follow_ups: string[];
  decided_by: string | null;
  created_at: string;
}

export interface ChatAgent {
  name: string;
  display_name: string;
  category: string | null;
  examples: string[];
}

export interface AccountUser {
  user_id: string;
  email: string | null;
  email_verified: boolean;
  display_name: string | null;
  photo_url: string | null;
  provider: string;
  created_at: string;
  last_login_at: string | null;
}

export type ChannelKind = "email" | "slack" | "discord" | "webhook";

export interface Channel {
  channel_id: string;
  kind: ChannelKind;
  name: string;
  target: string;
  verified: boolean;
  enabled: boolean;
  has_signing_secret: boolean;
  signing_secret_hint: string | null;
  last_used_at: string | null;
  last_error: string | null;
  created_at: string;
  events: string[];
}

export interface ChannelCreated {
  channel: Channel;
  signing_secret: string | null;
  verification_sent: boolean;
  verification_error?: string;
  dev_verification_code?: string;
}

export interface NotificationEventInfo {
  event: string;
  label: string;
  description: string;
  filters: string[];
}

export interface NotificationCatalog {
  events: NotificationEventInfo[];
  channel_kinds: { kind: ChannelKind; label: string }[];
  email_configured: boolean;
  dry_run: boolean;
  default_subscriptions: string[];
  priorities: string[];
  impact_levels: string[];
}

export interface Rule {
  rule_id: string;
  event: string;
  channel_ids: string[];
  filters: Record<string, string>;
  enabled: boolean;
  created_at: string;
}

export interface Delivery {
  delivery_id: string;
  channel_id: string | null;
  rule_id: string | null;
  event: string;
  subject: string;
  status: "sent" | "failed" | "skipped" | "dry_run";
  error: string | null;
  created_at: string;
}

export type ImpactLevel = "none" | "low" | "medium" | "high" | "breaking";

export interface ReportSummary {
  report_id: string;
  watch_id: string;
  kind: "baseline" | "update" | "recheck";
  trigger: string;
  base_ref: string | null;
  head_ref: string | null;
  head_sha: string | null;
  impact_level: ImpactLevel;
  summary: string;
  stats: ReportStats;
  created_at: string;
}

export interface ReportStats {
  changes?: number;
  changes_by_kind?: Record<string, number>;
  breaking_changes?: number;
  impacts?: number;
  impacts_by_level?: Record<string, number>;
  affected_files?: number;
  usages?: number;
  files_using_library?: number;
  commits?: number;
  upstream_version?: string | null;
  pinned?: { manifest: string; spec: string; version: string | null; floor: string | null; line?: number } | null;
  package_name?: string | null;
  import_names?: string[];
  ecosystem?: string;
}

export interface Impact {
  level: ImpactLevel;
  certainty: "certain" | "likely" | "possible";
  title: string;
  explanation: string;
  suggestion: string;
  file: string;
  line: number;
  snippet: string;
  usage_kind: string;
  symbol: string;
  change: { kind: string; severity: string; symbol: string; detail?: string; old_signature?: string; new_signature?: string; new_name?: string };
}

export interface UpstreamChange {
  kind: string;
  severity: "breaking" | "deprecation" | "behavior" | "info";
  symbol: string;
  names: string[];
  detail?: string;
  old_signature?: string;
  new_signature?: string;
  new_name?: string;
  file?: string;
  line?: number;
}

export interface WatchReport extends ReportSummary {
  base_sha: string | null;
  narrative: { summary: string; actions: string[]; decided_by: string; changelog: string[] };
  commits: { sha: string; author: string; date: string; message: string }[];
  upstream_changes: UpstreamChange[];
  impacts: Impact[];
  usages: { symbol: string; uses: number; files: string[] }[];
}

export type Frequency = "hourly" | "daily" | "weekly" | "manual";

export interface Watch {
  watch_id: string;
  project_id: string;
  upstream_url: string;
  upstream_name: string;
  branch: string | null;
  package_name: string | null;
  import_names: string[];
  ecosystem: string | null;
  frequency: Frequency;
  enabled: boolean;
  status: "pending" | "checking" | "ok" | "failed";
  last_error: string | null;
  last_checked_at: string | null;
  next_check_at: string | null;
  last_seen_sha: string | null;
  last_seen_version: string | null;
  created_at: string;
  latest_report: ReportSummary | null;
}

export interface Project {
  project_id: string;
  name: string;
  notes: string;
  source: "github" | "upload";
  repository_url: string | null;
  branch: string;
  file_count: number;
  total_bytes: number;
  created_at: string;
  updated_at: string;
  watches: Watch[];
}

export interface ProjectFileInfo {
  path: string;
  size: number;
  sha256: string;
  created_at: string;
}
