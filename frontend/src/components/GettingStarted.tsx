import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { SignInButton } from "../auth/AccountMenu";
import { useAuth } from "../auth/context";
import { notificationsApi, projectsApi } from "../services/api";

interface Progress {
  channels: number;
  projects: number;
  watches: number;
}

/** The signed-in user flow, as a checklist on the landing page. */
export function GettingStarted() {
  const { config, user, error } = useAuth();
  const [progress, setProgress] = useState<Progress | null>(null);

  useEffect(() => {
    if (!user) return;
    Promise.all([notificationsApi.channels(), projectsApi.list()])
      .then(([channels, projects]) =>
        setProgress({
          channels: channels.filter((c) => c.verified && c.enabled).length,
          projects: projects.length,
          watches: projects.reduce((n, p) => n + p.watches.length, 0),
        }),
      )
      .catch(() => setProgress(null));
  }, [user]);

  if (!config) return null;
  if (!user) {
    if (config.mode !== "firebase") return null;
    return (
      <section className="onboard">
        <div className="minw0">
          <span className="eyebrow">Keep watch over your own software</span>
          <p className="ink2">
            Sign in to get notified when a case finishes, and to watch the open-source repositories your project depends on: Skopeo tells you which lines of your code their changes affect.
          </p>
          {error && <div className="callout bad">{error}</div>}
        </div>
        <div className="signin-choices">
          <SignInButton className="btn primary" provider="google" />
          {(config.providers ?? ["google"]).includes("github") && <SignInButton className="btn" provider="github" />}
        </div>
      </section>
    );
  }
  if (!progress) return null;
  const steps = [
    { done: user.provider !== "local", label: "Sign in with Google or GitHub", hint: "Your projects and channels belong to your account.", to: null, skip: user.provider === "local" },
    { done: progress.channels > 0, label: "Connect a notification channel", hint: "Email, Slack, Discord or a webhook.", to: "/settings/notifications" },
    { done: progress.projects > 0, label: "Connect your project", hint: "A GitHub repository, or upload the files that use your dependencies.", to: "/projects" },
    { done: progress.watches > 0, label: "Watch an open-source dependency", hint: "See how its changes affect your code, on every release.", to: "/projects" },
  ].filter((s) => !s.skip);
  const remaining = steps.filter((s) => !s.done).length;
  if (remaining === 0) {
    return (
      <section className="onboard compact">
        <span className="small ink2">
          Watching {progress.watches} {progress.watches === 1 ? "repository" : "repositories"} across {progress.projects} {progress.projects === 1 ? "project" : "projects"}, with {progress.channels} active{" "}
          {progress.channels === 1 ? "channel" : "channels"}.
        </span>
        <Link to="/projects" className="btn sm">
          Open projects
        </Link>
      </section>
    );
  }
  return (
    <section className="onboard">
      <div className="minw0">
        <span className="eyebrow">Get started · {steps.length - remaining} of {steps.length} done</span>
        <ol className="steps">
          {steps.map((s) => (
            <li key={s.label} className={s.done ? "done" : ""}>
              <span className="tick" aria-hidden>
                {s.done ? "✓" : ""}
              </span>
              <div className="minw0">
                {s.to && !s.done ? <Link to={s.to}>{s.label}</Link> : <b>{s.label}</b>}
                <div className="small muted">{s.hint}</div>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
