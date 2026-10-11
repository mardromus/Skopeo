import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { StatusBadge } from "../components/Badges";
import { FilePicker } from "../components/FilePicker";
import { ChangeBadge, ImpactBadge, Ticks } from "../components/WatchBits";
import { fmtTime } from "../lib/format";
import { fmtBytes } from "../lib/projectFiles";
import { projectsApi } from "../services/api";
import type { Frequency, Project, ProjectFileInfo, ReportSummary, Watch, WatchReport } from "../types/account";

const FREQ_LABEL: Record<Frequency, string> = { hourly: "Every hour", daily: "Every day", weekly: "Every week", manual: "Only when I ask" };

function errText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export function ProjectPage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selectedWatch = params.get("watch");
  const selectedReport = params.get("report");

  const load = useCallback(
    () =>
      projectsApi
        .get(id)
        .then(setProject)
        .catch((err) => setError(errText(err))),
    [id],
  );

  useEffect(() => {
    projectsApi
      .get(id)
      .then(setProject)
      .catch((err) => setError(errText(err)));
  }, [id]);

  // poll while a check is running
  const busy = project?.watches.some((w) => w.status === "checking") ?? false;
  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(() => void load(), 2500);
    return () => window.clearInterval(t);
  }, [busy, load]);

  if (error && !project) return <main className="page"><div className="callout bad">{error}</div></main>;
  if (!project) return <main className="page"><p className="muted">Loading…</p></main>;

  const watch = project.watches.find((w) => w.watch_id === selectedWatch) ?? (project.watches.length === 1 ? project.watches[0] : undefined);
  const reportId = selectedReport ?? watch?.latest_report?.report_id ?? null;
  const select = (w: Watch, r?: string) => setParams(r ? { watch: w.watch_id, report: r } : { watch: w.watch_id }, { replace: true });

  return (
    <main className="page">
      <div className="crumbs small">
        <Link to="/projects">Projects</Link> / <span className="ink2">{project.name}</span>
      </div>
      <div className="row between project-head">
        <div className="minw0">
          <h1 className="page-title">{project.name}</h1>
          <div className="small ink2">
            {project.source === "github" ? (
              <>
                GitHub · <a href={project.repository_url ?? "#"} target="_blank" rel="noreferrer">{project.repository_url?.replace("https://github.com/", "")}</a> @ {project.branch}
              </>
            ) : (
              <>Uploaded context · {project.file_count} files · {fmtBytes(project.total_bytes)}</>
            )}
          </div>
        </div>
        <button
          className="btn sm danger"
          onClick={() => {
            if (window.confirm(`Delete the project “${project.name}” with its watches and reports?`)) void projectsApi.remove(project.project_id).then(() => nav("/projects"));
          }}
        >
          Delete project
        </button>
      </div>
      {params.get("new") && project.watches.length === 0 && (
        <div className="callout ok">Project connected. Next, watch an open-source repository it depends on: Skopeo will tell you how its changes affect this code.</div>
      )}

      <div className="cols-3-2 project-cols">
        <div className="minw0">
          <section className="section">
            <div className="section-head">
              <h2>Watched repositories</h2>
              <span className="note">{project.watches.length || "none yet"}</span>
            </div>
            <div className="stack">
              {project.watches.map((w) => (
                <WatchCard key={w.watch_id} watch={w} active={watch?.watch_id === w.watch_id} onSelect={() => select(w)} onChange={load} />
              ))}
            </div>
            <AddWatch projectId={project.project_id} first={project.watches.length === 0} onAdded={async (w) => {
              await load();
              select(w);
            }} />
          </section>
        </div>
        <div className="minw0">
          <ContextPanel project={project} onChange={load} />
        </div>
      </div>

      {watch && (
        <section className="section">
          <div className="section-head">
            <h2>Impact on {project.name}: {watch.upstream_name}</h2>
            <ReportPicker watch={watch} current={reportId} onPick={(r) => select(watch, r)} />
          </div>
          {watch.status === "checking" && !reportId && <div className="callout">Checking {watch.upstream_name}… this takes a few seconds to a minute.</div>}
          {reportId ? <ReportView key={reportId} reportId={reportId} /> : watch.status !== "checking" && <p className="empty">No report yet. Run a check.</p>}
        </section>
      )}
    </main>
  );
}

function WatchCard({ watch, active, onSelect, onChange }: { watch: Watch; active: boolean; onSelect: () => void; onChange: () => Promise<void> }) {
  const [error, setError] = useState<string | null>(null);
  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await onChange();
    } catch (err) {
      setError(errText(err));
    }
  };
  const r = watch.latest_report;
  return (
    <div className={`watch ${active ? "active" : ""}`}>
      <button className="watch-main" onClick={onSelect}>
        <div className="row between">
          <b className="mono">{watch.upstream_name}</b>
          {watch.status === "checking" ? (
            <StatusBadge status="running" label="Checking" />
          ) : watch.status === "failed" ? (
            <StatusBadge status="failed" label="Check failed" />
          ) : r ? (
            <ImpactBadge level={r.impact_level} />
          ) : (
            <StatusBadge status="queued" label="Waiting" />
          )}
        </div>
        <div className="small ink2">
          {watch.package_name ?? "package detected on first check"}
          {watch.last_seen_version && ` · upstream ${watch.last_seen_version}`}
          {watch.last_seen_sha && ` @ ${watch.last_seen_sha.slice(0, 8)}`}
        </div>
        {r && (
          <p className="small watch-summary">
            <Ticks text={r.summary} />
          </p>
        )}
        <div className="small muted">
          {FREQ_LABEL[watch.frequency]}
          {watch.last_checked_at && ` · checked ${fmtTime(watch.last_checked_at)}`}
          {watch.next_check_at && watch.enabled && watch.frequency !== "manual" && ` · next ${fmtTime(watch.next_check_at)}`}
          {!watch.enabled && " · paused"}
        </div>
      </button>
      {watch.last_error && watch.status === "failed" && <div className="callout bad small">{watch.last_error}</div>}
      {error && <div className="callout bad small">{error}</div>}
      <div className="row">
        <button className="btn sm primary" disabled={watch.status === "checking"} onClick={() => void run(() => projectsApi.check(watch.watch_id))}>
          Check now
        </button>
        <button
          className="btn sm"
          disabled={watch.status === "checking"}
          title="Compare the version your manifest pins with the latest upstream code"
          onClick={() => void run(() => projectsApi.check(watch.watch_id, true))}
        >
          Compare with my pinned version
        </button>
        <select
          className="input sm-select"
          value={watch.frequency}
          aria-label="Check frequency"
          onChange={(e) => void run(() => projectsApi.updateWatch(watch.watch_id, { frequency: e.target.value as Frequency }))}
        >
          {Object.entries(FREQ_LABEL).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <button className="btn sm quiet" onClick={() => void run(() => projectsApi.updateWatch(watch.watch_id, { enabled: !watch.enabled }))}>
          {watch.enabled ? "Pause" : "Resume"}
        </button>
        <button
          className="btn sm quiet danger"
          onClick={() => {
            if (window.confirm(`Stop watching ${watch.upstream_name}?`)) void run(() => projectsApi.deleteWatch(watch.watch_id));
          }}
        >
          Remove
        </button>
      </div>
    </div>
  );
}

function AddWatch({ projectId, first, onAdded }: { projectId: string; first: boolean; onAdded: (w: Watch) => Promise<void> }) {
  const [open, setOpen] = useState(first);
  const [url, setUrl] = useState("https://github.com/");
  const [frequency, setFrequency] = useState<Frequency>("daily");
  const [advanced, setAdvanced] = useState(false);
  const [branch, setBranch] = useState("");
  const [pkg, setPkg] = useState("");
  const [imports, setImports] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const w = await projectsApi.createWatch(projectId, {
        upstream_url: url.trim(),
        frequency,
        ...(branch.trim() ? { branch: branch.trim() } : {}),
        ...(pkg.trim() ? { package_name: pkg.trim() } : {}),
        ...(imports.trim() ? { import_names: imports.split(/[\s,]+/).filter(Boolean) } : {}),
      });
      setUrl("https://github.com/");
      setOpen(false);
      await onAdded(w);
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  if (!open)
    return (
      <button className="btn sm" onClick={() => setOpen(true)} style={{ marginTop: 12 }}>
        + Watch another repository
      </button>
    );
  return (
    <form className="panel" onSubmit={submit}>
      <h3>Watch an open-source dependency</h3>
      <div className="form-row">
        <label className="field">
          Upstream GitHub repository
          <input className="input mono" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/jpadilla/pyjwt" required />
        </label>
        <label className="field">
          Check
          <select className="input" value={frequency} onChange={(e) => setFrequency(e.target.value as Frequency)}>
            {Object.entries(FREQ_LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>
      <button type="button" className="btn sm quiet" onClick={() => setAdvanced((a) => !a)}>
        {advanced ? "Hide" : "Show"} advanced options
      </button>
      {advanced && (
        <div className="form-row three">
          <label className="field">
            Branch
            <input className="input mono" value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="default branch" />
          </label>
          <label className="field">
            Package name
            <input className="input mono" value={pkg} onChange={(e) => setPkg(e.target.value)} placeholder="auto (e.g. PyJWT)" />
          </label>
          <label className="field">
            Import names
            <input className="input mono" value={imports} onChange={(e) => setImports(e.target.value)} placeholder="auto (e.g. jwt)" />
          </label>
        </div>
      )}
      <span className="small muted">
        The first check compares the release your manifest pins (for example <code className="chip">PyJWT==1.7.1</code>) with the latest upstream code. Later checks report what changed since the
        previous one.
      </span>
      {error && <div className="callout bad">{error}</div>}
      <div className="row">
        <button className="btn primary" disabled={busy}>
          Start watching
        </button>
        {!first && (
          <button type="button" className="btn quiet" onClick={() => setOpen(false)}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

function ContextPanel({ project, onChange }: { project: Project; onChange: () => Promise<void> }) {
  const [notes, setNotes] = useState(project.notes);
  const [files, setFiles] = useState<ProjectFileInfo[] | null>(null);
  const [msg, setMsg] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (project.source === "upload") void projectsApi.files(project.project_id).then(setFiles);
  }, [project.project_id, project.source, project.updated_at]);

  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      if (ok) setMsg({ tone: "ok", text: ok });
      await onChange();
    } catch (err) {
      setMsg({ tone: "bad", text: errText(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="section">
      <div className="section-head">
        <h2>Project context</h2>
      </div>
      <label className="field">
        Notes for Skopeo
        <textarea className="input" rows={4} value={notes} maxLength={8000} onChange={(e) => setNotes(e.target.value)} placeholder="How and where do you use your dependencies?" />
      </label>
      <div className="row" style={{ marginTop: 8 }}>
        <button className="btn sm" disabled={busy || notes === project.notes} onClick={() => void act(() => projectsApi.update(project.project_id, { notes }), "Notes saved.")}>
          Save notes
        </button>
      </div>
      {project.source === "upload" && (
        <div className="stack" style={{ marginTop: 16 }}>
          <span className="field">Files</span>
          <FilePicker
            disabled={busy}
            onPicked={(p) => {
              if (!p.files.length) {
                setMsg({ tone: "bad", text: "No source files or manifests in that selection." });
                return;
              }
              void act(() => projectsApi.putFiles(project.project_id, p.files), `${p.files.length} file(s) added or updated.`);
            }}
          />
          {files && files.length > 0 && (
            <ul className="file-list">
              {files.map((f) => (
                <li key={f.path}>
                  <span className="mono small wrap-any">{f.path}</span>
                  <span className="small muted">{fmtBytes(f.size)}</span>
                  <button className="btn sm quiet danger" aria-label={`Remove ${f.path}`} onClick={() => void act(() => projectsApi.deleteFile(project.project_id, f.path))}>
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {project.source === "github" && <p className="small muted">Skopeo clones the repository fresh on every check, so new commits to your code are always included.</p>}
      {msg && <div className={`callout ${msg.tone}`} style={{ marginTop: 10 }}>{msg.text}</div>}
    </section>
  );
}

function ReportPicker({ watch, current, onPick }: { watch: Watch; current: string | null; onPick: (id: string) => void }) {
  const [reports, setReports] = useState<ReportSummary[]>([]);
  useEffect(() => {
    void projectsApi.reports(watch.watch_id).then(setReports).catch(() => setReports([]));
  }, [watch.watch_id, watch.latest_report?.report_id]);
  if (reports.length < 2) return null;
  return (
    <select className="input sm-select" value={current ?? ""} onChange={(e) => onPick(e.target.value)} aria-label="Report history">
      {reports.map((r) => (
        <option key={r.report_id} value={r.report_id}>
          {fmtTime(r.created_at)} · {r.kind} · {r.impact_level}
        </option>
      ))}
    </select>
  );
}

function ReportView({ reportId }: { reportId: string }) {
  const [report, setReport] = useState<WatchReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [allNotes, setAllNotes] = useState(false);
  useEffect(() => {
    projectsApi
      .report(reportId)
      .then(setReport)
      .catch((err) => setError(errText(err)));
  }, [reportId]);
  if (error) return <div className="callout bad">{error}</div>;
  if (!report) return <p className="muted">Loading report…</p>;
  const s = report.stats;
  const changes = report.upstream_changes.filter((c) => c.kind !== "added");
  const added = report.upstream_changes.filter((c) => c.kind === "added");
  return (
    <div className="report">
      <div className="report-top">
        <div className="minw0">
          <div className="row">
            <ImpactBadge level={report.impact_level} />
            <span className="small ink2 mono">
              {report.kind === "baseline" ? "first look" : `${report.base_ref ?? "previous"} → ${report.head_ref ?? ""}`} {report.head_sha ? `@ ${report.head_sha.slice(0, 10)}` : ""}
            </span>
            <span className="small muted">{fmtTime(report.created_at)}</span>
          </div>
          <p className="report-summary">
            <Ticks text={report.summary} />
          </p>
          {report.narrative.actions.length > 0 && (
            <ol className="actions-list">
              {report.narrative.actions.map((a, i) => (
                <li key={i}>
                  <Ticks text={a} />
                </li>
              ))}
            </ol>
          )}
          <span className="small muted">Written by {report.narrative.decided_by === "policy" ? "Skopeo's deterministic analysis" : report.narrative.decided_by}.</span>
        </div>
        <dl className="tally report-tally">
          <div>
            <b>{s.impacts ?? 0}</b>
            <span className="lbl">places in your code</span>
          </div>
          <div>
            <b>{s.affected_files ?? 0}</b>
            <span className="lbl">files affected</span>
          </div>
          <div>
            <b>{s.breaking_changes ?? 0}</b>
            <span className="lbl">breaking upstream</span>
          </div>
          {(s.commits ?? 0) > 0 && (
            <div>
              <b>{s.commits}</b>
              <span className="lbl">commits</span>
            </div>
          )}
        </dl>
      </div>
      {s.pinned && (
        <div className="callout small">
          Your <span className="mono">{s.pinned.manifest}</span> asks for <span className="mono">{s.package_name} {s.pinned.spec}</span>
          {s.upstream_version && <>; upstream is at <span className="mono">{s.upstream_version}</span></>}.
        </div>
      )}

      <h3 className="sub">Where your code is affected</h3>
      {report.impacts.length === 0 ? (
        <p className="empty">{report.kind === "baseline" ? "This first check records a baseline; the next one reports changes." : "None of the upstream changes touch code in this project."}</p>
      ) : (
        <div className="impacts">
          {report.impacts.map((i, n) => (
            <div key={n} className={`impact-row lvl-${i.level}`}>
              <div className="row between">
                <span className="row">
                  <ImpactBadge level={i.level} />
                  <b>
                    <Ticks text={i.title} />
                  </b>
                </span>
                <span className="small muted">{i.certainty}</span>
              </div>
              <div className="mono small loc">
                {i.file}:{i.line}
              </div>
              {i.snippet && <pre className="snippet">{i.snippet}</pre>}
              <p className="small">
                <Ticks text={i.explanation} />
              </p>
              {(i.change.old_signature || i.change.new_signature) && (
                <div className="diff small">
                  {i.change.old_signature && <div className="del">- {i.change.old_signature}</div>}
                  {i.change.new_signature && <div className="add">+ {i.change.new_signature}</div>}
                </div>
              )}
              <p className="small ink2">
                <b>Fix:</b> <Ticks text={i.suggestion} />
              </p>
            </div>
          ))}
        </div>
      )}

      {report.usages.length > 0 && (
        <>
          <h3 className="sub">What your project uses</h3>
          <div className="chips">
            {report.usages.map((u) => (
              <span key={u.symbol} className="chip" title={u.files.join("\n")}>
                {u.symbol} ×{u.uses}
              </span>
            ))}
          </div>
        </>
      )}

      {changes.length > 0 && (
        <>
          <h3 className="sub">Upstream API changes ({changes.length})</h3>
          <div className="table-wrap">
            <table className="ledger">
              <tbody>
                {(showAll ? changes : changes.slice(0, 15)).map((c, n) => (
                  <tr key={n}>
                    <td>
                      <ChangeBadge change={c} />
                    </td>
                    <td className="mono small wrap-any">{c.symbol}</td>
                    <td className="small">{c.detail && <Ticks text={c.detail} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {changes.length > 15 && (
            <button className="btn sm quiet" onClick={() => setShowAll((v) => !v)}>
              {showAll ? "Show fewer" : `Show all ${changes.length}`}
            </button>
          )}
        </>
      )}
      {added.length > 0 && <p className="small muted">{added.length} new public API element(s) were added upstream.</p>}

      {report.narrative.changelog.length > 0 && (
        <>
          <h3 className="sub">From the changelog</h3>
          <ul className="small changelog">
            {(allNotes ? report.narrative.changelog : report.narrative.changelog.slice(0, 6)).map((l, n) => (
              <li key={n}>
                <Ticks text={l} />
              </li>
            ))}
          </ul>
          {report.narrative.changelog.length > 6 && (
            <button className="btn sm quiet" onClick={() => setAllNotes((v) => !v)}>
              {allNotes ? "Show fewer" : `Show all ${report.narrative.changelog.length}`}
            </button>
          )}
        </>
      )}
      {report.commits.length > 0 && (
        <>
          <h3 className="sub">Upstream commits ({report.commits.length})</h3>
          <ul className="small commits">
            {report.commits.slice(0, 20).map((c) => (
              <li key={c.sha}>
                <span className="mono muted">{c.sha.slice(0, 8)}</span> {c.message} <span className="muted">· {c.author}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
