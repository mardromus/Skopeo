import { VerificationCard } from "../../components/VerificationCard";
import type { InvestigationBundle, Verification } from "../../types/api";

export function VerificationTab({ data }: { data: InvestigationBundle }) {
  const findings = Object.fromEntries(data.findings.map((f) => [f.finding_id, f]));
  const latest: Record<string, Verification> = {};
  for (const v of data.verifications) if (v.finding_id) latest[v.finding_id] = v;
  const items = Object.values(latest);
  const groups: { key: Verification["decision"]; title: string; note: string }[] = [
    { key: "rejected", title: "Rejected", note: "an agent proposed these; the red team disproved them" },
    { key: "needs_more_evidence", title: "Insufficient evidence", note: "follow-ups ran but could not settle the claim" },
    { key: "verified", title: "Verified", note: "survived every check and entered the risk report" },
  ];
  const earlier = data.verifications.filter((v) => v.finding_id && latest[v.finding_id] !== v);
  const corr = data.verifications.filter((v) => v.correlation_id);
  const evidenceFor = (id: string) => data.evidence.filter((e) => e.finding_id === id);

  if (!items.length) return <p className="empty">The red team rules after correlation. Rulings will appear here.</p>;
  return (
    <div>
      {groups.map((g) => {
        const list = items.filter((v) => v.decision === g.key);
        if (!list.length) return null;
        return (
          <section key={g.key} className="section">
            <div className="section-head">
              <h2>
                {g.title} · {list.length}
              </h2>
              <span className="note">{g.note}</span>
            </div>
            <div className="stack">
              {list.map((v) => (
                <VerificationCard key={v.verification_id} v={v} finding={findings[v.finding_id!]} evidence={evidenceFor(v.finding_id!)} />
              ))}
            </div>
          </section>
        );
      })}
      {earlier.length > 0 && (
        <section className="section">
          <div className="section-head">
            <h2>Earlier rounds</h2>
            <span className="note">rulings later revised when new evidence arrived</span>
          </div>
          <div className="stack" style={{ gap: 4 }}>
            {earlier.map((v) => (
              <div key={v.verification_id} className="small">
                Round {v.round}: <b>{findings[v.finding_id!]?.title}</b>, {v.decision.replace(/_/g, " ")}. <span className="muted">{v.reasoning_summary}</span>
              </div>
            ))}
          </div>
        </section>
      )}
      {corr.length > 0 && (
        <section className="section">
          <div className="section-head">
            <h2>Correlation rulings</h2>
          </div>
          <div className="stack" style={{ gap: 4 }}>
            {corr.map((v) => (
              <div key={v.verification_id} className="small">
                Round {v.round}: <b>{data.correlations.find((c) => c.correlation_id === v.correlation_id)?.title}</b>, {v.decision.replace(/_/g, " ")}.{" "}
                <span className="muted">{v.reasoning_summary}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
