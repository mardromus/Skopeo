import { useState } from "react";
import { SEV_COLOR, agentName, pct } from "../lib/format";
import type { Evidence, Finding, Verification } from "../types/api";
import { ConfidenceBar, SeverityBadge, StatusBadge } from "./Badges";

export function EvidenceBlock({ e }: { e: Evidence }) {
  const loc = e.file ? `${e.file}${e.line_start ? `:${e.line_start}${e.line_end && e.line_end !== e.line_start ? `–${e.line_end}` : ""}` : ""}` : null;
  return (
    <div className="evidence">
      <div className="evidence-head">
        <span className="chip">{e.source_type}</span>
        <span className="chip">{e.tool}</span>
        {loc && <code className="ink2">{loc}</code>}
        <span>collected by {agentName(e.created_by)}</span>
        <span style={{ marginLeft: "auto" }}>weight {pct(e.confidence)}</span>
      </div>
      {e.excerpt && <pre>{e.excerpt}</pre>}
      {e.raw_reference.startsWith("http") && (
        <div className="small" style={{ padding: "0 12px 8px" }}>
          <a href={e.raw_reference} target="_blank" rel="noreferrer noopener">
            {e.raw_reference}
          </a>
        </div>
      )}
    </div>
  );
}

const MEASURE: Record<string, string> = { measured: "measured", static_suspect: "static suspect", measured_no_issue: "measured · no issue" };

export function FindingCard({ f, evidence, verification }: { f: Finding; evidence: Evidence[]; verification?: Verification }) {
  const [open, setOpen] = useState(false);
  const measurement = f.attributes?.measurement as string | undefined;
  const title = f.title.replace(/ — (STATIC SUSPECT|MEASURED.*)$/, "");
  return (
    <div className={`finding ${f.status}`}>
      <button className="finding-head" style={{ ["--c" as string]: SEV_COLOR[f.severity] }} onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="stripe" aria-hidden />
        <SeverityBadge severity={f.severity} />
        <div className="minw0">
          <div className="finding-title">{title}</div>
          <div className="finding-sub">
            <span>{agentName(f.agent)}</span>
            {f.affected_files.slice(0, 2).map((p) => (
              <code key={p}>{p}</code>
            ))}
            {measurement && <span className="chip">{MEASURE[measurement] ?? measurement}</span>}
          </div>
        </div>
        <div className="row" style={{ justifyContent: "flex-end", flexWrap: "nowrap" }}>
          <ConfidenceBar value={f.confidence} />
          <StatusBadge status={f.status} />
        </div>
      </button>
      {open && (
        <div className="finding-body">
          {verification && (
            <div className="ruling" style={{ ["--c" as string]: verification.decision === "rejected" ? "var(--bad)" : verification.decision === "verified" ? "var(--ok)" : "var(--warn)" }}>
              <b>Red-team ruling, round {verification.round}:</b> {verification.reasoning_summary}
            </div>
          )}
          <dl className="kv">
            <dt>What was found</dt>
            <dd>{f.description}</dd>
            <dt>How the agent reasoned</dt>
            <dd>{f.reasoning_summary}</dd>
            {f.recommended_action && (
              <>
                <dt>Suggested action</dt>
                <dd>{f.recommended_action}</dd>
              </>
            )}
            <dt>Components</dt>
            <dd>{f.affected_components.join(", ") || "—"}</dd>
            <dt>Rule</dt>
            <dd>
              <code>{f.rule_id}</code>
            </dd>
          </dl>
          {f.confidence_factors.length > 0 && (
            <div>
              <div className="eyebrow" style={{ marginBottom: 4 }}>
                Confidence, computed from evidence
              </div>
              <div className="table-wrap">
                <table className="ledger">
                  <tbody>
                    {f.confidence_factors.map((c, i) => (
                      <tr key={i}>
                        <td style={{ width: 170 }}>
                          <code>{c.factor}</code>
                        </td>
                        <td className="r" style={{ width: 64 }}>
                          {c.delta > 0 && i > 0 ? "+" : ""}
                          {c.delta.toFixed(2)}
                        </td>
                        <td className="ink2">{c.detail}</td>
                      </tr>
                    ))}
                    <tr>
                      <td>
                        <b>result</b>
                      </td>
                      <td className="r">
                        <b>{f.confidence.toFixed(2)}</b>
                      </td>
                      <td />
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}
          <div className="stack">
            <div className="eyebrow">Evidence · {evidence.length}</div>
            {evidence.length ? evidence.map((e) => <EvidenceBlock key={e.evidence_id} e={e} />) : <div className="muted small">Hypothesis without direct evidence; confidence is capped at 0.40.</div>}
          </div>
        </div>
      )}
    </div>
  );
}
