import { useEffect, useState } from "react";
import { StatusBadge } from "../../components/Badges";
import { Gantt } from "../../components/Gantt";
import { agentName, fmtDuration, fmtTime } from "../../lib/format";
import type { InvestigationBundle } from "../../types/api";

export function AgentsTab({ data }: { data: InvestigationBundle }) {
  const [now, setNow] = useState(() => Date.now());
  const running = ["queued", "running"].includes(data.detail.status);
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [running]);
  return (
    <div>
      <section className="section">
        <div className="section-head">
          <h2>Timeline</h2>
          <span className="note">one row per run; overlapping bars ran in parallel</span>
        </div>
        <Gantt runs={data.agents} now={now} />
      </section>
      <section className="section">
        <div className="section-head">
          <h2>Runs</h2>
          <span className="note">{data.agents.length} runs, in the order they were scheduled</span>
        </div>
        <div className="table-wrap">
          <table className="ledger">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Task</th>
                <th>Why it ran</th>
                <th className="r">Round</th>
                <th>Result</th>
                <th className="r">Time</th>
                <th className="r">Steps</th>
                <th className="r">Tools</th>
                <th className="r">Findings</th>
              </tr>
            </thead>
            <tbody>
              {data.agents.map((r) => (
                <tr key={r.run_id}>
                  <td style={{ whiteSpace: "nowrap" }}>{agentName(r.agent)}</td>
                  <td className="minw0" style={{ maxWidth: 420 }}>
                    <div className="wrap-any">{r.objective}</div>
                    {r.summary && <div className="small muted">{r.summary}</div>}
                    {r.error_message && (
                      <div className="small" style={{ color: "var(--bad)" }}>
                        {r.error_type}: {r.error_message}
                      </div>
                    )}
                    {(r.coverage?.limitations ?? []).length > 0 && <div className="small" style={{ color: "var(--warn)" }}>{(r.coverage.limitations ?? []).join(" · ")}</div>}
                  </td>
                  <td>
                    <span className="chip">{r.trigger.replace(/_/g, " ")}</span>
                    {r.mode !== "full" && (
                      <div>
                        <span className="chip">{r.mode}</span>
                      </div>
                    )}
                    {r.strategy !== "default" && (
                      <div>
                        <span className="chip">{r.strategy}</span>
                      </div>
                    )}
                  </td>
                  <td className="r">{r.round}</td>
                  <td>
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="r" title={`started ${fmtTime(r.started_at)}`}>
                    {fmtDuration(r.duration_ms)}
                  </td>
                  <td className="r">{r.iterations}</td>
                  <td className="r">{r.tool_calls}</td>
                  <td className="r">{r.findings_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
