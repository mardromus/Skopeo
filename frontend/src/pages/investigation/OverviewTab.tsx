import { PriorityBadge, StatusBadge } from "../../components/Badges";
import { RiskScoreChart, SeverityChart } from "../../components/Charts";
import { Timeline } from "../../components/Timeline";
import { COORDINATORS, SPECIALISTS, shortAgent } from "../../lib/format";
import type { InvestigationBundle } from "../../types/api";
import { agentState } from "./agentStatus";

export function OverviewTab({ data, onNavigate }: { data: InvestigationBundle; onNavigate: (tab: string) => void }) {
  const plan = data.detail.plan ?? {};
  const coverage = data.detail.coverage?.agents ?? {};
  const s = data.detail.execution_summary ?? {};
  const order = [COORDINATORS[0], ...SPECIALISTS, ...COORDINATORS.slice(1)];
  return (
    <div>
      <div className="cols-3-2">
        <section className="section">
          <div className="section-head">
            <h2>Verified risks</h2>
            <button className="btn quiet sm" onClick={() => onNavigate("actions")}>
              See fixes
            </button>
          </div>
          {data.risks.length === 0 ? (
            <p className="empty">Risks are scored after the red team has ruled. Only verified findings are scored.</p>
          ) : (
            <div className="risk-list">
              {data.risks.slice(0, 7).map((r) => (
                <div key={r.risk_id} className="risk-item">
                  <PriorityBadge priority={r.priority} />
                  <div className="minw0">
                    <div style={{ fontWeight: 600 }} className="wrap-any">
                      {r.kind === "compound" && (
                        <span className="chip" style={{ marginRight: 6 }}>
                          compound
                        </span>
                      )}
                      {r.title.replace(/ — (STATIC SUSPECT|MEASURED.*)$/, "")}
                    </div>
                    <div className="why wrap-any">{r.rationale}</div>
                  </div>
                  <span className="score">{r.score.toFixed(1)}</span>
                </div>
              ))}
            </div>
          )}
        </section>
        <section className="section">
          <div className="section-head">
            <h2>Score by risk</h2>
            <span className="note">ticks mark the P3 · P2 · P1 · P0 thresholds</span>
          </div>
          {data.risks.length ? <RiskScoreChart risks={data.risks} /> : <p className="empty">Waiting for risk assessment.</p>}
          <div className="section-head" style={{ marginTop: 18 }}>
            <h2>Findings by severity</h2>
          </div>
          <SeverityChart findings={data.findings} />
        </section>
      </div>

      <div className="cols">
        <section className="section">
          <div className="section-head">
            <h2>Agents</h2>
            <button className="btn quiet sm" onClick={() => onNavigate("agents")}>
              Timeline
            </button>
          </div>
          <div className="table-wrap">
            <table className="ledger">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>State</th>
                  <th className="r">Runs</th>
                  <th className="r">Findings</th>
                </tr>
              </thead>
              <tbody>
                {order.map((a) => {
                  const st = agentState(a, data);
                  return (
                    <tr key={a} className={st.state === "skipped" ? "dim" : ""}>
                      <td>{shortAgent(a)}</td>
                      <td>
                        <StatusBadge status={st.state} label={st.label} />
                      </td>
                      <td className="r">{st.runs.length}</td>
                      <td className="r">{st.runs.reduce((n, r) => n + r.findings_count, 0) || ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
        <section className="section">
          <div className="section-head">
            <h2>Plan</h2>
            <span className="note">decided by {plan.decided_by ?? "…"}</span>
          </div>
          {plan.initial_tasks?.length ? (
            <div className="stack" style={{ gap: 6 }}>
              {plan.initial_tasks.map((t) => (
                <div key={t.agent} className="small">
                  <b>{shortAgent(t.agent)}</b> <span className="muted">{t.rationale}</span>
                </div>
              ))}
              {plan.skipped?.map((sk) => (
                <div key={sk.agent} className="small muted">
                  <s>{shortAgent(sk.agent)}</s> skipped: {sk.reason}
                </div>
              ))}
              {plan.revisions?.map((rev, i) => (
                <div key={i} className="callout small" style={{ marginTop: 4 }}>
                  <b>Replanned for round {rev.round}.</b> {rev.added.map((a) => `${shortAgent(a.agent)} (${a.mode}): ${a.objective}`).join("; ")}
                </div>
              ))}
            </div>
          ) : (
            <p className="empty">The orchestrator is planning.</p>
          )}
        </section>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>Coverage</h2>
          <span className="note">what each specialist could and could not examine</span>
        </div>
        {Object.keys(coverage).length === 0 ? (
          <p className="empty">Coverage is reported when the investigation finishes.</p>
        ) : (
          <div className="table-wrap">
            <table className="ledger">
              <tbody>
                {Object.entries(coverage).map(([agent, c]) => (
                  <tr key={agent}>
                    <td style={{ width: 170 }}>{shortAgent(agent)}</td>
                    <td style={{ width: 150 }}>
                      <StatusBadge status={c.status} />
                    </td>
                    <td className="ink2 small">{(c.limitations ?? []).slice(0, 3).join(" · ") || c.reason || "Full coverage."}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Latest events</h2>
          <button className="btn quiet sm" onClick={() => onNavigate("trace")}>
            Full trace
          </button>
        </div>
        {data.events.length ? <Timeline events={data.events} compact /> : <p className="empty">Waiting for the first event.</p>}
        <p className="small muted">
          Decisions: {s.llm?.decisions ?? 0} by {s.llm?.provider ?? "—"} · tool calls {String(s.tool_calls ?? "—")}
        </p>
      </section>
    </div>
  );
}
