import { CorrelationChain } from "../../components/CorrelationChain";
import type { Finding, InvestigationBundle } from "../../types/api";

const ORDER = ["compound_risk", "contradiction", "causal", "dependency", "shared_root_cause", "duplicate"];

export function CorrelationsTab({ data }: { data: InvestigationBundle }) {
  const byId: Record<string, Finding> = Object.fromEntries(data.findings.map((f) => [f.finding_id, f]));
  const sorted = [...data.correlations].sort((a, b) => ORDER.indexOf(a.relationship_type) - ORDER.indexOf(b.relationship_type) || b.risk_multiplier - a.risk_multiplier);
  return (
    <div className="section">
      <p className="ink2" style={{ maxWidth: "80ch", marginTop: 0 }}>
        The correlation agent looks across findings from different agents for shared packages, files, components and opposing claims. A compound risk only raises a score after the red team has
        verified its members.
      </p>
      {sorted.length === 0 ? <p className="empty">Correlation runs once the specialists have reported.</p> : sorted.map((c) => <CorrelationChain key={c.correlation_id} c={c} findings={byId} />)}
    </div>
  );
}
