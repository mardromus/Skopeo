import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { describeAuthError, loadFirebase, type FirebaseSession } from "../lib/firebase";
import { accountApi, githubApi, setIdTokenProvider } from "../services/api";
import type { AccountUser, AuthConfig, AuthProviderId } from "../types/account";
import { AuthContext, type AuthState } from "./context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [user, setUser] = useState<AccountUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const firebase = useRef<FirebaseSession | null>(null);
  const [githubVersion, setGithubVersion] = useState(0);
  const privateRepos = Boolean(config?.github?.private_repos);

  /** Store the GitHub OAuth token server-side (encrypted) so repositories can be listed and imported. */
  const saveGitHubToken = useCallback(async (token: string | null) => {
    if (!token) return false;
    try {
      await githubApi.connect(token, "oauth");
      setGithubVersion((v) => v + 1);
      return true;
    } catch (err) {
      setError(`Signed in, but GitHub could not be connected: ${err instanceof Error ? err.message : String(err)}`);
      return false;
    }
  }, []);

  const loadMe = useCallback(async () => {
    try {
      setUser(await accountApi.me());
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    let unsubscribe: (() => void) | undefined;
    let alive = true;
    accountApi
      .config()
      .then(async (cfg) => {
        if (!alive) return;
        setConfig(cfg);
        if (cfg.mode === "local" || !cfg.firebase) {
          await loadMe();
          setLoading(false);
          return;
        }
        const fb = await loadFirebase(cfg.firebase);
        if (!alive) return;
        firebase.current = fb;
        setIdTokenProvider(() => fb.idToken());
        let pendingRedirect: Promise<string | null> | null = fb.redirectGitHubToken();
        unsubscribe = fb.onUserChanged(async (fbUser) => {
          if (fbUser) {
            await loadMe();
            if (pendingRedirect) {
              const token = await pendingRedirect;
              pendingRedirect = null;
              if (token) await saveGitHubToken(token);
            }
          } else setUser(null);
          setLoading(false);
        });
      })
      .catch((err) => {
        if (!alive) return;
        setError(`Sign-in is unavailable: ${describeAuthError(err)}`);
        setLoading(false);
      });
    return () => {
      alive = false;
      unsubscribe?.();
    };
  }, [loadMe, saveGitHubToken]);

  const signIn = useCallback(
    async (provider: AuthProviderId = "google") => {
      setError(null);
      if (!firebase.current) {
        setError("Sign-in is not configured on this server.");
        return;
      }
      try {
        const { githubToken } = await firebase.current.signIn(provider, { privateRepos });
        if (githubToken) {
          await loadMe(); // make sure the account exists before attaching GitHub to it
          await saveGitHubToken(githubToken);
        }
      } catch (err) {
        setError(describeAuthError(err));
      }
    },
    [privateRepos, loadMe, saveGitHubToken],
  );

  const connectGitHub = useCallback(async () => {
    setError(null);
    if (!firebase.current) return false;
    try {
      return await saveGitHubToken(await firebase.current.linkGitHub({ privateRepos }));
    } catch (err) {
      setError(describeAuthError(err));
      return false;
    }
  }, [privateRepos, saveGitHubToken]);

  const signOut = useCallback(async () => {
    await firebase.current?.signOut();
    setUser(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ config, user, loading, error, signIn, connectGitHub, githubVersion, signOut, refresh: loadMe }),
    [config, user, loading, error, signIn, connectGitHub, githubVersion, signOut, loadMe],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
