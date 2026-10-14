import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { AuthProviderId } from "../types/account";
import { useAuth } from "./context";

function GoogleMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden>
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}

export function GitHubMark({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

export function SignInButton({
  label,
  className = "btn",
  provider = "google",
}: {
  label?: string;
  className?: string;
  provider?: AuthProviderId;
}) {
  const { signIn, loading } = useAuth();
  const github = provider === "github";
  return (
    <button className={`${className} ${github ? "github-btn" : "google-btn"}`} onClick={() => void signIn(provider)} disabled={loading}>
      {github ? <GitHubMark /> : <GoogleMark />}
      {label ?? (github ? "Sign in with GitHub" : "Sign in with Google")}
    </button>
  );
}

/** One button per sign-in method the server offers. */
export function SignInChoices({ className = "btn" }: { className?: string }) {
  const { config } = useAuth();
  const providers = config?.providers ?? ["google"];
  return (
    <div className="signin-choices">
      {providers.map((p) => (
        <SignInButton key={p} provider={p} className={className} />
      ))}
    </div>
  );
}

function initials(name: string | null | undefined): string {
  return (name || "?")
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}

export function Avatar({ src, name, size = 26 }: { src: string | null; name: string | null; size?: number }) {
  const [broken, setBroken] = useState(false);
  if (src && !broken) {
    return <img className="avatar" src={src} alt="" width={size} height={size} referrerPolicy="no-referrer" onError={() => setBroken(true)} />;
  }
  return (
    <span className="avatar avatar-text" style={{ width: size, height: size }} aria-hidden>
      {initials(name)}
    </span>
  );
}

export function AccountMenu() {
  const { config, user, loading, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  if (!config || (loading && !user)) return null;
  if (config.mode === "firebase" && !user) {
    return (
      <div className="account" ref={ref}>
        <button className="btn sm" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="menu">
          Sign in
        </button>
        {open && (
          <div className="account-pop signin-pop" role="menu">
            <div className="account-head">
              <b>Sign in to Skopeo</b>
              <span className="small muted">Keep projects, watches, alerts and chats in your account.</span>
            </div>
            <SignInChoices className="btn" />
          </div>
        )}
      </div>
    );
  }
  if (!user) return null;
  const local = user.provider === "local";
  return (
    <div className="account" ref={ref}>
      <button className="account-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="menu" title={user.email ?? undefined}>
        <Avatar src={user.photo_url} name={user.display_name ?? user.email} />
        <span className="hide-sm">{local ? "Local workspace" : (user.display_name ?? user.email)}</span>
      </button>
      {open && (
        <div className="account-pop" role="menu">
          <div className="account-head">
            <b>{local ? "Local workspace" : user.display_name}</b>
            <span className="small muted">{local ? "No sign-in configured on this server" : user.email}</span>
          </div>
          <MenuLink to="/projects" onClick={() => setOpen(false)}>
            Projects and watches
          </MenuLink>
          <MenuLink to="/github" onClick={() => setOpen(false)}>
            GitHub repositories
          </MenuLink>
          <MenuLink to="/settings/notifications" onClick={() => setOpen(false)}>
            Notifications
          </MenuLink>
          <MenuLink to="/settings/account" onClick={() => setOpen(false)}>
            Account
          </MenuLink>
          {!local && (
            <button
              className="account-item"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                void signOut();
              }}
            >
              Sign out
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function MenuLink({ to, children, onClick }: { to: string; children: ReactNode; onClick: () => void }) {
  return (
    <Link className="account-item" role="menuitem" to={to} onClick={onClick}>
      {children}
    </Link>
  );
}

/** Wraps pages that need an account: shows a sign-in prompt instead when signed out. */
export function RequireUser({ children, what }: { children: ReactNode; what: string }) {
  const { config, user, loading, error } = useAuth();
  if (loading || !config) {
    return (
      <main className="page">
        <p className="muted">Loading your account…</p>
      </main>
    );
  }
  if (!user) {
    return (
      <main className="page">
        <div className="signin-card">
          <span className="eyebrow">Sign in required</span>
          <h1>Sign in to manage {what}</h1>
          <p className="ink2">
            Your projects, watched repositories and notification channels belong to your account. Skopeo uses your Google or GitHub account to know who you are; with GitHub it can also list
            your repositories so you can import them. It never posts anything on your behalf.
          </p>
          {config.mode === "firebase" ? <SignInChoices className="btn primary" /> : <div className="callout warn">Accounts are not available on this server.</div>}
          {error && <div className="callout bad">{error}</div>}
        </div>
      </main>
    );
  }
  return <>{children}</>;
}
