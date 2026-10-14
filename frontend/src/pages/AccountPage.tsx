import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Avatar } from "../auth/AccountMenu";
import { GitHubConnectionCard } from "../components/GitHubConnect";
import { useAuth } from "../auth/context";
import { fmtTime } from "../lib/format";
import { accountApi } from "../services/api";

export function AccountPage() {
  const { user, config, signOut } = useAuth();
  const nav = useNavigate();
  const [error, setError] = useState<string | null>(null);
  if (!user || !config) return null;
  const local = user.provider === "local";

  async function remove() {
    if (!window.confirm("Delete your Skopeo account? Your projects, watches, reports and notification channels are deleted permanently. Investigations stay on the server without an owner.")) return;
    try {
      await accountApi.deleteMe();
      await signOut();
      nav("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <main className="page narrow">
      <span className="eyebrow">Settings</span>
      <h1 className="page-title">Account</h1>
      <section className="section">
        <div className="profile">
          <Avatar src={user.photo_url} name={user.display_name ?? user.email} size={56} />
          <div>
            <b className="profile-name">{local ? "Local workspace" : user.display_name}</b>
            <div className="ink2">{user.email}</div>
            <div className="small muted">
              {local ? "This server has no sign-in configured; everything here belongs to one shared local workspace." : `Signed in with ${user.provider === "github" ? "GitHub" : "Google"} · member since ${fmtTime(user.created_at)}`}
            </div>
          </div>
        </div>
      </section>
      <GitHubConnectionCard />
      {!local && (
        <section className="section">
          <div className="section-head">
            <h2>Session</h2>
          </div>
          <button className="btn" onClick={() => void signOut().then(() => nav("/"))}>
            Sign out
          </button>
        </section>
      )}
      {!local && (
        <section className="section">
          <div className="section-head">
            <h2>Delete account</h2>
          </div>
          <p className="ink2">Removes your projects, uploaded files, watches, reports, notification channels, rules, delivery log, GitHub connection and case conversations.</p>
          {error && <div className="callout bad">{error}</div>}
          <button className="btn danger" onClick={() => void remove()}>
            Delete my account
          </button>
        </section>
      )}
    </main>
  );
}
