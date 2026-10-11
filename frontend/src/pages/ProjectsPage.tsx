import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FilePicker } from "../components/FilePicker";
import { ImpactBadge } from "../components/WatchBits";
import { fmtTime } from "../lib/format";
import { fmtBytes, type PickedFiles } from "../lib/projectFiles";
import { projectsApi } from "../services/api";
import type { Project } from "../types/account";

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    projectsApi
      .list()
      .then((p) => {
        setProjects(p);
        setCreating(p.length === 0);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  return (
    <main className="page narrow">
      <span className="eyebrow">Your software</span>
      <h1 className="page-title">Projects</h1>
      <p className="lede ink2">
        Connect your own project, then watch the open-source repositories it depends on. When they change, Skopeo diffs their public API and shows exactly which lines of <em>your</em> code are
        affected: breaking calls, deprecated functions, changed defaults.
      </p>
      {error && <div className="callout bad">{error}</div>}
      {projects && projects.length > 0 && (
        <section className="section">
          <div className="section-head">
            <h2>Your projects</h2>
            {!creating && (
              <button className="btn sm primary" onClick={() => setCreating(true)}>
                New project
              </button>
            )}
          </div>
          <div className="cases">
            {projects.map((p) => {
              const worst = p.watches.map((w) => w.latest_report?.impact_level ?? "none").sort((a, b) => LEVEL[b] - LEVEL[a])[0];
              return (
                <Link key={p.project_id} to={`/projects/${p.project_id}`} className="case-row project-row">
                  <span className="minw0">
                    <b>{p.name}</b>
                    <span className="small muted">
                      {" "}
                      · {p.source === "github" ? p.repository_url?.replace("https://github.com/", "") : `${p.file_count} uploaded files, ${fmtBytes(p.total_bytes)}`} · updated {fmtTime(p.updated_at)}
                    </span>
                  </span>
                  <span className="small ink2">
                    {p.watches.length} watched {p.watches.length === 1 ? "repository" : "repositories"}
                  </span>
                  <span>{worst && worst !== "none" ? <ImpactBadge level={worst} /> : <span className="small muted">no impact</span>}</span>
                </Link>
              );
            })}
          </div>
        </section>
      )}
      {creating && <NewProject onCancel={projects && projects.length ? () => setCreating(false) : undefined} />}
    </main>
  );
}

const LEVEL: Record<string, number> = { none: 0, low: 1, medium: 2, high: 3, breaking: 4 };

function NewProject({ onCancel }: { onCancel?: () => void }) {
  const nav = useNavigate();
  const [name, setName] = useState("");
  const [source, setSource] = useState<"upload" | "github">("upload");
  const [repo, setRepo] = useState("https://github.com/");
  const [branch, setBranch] = useState("main");
  const [notes, setNotes] = useState("");
  const [picked, setPicked] = useState<PickedFiles | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const p = await projectsApi.create({
        name: name.trim(),
        notes,
        source,
        ...(source === "github" ? { repository_url: repo.trim(), branch: branch.trim() || "main" } : {}),
        files: source === "upload" ? (picked?.files ?? []) : [],
      });
      nav(`/projects/${p.project_id}?new=1`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <form className="panel" onSubmit={submit}>
      <h3>Connect a project</h3>
      <label className="field">
        Project name
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="payments-api" required maxLength={120} />
      </label>
      <div className="field">
        Where is the code?
        <div className="seg" role="radiogroup">
          <button type="button" role="radio" aria-checked={source === "upload"} className={`seg-btn ${source === "upload" ? "on" : ""}`} onClick={() => setSource("upload")}>
            Upload files
          </button>
          <button type="button" role="radio" aria-checked={source === "github"} className={`seg-btn ${source === "github" ? "on" : ""}`} onClick={() => setSource("github")}>
            Public GitHub repository
          </button>
        </div>
        <span className="small muted">
          {source === "upload"
            ? "Good for private code: upload only the manifests and the files that use your dependencies. Code is parsed, never executed."
            : "Skopeo makes a fresh shallow clone on every check and reads it; nothing is executed or written back."}
        </span>
      </div>
      {source === "github" ? (
        <div className="form-row">
          <label className="field">
            Repository
            <input className="input mono" value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="https://github.com/you/your-app" required />
          </label>
          <label className="field">
            Branch
            <input className="input mono" value={branch} onChange={(e) => setBranch(e.target.value)} />
          </label>
        </div>
      ) : (
        <>
          <FilePicker onPicked={setPicked} disabled={busy} />
          {picked && (
            <div className="small ink2">
              {picked.files.length} file(s) ready ({fmtBytes(picked.files.reduce((n, f) => n + f.content.length, 0))}), {picked.skipped} ignored
              {picked.tooLarge.length > 0 && `, ${picked.tooLarge.length} over 400 KB skipped`}.
            </div>
          )}
        </>
      )}
      <label className="field">
        Context for Skopeo (optional)
        <textarea
          className="input"
          rows={3}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          maxLength={8000}
          placeholder="How do you use your dependencies? e.g. “PyJWT verifies session tokens in auth/tokens.py; requests is only used by the billing sync job.”"
        />
      </label>
      {error && <div className="callout bad">{error}</div>}
      <div className="row">
        <button className="btn primary" type="submit" disabled={busy || !name.trim()}>
          Create project
        </button>
        {onCancel && (
          <button type="button" className="btn quiet" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
