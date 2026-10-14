import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Avatar, GitHubMark } from "../auth/AccountMenu";
import { useAuth } from "../auth/context";
import { CaseOptionsDialog, type CaseOptions } from "./CaseOptionsDialog";
import { fmtTime } from "../lib/format";
import { ApiError, githubApi } from "../services/api";
import type { GitHubConnection, GitHubRepo } from "../types/account";

const msg = (err: unknown) => (err instanceof Error ? err.message : String(err));

/** The connection as the server knows it; reloads when sign-in connects GitHub. null while loading, "signed-out" on 401. */
function useGitHubConnection(): [GitHubConnection | null | "signed-out", () => void] {
  const { githubVersion, user } = useAuth();
  const [conn, setConn] = useState<GitHubConnection | null | "signed-out">(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    githubApi
      .connection()
      .then((c) => alive && setConn(c))
      .catch((err) => alive && setConn(err instanceof ApiError && err.status === 401 ? "signed-out" : { connected: false }));
    return () => {
      alive = false;
    };
  }, [githubVersion, tick, user?.user_id]);
  return [conn, () => setTick((t) => t + 1)];
}

/** Personal access token form: the way to connect GitHub without Firebase (local mode), or with a fine-grained token. */
function TokenForm({ onDone }: { onDone: () => void }) {
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await githubApi.connect(token.trim(), "pat");
      setToken("");
      onDone();
    } catch (err) {
      setError(msg(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="gh-token" onSubmit={submit}>
      <label className="field" htmlFor="gh-pat">
        Personal access token
        <input
          id="gh-pat"
          className="input mono"
          type="password"
          autoComplete="off"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="github_pat_… or ghp_…"
          required
          minLength={10}
        />
        <span className="small muted">
          Create one at github.com → Settings → Developer settings → Personal access tokens. Read-only “Contents” and “Metadata” access is enough. It is checked with GitHub, stored encrypted, and
          never shown again.
        </span>
      </label>
      {error && <div className="callout bad">{error}</div>}
      <button className="btn" type="submit" disabled={busy || token.trim().length < 10}>
        {busy ? "Checking with GitHub…" : "Connect with token"}
      </button>
    </form>
  );
}

/** Account settings: connect, inspect and disconnect GitHub. */
export function GitHubConnectionCard() {
  const { config, connectGitHub, error: authError } = useAuth();
  const [conn, reload] = useGitHubConnection();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showToken, setShowToken] = useState(false);
  const firebase = config?.mode === "firebase";
  const githubOn = config?.github?.enabled !== false;
  if (!githubOn || conn === "signed-out") return null;

  return (
    <section className="section">
      <div className="section-head">
        <h2>GitHub</h2>
        <span className="note">List and import your repositories</span>
      </div>
      {conn === null ? (
        <p className="muted">Loading…</p>
      ) : conn.connected ? (
        <div className="gh-conn">
          <Avatar src={conn.avatar_url ?? null} name={conn.login ?? null} size={40} />
          <div className="minw0">
            <b>@{conn.login}</b>
            <div className="small muted">
              {conn.source === "pat" ? "Personal access token" : "Signed in with GitHub"} · connected {fmtTime(conn.connected_at)}
              {conn.scopes && conn.scopes.length > 0 ? ` · scopes ${conn.scopes.join(", ")}` : ""}
            </div>
            <div className="small ink2">
              {conn.private_repos
                ? "Public and private repositories can be imported. Private cases are visible only to you."
                : conn.private_repos_enabled
                  ? "Only public repositories: reconnect and grant the repo permission to import private ones."
                  : "Public repositories only (this server does not import private repositories)."}
            </div>
          </div>
          <div className="row">
            <Link className="btn sm" to="/github">
              Browse repositories
            </Link>
            <button
              className="btn sm quiet"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError(null);
                try {
                  await githubApi.disconnect();
                  reload();
                } catch (err) {
                  setError(msg(err));
                } finally {
                  setBusy(false);
                }
              }}
            >
              Disconnect
            </button>
          </div>
        </div>
      ) : (
        <div className="gh-empty">
          <p className="ink2">Connect GitHub to pick repositories from a list instead of pasting URLs, and to import them as cases or projects.</p>
          <div className="row">
            {firebase && (
              <button
                className="btn primary github-btn"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  if (await connectGitHub()) reload();
                  setBusy(false);
                }}
              >
                <GitHubMark />
                Connect GitHub
              </button>
            )}
            {firebase && !showToken && (
              <button className="btn quiet" onClick={() => setShowToken(true)}>
                Use a personal access token instead
              </button>
            )}
          </div>
          {(!firebase || showToken) && <TokenForm onDone={reload} />}
        </div>
      )}
      {(error || authError) && <div className="callout bad">{error ?? authError}</div>}
    </section>
  );
}

function RepoRow({ repo, targets, onImport, busy }: { repo: GitHubRepo; targets: Target[]; onImport: (r: GitHubRepo, t: Target) => void; busy: boolean }) {
  return (
    <div className="gh-repo">
      <div className="minw0">
        <div className="gh-repo-name">
          <b className="mono">{repo.full_name}</b>
          {repo.private && <span className="tag warn">private</span>}
          {repo.fork && <span className="tag neutral">fork</span>}
          {repo.archived && <span className="tag neutral">archived</span>}
        </div>
        {repo.description && <div className="small ink2 gh-desc">{repo.description}</div>}
        <div className="small muted">
          {[repo.language, repo.stars ? `★ ${repo.stars}` : null, repo.default_branch, repo.pushed_at ? `pushed ${fmtTime(repo.pushed_at)}` : null].filter(Boolean).join(" · ")}
        </div>
      </div>
      <div className="row gh-actions">
        {targets.includes("investigation") && (
          <button className="btn sm primary" disabled={busy} onClick={() => onImport(repo, "investigation")}>
            Investigate
          </button>
        )}
        {targets.includes("project") && (
          <button className="btn sm" disabled={busy} onClick={() => onImport(repo, "project")}>
            Add as project
          </button>
        )}
      </div>
    </div>
  );
}

type Target = "investigation" | "project";

/** Browse the connected account's repositories and import one as a case (investigation) or a project. */
export function GitHubImport({ targets = ["investigation", "project"], compact = false }: { targets?: Target[]; compact?: boolean }) {
  const { config, connectGitHub, error: authError } = useAuth();
  const nav = useNavigate();
  const [conn, reload] = useGitHubConnection();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [repos, setRepos] = useState<GitHubRepo[] | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [depth, setDepth] = useState("standard");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<GitHubRepo | null>(null); // repository waiting for its case options
  const connected = conn !== null && conn !== "signed-out" && conn.connected;

  useEffect(() => {
    const t = window.setTimeout(() => setQuery(q.trim()), 300);
    return () => window.clearTimeout(t);
  }, [q]);

  useEffect(() => {
    if (!connected) return;
    let alive = true;
    githubApi
      .repos(query, 1)
      .then((r) => {
        if (!alive) return;
        setRepos(r.repos);
        setPage(1);
        setHasMore(r.has_more);
        setError(null);
      })
      .catch((err) => alive && setError(msg(err)));
    return () => {
      alive = false;
    };
  }, [connected, query]);

  async function more() {
    try {
      const r = await githubApi.repos(query, page + 1);
      setRepos((prev) => [...(prev ?? []), ...r.repos]);
      setPage(r.page);
      setHasMore(r.has_more);
    } catch (err) {
      setError(msg(err));
    }
  }

  function importRepo(repo: GitHubRepo, target: Target) {
    if (target === "investigation") {
      setError(null);
      setPending(repo);
      return;
    }
    void doImport(repo, target);
  }

  async function doImport(repo: GitHubRepo, target: Target, options?: CaseOptions) {
    setBusy(true);
    setError(null);
    try {
      const res = await githubApi.importRepo({ full_name: repo.full_name, target, branch: repo.default_branch, analysis_depth: depth, ...(options ?? {}) });
      if (res.target === "investigation") nav(`/investigations/${res.investigation.investigation_id}`);
      else nav(`/projects/${res.project.project_id}`);
    } catch (err) {
      setError(msg(err));
      setBusy(false);
    }
  }

  if (config?.github?.enabled === false || conn === null) return null;
  if (conn === "signed-out") {
    return (
      <div className="gh-box">
        <div className="gh-box-head">
          <GitHubMark size={18} />
          <b>Import from GitHub</b>
        </div>
        <p className="small ink2">Sign in with GitHub to pick one of your repositories instead of pasting its URL.</p>
      </div>
    );
  }
  if (!conn.connected) {
    return (
      <div className="gh-box">
        <div className="gh-box-head">
          <GitHubMark size={18} />
          <b>Import from GitHub</b>
        </div>
        <p className="small ink2">Connect your GitHub account to pick repositories from a list.</p>
        <div className="row">
          {config?.mode === "firebase" ? (
            <button
              className="btn sm github-btn"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                if (await connectGitHub()) reload();
                setBusy(false);
              }}
            >
              <GitHubMark />
              Connect GitHub
            </button>
          ) : null}
          <Link className="btn sm quiet" to="/settings/account">
            {config?.mode === "firebase" ? "Use a token" : "Connect with a token"}
          </Link>
        </div>
        {authError && <div className="callout bad">{authError}</div>}
      </div>
    );
  }

  return (
    <div className={`gh-box ${compact ? "compact" : ""}`}>
      <div className="gh-box-head">
        <GitHubMark size={18} />
        <b>Your GitHub repositories</b>
        <span className="small muted">
          @{conn.login}
          {conn.private_repos ? " · public and private" : " · public"}
        </span>
      </div>
      <div className="form-row">
        <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by name or description" aria-label="Filter repositories" />
        {targets.includes("investigation") && (
          <select className="input" value={depth} onChange={(e) => setDepth(e.target.value)} aria-label="Investigation depth">
            <option value="quick">Quick</option>
            <option value="standard">Standard</option>
            <option value="deep">Deep</option>
          </select>
        )}
      </div>
      {error && !pending && <div className="callout bad">{error}</div>}
      <div className="gh-list">
        {repos === null ? (
          <p className="small muted">Loading repositories…</p>
        ) : repos.length === 0 ? (
          <p className="small muted">{query ? "No repository matches that filter." : "No repositories found on this account."}</p>
        ) : (
          repos.map((r) => <RepoRow key={r.full_name} repo={r} targets={targets} onImport={importRepo} busy={busy} />)
        )}
        <CaseOptionsDialog
          open={pending !== null}
          repo={pending ? `${pending.full_name} @ ${pending.default_branch}` : ""}
          busy={busy}
          error={pending ? error : null}
          onClose={() => !busy && setPending(null)}
          onStart={(o) => pending && void doImport(pending, "investigation", o)}
        />
        {hasMore && (
          <button className="btn sm quiet" onClick={() => void more()}>
            Load more
          </button>
        )}
      </div>
    </div>
  );
}
