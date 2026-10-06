import { useState } from "react";
import { PriorityBadge, StatusBadge } from "../../components/Badges";
import { api } from "../../services/api";
import type { ActionProposal, InvestigationBundle } from "../../types/api";

function Diff({ patch }: { patch: string }) {
  return (
    <div className="diff">
      {patch.split("\n").map((line, i) => (
        <div key={i} className={line.startsWith("+") && !line.startsWith("+++") ? "add" : line.startsWith("-") && !line.startsWith("---") ? "del" : ""}>
          {line || " "}
        </div>
      ))}
    </div>
  );
}

function Proposal({ a, investigationId, onChange }: { a: ActionProposal; investigationId: string; onChange: () => void }) {
  const [who, setWho] = useState("");
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const decide = async (decision: "approve" | "reject") => {
    setError(null);
    try {
      await api.approve(investigationId, { action_id: a.action_id, decision, approved_by: who.trim() || "reviewer" });
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  return (
    <div className="prop">
      <div className="row between" style={{ alignItems: "flex-start" }}>
        <div className="minw0">
          <span className="eyebrow">{a.action_type === "pull_request" ? "Draft pull request" : "GitHub issue"} · {a.target_repository}</span>
          <div style={{ fontWeight: 600, marginTop: 2 }} className="wrap-any">
            {a.title}
          </div>
        </div>
        <StatusBadge status={a.status === "proposed" ? "waiting" : a.status} label={a.status === "proposed" ? "Awaiting approval" : undefined} />
      </div>
      {a.patch && <Diff patch={a.patch} />}
      <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? "Hide issue text" : "Show issue text"}
      </button>
      {open && <pre className="diff pre-wrap" style={{ whiteSpace: "pre-wrap" }}>{a.body}</pre>}
      {a.status === "proposed" ? (
        <div className="row">
          <input id={`approver-${a.action_id}`} className="input" style={{ maxWidth: 220 }} placeholder="Your name" value={who} onChange={(e) => setWho(e.target.value)} aria-label="Approver name" />
          <button className="btn primary sm" onClick={() => decide("approve")}>
            Approve
          </button>
          <button className="btn sm" onClick={() => decide("reject")}>
            Reject
          </button>
          <span className="small muted">{a.result?.executable ? "Approval sends it to GitHub unless dry run is on." : "Recorded only: GitHub actions are off for this case."}</span>
        </div>
      ) : (
        <div className="small muted">
          {a.status === "rejected" ? "Rejected" : "Approved"} by {a.approved_by ?? "—"}. {a.result?.reason ? `Nothing was sent (${String(a.result.reason)}).` : ""} {a.result?.url ? String(a.result.url) : ""}
        </div>
      )}
      {error && <div className="callout bad">{error}</div>}
    </div>
  );
}

export function ActionsTab({ data, onChange }: { data: InvestigationBundle; onChange: () => void }) {
  return (
    <div className="cols-3-2">
      <section className="section">
        <div className="section-head">
          <h2>Recommended fixes</h2>
          <span className="note">written from verified risks only</span>
        </div>
        {data.recommendations.length === 0 && <p className="empty">Fixes are written after risk assessment.</p>}
        {data.recommendations.map((r) => (
          <article key={r.recommendation_id} className="prop">
            <div className="row" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
              <PriorityBadge priority={r.priority} />
              <h3 className="wrap-any" style={{ fontSize: 15 }}>
                {r.title.replace(/ — (STATIC SUSPECT|MEASURED.*)$/, "")}
              </h3>
            </div>
            <dl className="kv">
              <dt>Problem</dt>
              <dd>{r.problem}</dd>
              <dt>Where</dt>
              <dd>{r.affected_component}</dd>
              <dt>Why it matters</dt>
              <dd>{r.why_it_matters}</dd>
              <dt>Fix</dt>
              <dd className="pre-wrap">{r.proposed_fix}</dd>
              <dt>Benefit</dt>
              <dd>{r.expected_benefit}</dd>
              <dt>Effort</dt>
              <dd>
                {r.implementation_difficulty} · risk score {r.estimated_risk.score} · {r.verification_status}
              </dd>
            </dl>
          </article>
        ))}
      </section>
      <section className="section">
        <div className="section-head">
          <h2>Proposed GitHub actions</h2>
        </div>
        <p className="small ink2" style={{ marginTop: 0 }}>
          Skopeo only opens issues and draft pull requests, and only after someone approves them here. It never merges, deploys, deletes files or rotates credentials. With dry run on, an approval is recorded and nothing is sent.
        </p>
        {data.actions.length === 0 && <p className="empty">Only P0 and P1 risks produce proposals.</p>}
        {data.actions.map((a) => (
          <Proposal key={a.action_id} a={a} investigationId={data.detail.investigation_id} onChange={onChange} />
        ))}
      </section>
    </div>
  );
}
