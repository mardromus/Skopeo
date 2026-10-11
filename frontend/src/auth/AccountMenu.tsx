import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
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

export function SignInButton({ label = "Sign in with Google", className = "btn" }: { label?: string; className?: string }) {
  const { signIn, loading } = useAuth();
  return (
    <button className={`${className} google-btn`} onClick={() => void signIn()} disabled={loading}>
      <GoogleMark />
      {label}
    </button>
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
  if (config.mode === "firebase" && !user) return <SignInButton className="btn sm" label="Sign in" />;
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
            Your projects, watched repositories and notification channels belong to your account. Skopeo uses your Google account only to know who you are; it never posts anything on your
            behalf.
          </p>
          {config.mode === "firebase" ? <SignInButton className="btn primary" /> : <div className="callout warn">Accounts are not available on this server.</div>}
          {error && <div className="callout bad">{error}</div>}
        </div>
      </main>
    );
  }
  return <>{children}</>;
}
