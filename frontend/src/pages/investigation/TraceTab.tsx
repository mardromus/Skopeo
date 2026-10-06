import { StatusBadge } from "../../components/Badges";
import { Timeline } from "../../components/Timeline";
import { agentName } from "../../lib/format";
import type { InvestigationBundle } from "../../types/api";

export function TraceTab({ data }: { data: InvestigationBundle }) {
  return (
    <div>
      <section className="section">
        <Timeline events={data.events} />
      </section>
      <section className="section">
        <div className="section-head">
          <h2>Investigation requests</h2>
          <span className="note">agents ask for more work on the evidence board; the orchestrator decides</span>
        </div>
        {data.requests.length === 0 ? (
          <p className="empty">No requests yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="ledger">
              <thead>
                <tr>
                  <th>From</th>
                  <th>Asks for</th>
                  <th>Objective</th>
                  <th>Decision</th>
                </tr>
              </thead>
              <tbody>
                {data.requests.map((r) => (
                  <tr key={r.request_id}>
                    <td style={{ whiteSpace: "nowrap" }}>{agentName(r.requested_by)}</td>
                    <td>
                      <span className="chip">{r.required_evidence.replace(/_/g, " ")}</span>
                    </td>
                    <td className="ink2">{r.objective}</td>
                    <td>
                      <StatusBadge status={r.status === "fulfilled" ? "completed" : r.status === "declined" ? "skipped" : r.status === "accepted" ? "running" : "waiting"} label={r.status} />
                      {r.decision_reason && <div className="small muted">{r.decision_reason}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
