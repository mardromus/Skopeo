import { SEV_COLOR } from "../lib/format";
import type { Priority, Severity } from "../types/api";

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className="tag sev" style={{ ["--c" as string]: SEV_COLOR[severity] }} title={`Severity: ${severity}`}>
      {severity}
    </span>
  );
}

type Tone = "ok" | "bad" | "warn" | "run" | "neutral";

const STATES: Record<string, { tone: Tone; glyph: string; label: string }> = {
  verified: { tone: "ok", glyph: "✓", label: "Verified" },
  completed: { tone: "ok", glyph: "✓", label: "Completed" },
  complete: { tone: "ok", glyph: "✓", label: "Complete" },
  resolved: { tone: "ok", glyph: "✓", label: "Resolved" },
  approved_dry_run: { tone: "ok", glyph: "✓", label: "Approved · dry run" },
  executed: { tone: "ok", glyph: "✓", label: "Executed" },
  rejected: { tone: "bad", glyph: "✕", label: "Rejected" },
  failed: { tone: "bad", glyph: "✕", label: "Failed" },
  timeout: { tone: "bad", glyph: "✕", label: "Timed out" },
  unavailable: { tone: "bad", glyph: "✕", label: "Unavailable" },
  needs_more_evidence: { tone: "warn", glyph: "?", label: "Insufficient evidence" },
  partial: { tone: "warn", glyph: "~", label: "Partial" },
  completed_with_limitations: { tone: "warn", glyph: "~", label: "Completed with limitations" },
  retrying: { tone: "warn", glyph: "↻", label: "Failed → retrying" },
  cancelled: { tone: "warn", glyph: "■", label: "Cancelled" },
  running: { tone: "run", glyph: "●", label: "Running" },
  queued: { tone: "run", glyph: "○", label: "Queued" },
  waiting: { tone: "neutral", glyph: "○", label: "Waiting" },
  challenged: { tone: "run", glyph: "●", label: "Under challenge" },
  proposed: { tone: "neutral", glyph: "·", label: "Proposed" },
  correlated: { tone: "neutral", glyph: "·", label: "Correlated" },
  skipped: { tone: "neutral", glyph: "–", label: "Skipped" },
  not_run: { tone: "neutral", glyph: "–", label: "Not run" },
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const s = STATES[status] ?? { tone: "neutral" as Tone, glyph: "·", label: status.replace(/_/g, " ") };
  return (
    <span className={`tag ${s.tone}`}>
      <span className="glyph" aria-hidden>
        {s.glyph}
      </span>
      {label ?? s.label}
    </span>
  );
}

export function PriorityBadge({ priority }: { priority: Priority }) {
  return (
    <span className={`tag prio ${priority.toLowerCase()}`} title={`Priority ${priority}`}>
      {priority}
    </span>
  );
}

export function ConfidenceBar({ value }: { value: number }) {
  return (
    <span className="conf" title={`Confidence ${Math.round(value * 100)}%`}>
      <i>
        <span style={{ width: `${Math.max(2, value * 100)}%` }} />
      </i>
      {Math.round(value * 100)}%
    </span>
  );
}
