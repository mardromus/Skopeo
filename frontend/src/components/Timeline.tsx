import { Fragment, useMemo, useState } from "react";
import { EVENT_COLORS, fmtTimeMs, shortAgent } from "../lib/format";
import type { ExecutionEvent } from "../types/api";

const GROUPS: Record<string, string[]> = {
  "Planning and replanning": ["investigation_started", "repository_prepared", "plan_created", "replan", "orchestrator_decision", "request_decided"],
  "Agent lifecycle": ["agent_started", "agent_completed", "agent_failed", "agent_retry_scheduled"],
  "Messages and requests": ["agent_message", "investigation_requested"],
  Evidence: ["finding_created", "evidence_added", "tool_executed", "finding_updated"],
  Correlation: ["correlation_created", "correlation_updated"],
  Verification: ["verification_started", "challenge", "finding_verified", "finding_rejected", "verification_completed"],
  "Risk and actions": ["risk_assessed", "recommendation_created", "github_action_proposed", "human_approval_required", "action_decided"],
  Outcome: ["investigation_completed", "investigation_failed", "investigation_cancelled"],
};

/** The persisted execution trace, rendered like a log. Click a message to see its payload. */
export function Timeline({ events, compact = false }: { events: ExecutionEvent[]; compact?: boolean }) {
  const [group, setGroup] = useState("all");
  const [agent, setAgent] = useState("all");
  const [query, setQuery] = useState("");
  const [openSeq, setOpenSeq] = useState<number | null>(null);
  const agents = useMemo(() => Array.from(new Set(events.map((e) => e.sender))).sort(), [events]);
  const shown = events.filter(
    (e) =>
      (group === "all" || GROUPS[group].includes(e.event_type)) &&
      (agent === "all" || e.sender === agent || e.receiver === agent) &&
      (!query || `${e.message} ${e.event_type}`.toLowerCase().includes(query.toLowerCase())),
  );
  const rows = compact ? shown.slice(-12) : shown;
  return (
    <div>
      {!compact && (
        <div className="filters" style={{ gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr) minmax(0,2fr)" }}>
          <select id="trace-group" className="input" value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Event type">
            <option value="all">All event types</option>
            {Object.keys(GROUPS).map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
          <select id="trace-agent" className="input" value={agent} onChange={(e) => setAgent(e.target.value)} aria-label="Agent">
            <option value="all">All agents</option>
            {agents.map((a) => (
              <option key={a} value={a}>
                {shortAgent(a)}
              </option>
            ))}
          </select>
          <input id="trace-search" className="input" placeholder="Search messages" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
      )}
      <div className="trace">
        {rows.map((e) => (
          <Fragment key={e.event_id}>
            <div className={`trace-row ${e.severity} ${openSeq === e.seq ? "open" : ""}`}>
              <span className="seq">{String(e.seq).padStart(3, "0")}</span>
              <span className="t">{fmtTimeMs(e.timestamp)}</span>
              <span className="route" title={`${e.sender} → ${e.receiver}`}>
                {shortAgent(e.sender)} <i>→</i> {shortAgent(e.receiver)}
              </span>
              <span className="et" style={{ ["--c" as string]: EVENT_COLORS[e.event_type] ?? "var(--ink-2)" }}>
                {e.event_type}
              </span>
              {compact ? (
                <span className="m">{e.message}</span>
              ) : (
                <button className="m" onClick={() => setOpenSeq(openSeq === e.seq ? null : e.seq)} aria-expanded={openSeq === e.seq}>
                  {e.message}
                </button>
              )}
            </div>
            {openSeq === e.seq && <pre className="trace-payload">{JSON.stringify(e.payload, null, 2)}</pre>}
          </Fragment>
        ))}
        {rows.length === 0 && <div className="empty" style={{ padding: 14 }}>No events match.</div>}
      </div>
      <div className="small muted" style={{ marginTop: 8 }}>
        {compact ? `Last ${rows.length} of ${events.length} events.` : `${shown.length} of ${events.length} events.`} Read from the execution_events table; nothing here is generated for display.
      </div>
    </div>
  );
}
