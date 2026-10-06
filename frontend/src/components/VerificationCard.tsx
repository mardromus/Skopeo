import { agentName } from "../lib/format";
import type { Evidence, Finding, Verification } from "../types/api";
import { SeverityBadge, StatusBadge } from "./Badges";

const GLYPH: Record<string, string> = { pass: "✓", fail: "✕", inconclusive: "?", not_applicable: "–" };

/** One adjudication: the agent's claim, the red-team's cross-examination, and the ruling. */
export function VerificationCard({ v, finding, evidence }: { v: Verification; finding: Finding; evidence: Evidence[] }) {
  const original = (finding.attributes?.original_severity as Finding["severity"] | undefined) ?? finding.severity;
  const first = evidence[0];
  return (
    <article className="case-card">
      <div>
        <span className="eyebrow">Claim · {agentName(finding.agent)}</span>
        <div className="row">
          <SeverityBadge severity={original} />
          <span className="chip">round {v.round}</span>
        </div>
        <h3>{finding.title.replace(/ — (STATIC SUSPECT|MEASURED.*)$/, "")}</h3>
        <div className="small ink2">{finding.reasoning_summary}</div>
        {first && (
          <div className="small">
            <code className="ink2">{first.file ?? first.source}</code>
            {first.excerpt && (
              <div className="mono muted wrap-any" style={{ marginTop: 3 }}>
                {first.excerpt.slice(0, 160)}
              </div>
            )}
          </div>
        )}
      </div>
      <div>
        <span className="eyebrow">Cross-examination</span>
        <p className="q" style={{ margin: 0 }}>
          {v.challenge}
        </p>
        <div className="checks">
          {v.checks.map((c, i) => (
            <div key={i} className={`chk ${c.outcome}`} title={c.question}>
              <span className="g">{GLYPH[c.outcome] ?? "·"}</span>
              <span>
                <code>{c.check}</code> {c.detail}
              </span>
            </div>
          ))}
        </div>
      </div>
      <div className={`ruling-col ${v.decision}`}>
        <span className="eyebrow">Ruling</span>
        <StatusBadge status={v.decision} />
        {v.adjusted_severity && v.adjusted_severity !== original && (
          <div className="small row">
            severity lowered to <SeverityBadge severity={v.adjusted_severity} />
          </div>
        )}
        <div className="small">{v.reasoning_summary}</div>
        <div className="small muted">
          {v.decision === "rejected" ? "Excluded from the risk report." : v.decision === "needs_more_evidence" ? "Follow-up requested from the orchestrator." : "Admitted to the risk report."}
        </div>
        <div className="small muted mono">decided by {v.decided_by}</div>
      </div>
    </article>
  );
}
