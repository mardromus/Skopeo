import { COORDINATORS, fmtDuration, shortAgent, toMs } from "../lib/format";
import type { AgentRun } from "../types/api";

/** Every agent run on one time axis: parallel work, failures and retries are visible at a glance. */
export function Gantt({ runs, now }: { runs: AgentRun[]; now: number }) {
  const rows = runs.filter((r) => r.agent !== "orchestrator" && r.started_at);
  if (!rows.length) return <div className="empty">No agent has started yet.</div>;
  const t0 = Math.min(...rows.map((r) => toMs(r.started_at)!));
  const t1 = Math.max(...rows.map((r) => toMs(r.completed_at) ?? now), t0 + 1000);
  const span = t1 - t0;
  return (
    <div>
      <div className="gantt" role="table" aria-label="Agent run timeline">
        {rows.map((r) => {
          const s = toMs(r.started_at)!;
          const e = toMs(r.completed_at) ?? now;
          const cls = r.status === "running" ? "running" : r.status === "failed" || r.status === "timeout" ? "failed" : COORDINATORS.includes(r.agent) ? "coord" : "";
          const label = `${shortAgent(r.agent)}${r.mode !== "full" ? ` · ${r.mode}` : ""}${r.trigger === "retry" ? " · retry" : ""}`;
          return (
            <div className="gantt-row" role="row" key={r.run_id}>
              <div className="gantt-label" title={r.objective}>
                {label}
              </div>
              <div className="gantt-track">
                <div
                  className={`gantt-bar ${cls}`}
                  style={{ left: `${((s - t0) / span) * 100}%`, width: `${Math.max(0.5, ((e - s) / span) * 100)}%` }}
                  title={`${label} — ${r.status} in ${fmtDuration(r.duration_ms)}\n${r.objective}${r.error_message ? `\n${r.error_type}: ${r.error_message}` : ""}`}
                />
              </div>
            </div>
          );
        })}
      </div>
      <div className="gantt-axis">
        <span />
        <div className="row between">
          <span>0 s</span>
          <span>{fmtDuration(span / 2)}</span>
          <span>{fmtDuration(span)}</span>
        </div>
      </div>
      <div className="legend">
        <span>
          <i style={{ background: "var(--ink-2)" }} />
          specialist
        </span>
        <span>
          <i style={{ background: "var(--signal)" }} />
          correlation · red-team · risk · recommendation
        </span>
        <span>
          <i style={{ background: "repeating-linear-gradient(135deg, var(--bad) 0 3px, transparent 3px 6px)", outline: "1px solid var(--bad)" }} />
          failed run
        </span>
      </div>
    </div>
  );
}
