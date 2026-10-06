import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { StatusBadge } from "../components/Badges";
import { caseNo, fmtTime, fmtTimeMs, shortAgent } from "../lib/format";
import { api } from "../services/api";
import type { ExecutionEvent, Health, InvestigationSummary } from "../types/api";

const NOTABLE = new Set([
  "plan_created",
  "agent_failed",
  "agent_retry_scheduled",
  "investigation_requested",
  "replan",
  "correlation_created",
  "challenge",
  "finding_rejected",
  "finding_verified",
  "risk_assessed",
  "investigation_completed",
]);

const ROSTER: [string, string][] = [
  ["Orchestrator", "Plans the investigation, reviews the evidence board after every phase, schedules follow-ups and retries."],
  ["Security", "Committed secrets, unsafe calls found by AST analysis, AI-directed instructions in docs, use of vulnerable packages."],
  ["Dependency health", "Manifests in five ecosystems, OSV advisories for exact versions, freshness, pinning."],
  ["Code quality", "Cyclomatic complexity, nesting, swallowed exceptions, duplicated blocks."],
  ["API compatibility", "Public API, deprecations still in use, breaking changes an upgrade would cause."],
  ["Test reliability", "Runs the suite under coverage when allowed; weak assertions; untested critical code."],
  ["License compliance", "License text against package metadata, copyleft headers, dependency licenses."],
  ["Maintenance", "Commit cadence, contributor concentration, releases and pull-request activity."],
  ["Performance", "N+1 queries and network calls in loops; measures them with benchmarks before claiming impact."],
  ["Correlation", "Links findings across agents into compound risks, shared root causes and contradictions."],
  ["Red team", "Tries to disprove every finding with its own checks. Its ruling decides what reaches the report."],
  ["Risk and recommendations", "Scores only verified findings and drafts fixes, issues and draft PRs for approval."],
];

function tone(t: string): string {
  if (t === "finding_rejected" || t === "agent_failed") return "bad";
  if (t === "finding_verified" || t === "investigation_completed") return "ok";
  if (t === "challenge" || t === "agent_retry_scheduled") return "warn";
  return "";
}

export function HomePage({ health }: { health: Health | null }) {
  const nav = useNavigate();
  const [url, setUrl] = useState("https://github.com/");
  const [branch, setBranch] = useState("main");
  const [depth, setDepth] = useState("standard");
  const [actions, setActions] = useState(false);
  const [fault, setFault] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<InvestigationSummary[]>([]);
  const [log, setLog] = useState<{ inv: InvestigationSummary; events: ExecutionEvent[] } | null>(null);

  useEffect(() => {
    api
      .list()
      .then(async (list) => {
        setHistory(list);
        const done = list.find((i) => !["queued", "running"].includes(i.status));
        if (done) {
          const events = await api.events(done.investigation_id);
          setLog({ inv: done, events: events.filter((e) => NOTABLE.has(e.event_type)) });
        }
      })
      .catch(() => setHistory([]));
  }, []);

  async function start(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const inv = await api.create({ repository_url: url.trim(), branch: branch.trim(), analysis_depth: depth, enable_github_actions: actions });
      nav(`/investigations/${inv.investigation_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  async function demo() {
    setBusy(true);
    setError(null);
    try {
      const inv = await api.createDemo({ fault_injection: fault });
      nav(`/investigations/${inv.investigation_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <main className="page">
      <div className="intake">
        <section className="minw0">
          <span className="eyebrow">Open a new investigation</span>
          <h1>Find what is wrong with a repository, and prove it.</h1>
          <p className="lede">
            Eight specialist agents examine the code in parallel. Every finding cites evidence, a red-team agent tries to disprove it, and only findings that survive are scored as risk.
          </p>
          <form onSubmit={start}>
            <label className="field" htmlFor="repo-url">
              GitHub repository
              <input id="repo-url" className="input mono" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/owner/repository" required />
            </label>
            <div className="form-row">
              <label className="field" htmlFor="repo-branch">
                Branch
                <input id="repo-branch" className="input mono" value={branch} onChange={(e) => setBranch(e.target.value)} required />
              </label>
              <label className="field" htmlFor="repo-depth">
                Depth
                <select id="repo-depth" className="input" value={depth} onChange={(e) => setDepth(e.target.value)}>
                  <option value="quick">Quick: security, dependencies, tests</option>
                  <option value="standard">Standard: every relevant agent</option>
                  <option value="deep">Deep: every agent, always</option>
                </select>
              </label>
            </div>
            <label className="check-label" htmlFor="repo-actions">
              <input id="repo-actions" type="checkbox" checked={actions} onChange={(e) => setActions(e.target.checked)} />
              Let approved issues and draft PRs be sent to GitHub
            </label>
            {error && <div className="callout bad">{error}</div>}
            <div className="row">
              <button className="btn primary" type="submit" disabled={busy}>
                Start investigation
              </button>
              <span className="small muted">Repository code is treated as untrusted. Nothing is merged or deployed.</span>
            </div>
          </form>

          <div className="demo-box">
            <span className="eyebrow">Or run the reference case</span>
            <p className="ink2" style={{ margin: 0 }}>
              <code>examples/vulnerable-demo-repo</code> has a vulnerable PyJWT pin, weak authentication, untested auth code, a documented dummy AWS key, an N+1 query and a GPL file in an MIT
              project. It runs offline in under a minute.
            </p>
            <div className="row">
              <button className="btn" onClick={demo} disabled={busy || (health !== null && !health.demo_mode)}>
                Run the reference case
              </button>
              <label className="check-label" htmlFor="demo-fault">
                <input id="demo-fault" type="checkbox" checked={fault} onChange={(e) => setFault(e.target.checked)} />
                Make the performance agent fail once
              </label>
            </div>
          </div>
        </section>

        <section className="minw0">
          {log ? (
            <div className="log">
              <div className="log-head">
                <span>
                  {caseNo(log.inv.investigation_id)} · {log.inv.repository}
                </span>
                <Link to={`/investigations/${log.inv.investigation_id}`}>open case</Link>
              </div>
              <div className="log-body">
                {log.events.slice(0, 40).map((e) => (
                  <div key={e.event_id} className={`log-line ${tone(e.event_type)}`}>
                    <span className="t">{fmtTimeMs(e.timestamp)}</span>
                    <span className="who">{shortAgent(e.sender)}</span>
                    <span className="m">{e.message}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div>
              <span className="eyebrow">The team</span>
              <table className="roster" style={{ marginTop: 8 }}>
                <tbody>
                  {ROSTER.map(([name, job]) => (
                    <tr key={name}>
                      <td>{name}</td>
                      <td>{job}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      <section className="section" style={{ marginTop: 40 }}>
        <div className="section-head">
          <h2>Cases</h2>
          <span className="note">{history.length ? `${history.length} on record` : "None yet. Run the reference case to see a complete one."}</span>
        </div>
        <div className="cases">
          {history.map((h) => (
            <Link key={h.investigation_id} to={`/investigations/${h.investigation_id}`} className="case-row">
              <span className="case-id">{caseNo(h.investigation_id)}</span>
              <span className="minw0">
                <b>{h.repository}</b>
                <span className="small muted">
                  {" "}
                  · {h.branch} · {fmtTime(h.started_at ?? h.created_at)}
                  {h.duration_seconds ? ` · ${h.duration_seconds}s` : ""}
                </span>
              </span>
              <span className="small mono ink2">{h.overall_risk?.score != null ? `risk ${Math.round(h.overall_risk.score)} ${h.overall_risk.level}` : "—"}</span>
              <span>
                <StatusBadge status={h.status} />
              </span>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
