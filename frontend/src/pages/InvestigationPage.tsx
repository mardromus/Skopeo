import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { StatusBadge } from "../components/Badges";
import { RiskScale } from "../components/RiskGauge";
import { useInvestigation } from "../hooks/useInvestigation";
import { caseNo, fmtTime } from "../lib/format";
import { api } from "../services/api";
import { ActionsTab } from "./investigation/ActionsTab";
import { AgentsTab } from "./investigation/AgentsTab";
import { CorrelationsTab } from "./investigation/CorrelationsTab";
import { FindingsTab } from "./investigation/FindingsTab";
import { OverviewTab } from "./investigation/OverviewTab";
import { TraceTab } from "./investigation/TraceTab";
import { VerificationTab } from "./investigation/VerificationTab";

type TabId = "overview" | "agents" | "findings" | "correlations" | "verification" | "trace" | "actions";
const TAB_IDS: TabId[] = ["overview", "agents", "findings", "correlations", "verification", "trace", "actions"];

export function InvestigationPage() {
  const { id } = useParams();
  const { data, error, refresh } = useInvestigation(id);
  const [params, setParams] = useSearchParams();
  const initial = params.get("tab") as TabId | null;
  const [tab, setTabState] = useState<TabId>(initial && TAB_IDS.includes(initial) ? initial : "overview");
  const setTab = (t: TabId) => {
    setTabState(t);
    setParams(t === "overview" ? {} : { tab: t }, { replace: true });
  };
  const running = data ? ["queued", "running"].includes(data.detail.status) : true;

  const tabs = useMemo(
    () =>
      [
        { id: "overview", label: "Summary" },
        { id: "agents", label: "Agents", count: data?.agents.length },
        { id: "findings", label: "Findings", count: data?.findings.length },
        { id: "correlations", label: "Correlations", count: data?.correlations.length },
        { id: "verification", label: "Red-team rulings", count: data ? new Set(data.verifications.filter((v) => v.finding_id).map((v) => v.finding_id)).size : undefined },
        { id: "trace", label: "Execution trace", count: data?.events.length },
        { id: "actions", label: "Fixes and actions", count: data?.recommendations.length },
      ] as { id: TabId; label: string; count?: number }[],
    [data],
  );

  if (error && !data) {
    return (
      <main className="page">
        <div className="callout bad">This investigation could not be loaded: {error}</div>
        <p>
          <Link to="/">Back to cases</Link>
        </p>
      </main>
    );
  }
  if (!data) {
    return (
      <main className="page">
        <div className="empty">Loading case…</div>
      </main>
    );
  }
  const d = data.detail;
  const s = d.execution_summary ?? {};
  const f = data.findings;
  const runs = data.agents.filter((r) => r.agent !== "orchestrator");
  const failed = runs.filter((r) => r.status === "failed" || r.status === "timeout").length;
  const retries = runs.filter((r) => r.trigger === "retry").length;
  const followUps = runs.filter((r) => r.trigger === "follow_up" || r.trigger === "verification_request").length;
  const replans = s.replans ?? d.plan?.revisions?.length ?? 0;

  return (
    <main className="page">
      <div className="small">
        <Link to="/">Cases</Link> <span className="muted">/ {caseNo(d.investigation_id)}</span>
      </div>
      <header className="docket" style={{ marginTop: 10 }}>
        <div className="minw0">
          <div className="row">
            <h1>{d.repository}</h1>
            <StatusBadge status={d.status} />
          </div>
          <div className="meta">
            <span>{d.source === "demo_fixture" ? "bundled reference case" : d.repository_url}</span>
            <span>
              branch <code>{d.branch}</code>
            </span>
            {d.commit_sha && (
              <span>
                commit <code>{d.commit_sha.slice(0, 10)}</code>
              </span>
            )}
            <span>depth {d.analysis_depth}</span>
            <span>opened {fmtTime(d.started_at)}</span>
            {d.duration_seconds != null && <span>took {d.duration_seconds}s</span>}
          </div>
          {d.plan?.assessment && <p className="assessment">{d.plan.assessment}</p>}
          {d.error && <div className="callout bad">{d.error}</div>}
          <div className="row" style={{ marginTop: 12 }}>
            <a className="btn sm" href={api.reportUrl(d.investigation_id, "markdown")}>
              Download report (.md)
            </a>
            <a className="btn sm" href={api.reportUrl(d.investigation_id, "json")} target="_blank" rel="noreferrer">
              Open report JSON
            </a>
            {running && (
              <button
                className="btn sm danger"
                onClick={async () => {
                  await api.cancel(d.investigation_id);
                  refresh();
                }}
              >
                Cancel investigation
              </button>
            )}
            {running && <span className="small muted">Updating live as agents report.</span>}
          </div>
        </div>
        <RiskScale score={d.overall_risk?.score ?? null} level={d.overall_risk?.level ?? null} />
      </header>

      <div className="tally" aria-label="Case tally">
        <div>
          <b>{f.length}</b>
          <span className="lbl">findings · {data.evidence.length} evidence</span>
        </div>
        <div>
          <b>{f.filter((x) => x.status === "verified").length}</b>
          <span className="lbl">verified</span>
        </div>
        <div>
          <b>{f.filter((x) => x.status === "rejected").length}</b>
          <span className="lbl">rejected by red team</span>
        </div>
        <div>
          <b>{f.filter((x) => x.status === "needs_more_evidence").length}</b>
          <span className="lbl">insufficient evidence</span>
        </div>
        <div>
          <b>{runs.length}</b>
          <span className="lbl">
            agent runs · <em>{failed} failed</em>, {retries} retried, {followUps} follow-ups
          </span>
        </div>
        <div>
          <b>{replans}</b>
          <span className="lbl">replans</span>
        </div>
        <div>
          <b>{s.parallelism ?? "–"}</b>
          <span className="lbl">agents at once</span>
        </div>
      </div>

      <nav className="tabs" role="tablist" aria-label="Case sections">
        {tabs.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={`tab ${tab === t.id ? "active" : ""}`} onClick={() => setTab(t.id)}>
            {t.label}
            {t.count !== undefined && <span className="count">{t.count}</span>}
          </button>
        ))}
      </nav>

      {tab === "overview" && <OverviewTab data={data} onNavigate={(t) => setTab(t as TabId)} />}
      {tab === "agents" && <AgentsTab data={data} />}
      {tab === "findings" && <FindingsTab data={data} />}
      {tab === "correlations" && <CorrelationsTab data={data} />}
      {tab === "verification" && <VerificationTab data={data} />}
      {tab === "trace" && <TraceTab data={data} />}
      {tab === "actions" && <ActionsTab data={data} onChange={refresh} />}
    </main>
  );
}
