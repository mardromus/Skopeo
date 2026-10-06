import { shortAgent } from "../lib/format";
import type { Correlation, Finding } from "../types/api";
import { SeverityBadge, StatusBadge } from "./Badges";

const TYPE_LABEL: Record<Correlation["relationship_type"], string> = {
  compound_risk: "Compound risk",
  duplicate: "Duplicate",
  contradiction: "Contradiction",
  dependency: "Dependency link",
  causal: "Causal chain",
  shared_root_cause: "Shared root cause",
};

/** A relationship the correlation agent found between findings from different agents. */
export function CorrelationChain({ c, findings }: { c: Correlation; findings: Record<string, Finding> }) {
  const members = c.finding_ids.map((id) => findings[id]).filter(Boolean);
  const agents = new Set(members.map((m) => m.agent)).size;
  return (
    <section className="corr">
      <div className="row between" style={{ alignItems: "flex-start" }}>
        <div className="minw0">
          <span className="eyebrow">
            {TYPE_LABEL[c.relationship_type]} · {members.length} findings from {agents} agent{agents === 1 ? "" : "s"}
          </span>
          <h3 style={{ fontSize: 16, marginTop: 4 }}>{c.title}</h3>
        </div>
        <div className="row">
          {c.risk_multiplier !== 1 && <span className="chip">risk ×{c.risk_multiplier.toFixed(2)}</span>}
          <span className="chip">confidence {Math.round(c.confidence * 100)}%</span>
          <StatusBadge status={c.status} />
        </div>
      </div>
      <div className="corr-members">
        {members.map((m) => (
          <div key={m.finding_id} className="member">
            <div className="row between">
              <span className="who">{shortAgent(m.agent)}</span>
              <SeverityBadge severity={m.severity} />
            </div>
            <div className="wrap-any" style={{ fontWeight: 500 }}>
              {m.title.replace(/ — (STATIC SUSPECT|MEASURED.*)$/, "")}
            </div>
            <div>
              <StatusBadge status={m.status} />
            </div>
          </div>
        ))}
      </div>
      <p className="corr-result">
        <b>Correlation agent:</b> {c.description}
      </p>
      {c.resolution && (
        <p className="corr-result">
          <b>Resolution:</b> {c.resolution}
        </p>
      )}
      <p className="small muted" style={{ margin: "6px 0 0" }}>
        {c.reasoning_summary}
      </p>
    </section>
  );
}
