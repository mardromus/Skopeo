import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { describeAuthError, loadFirebase, type FirebaseSession } from "../lib/firebase";
import { accountApi, setIdTokenProvider } from "../services/api";
import type { AccountUser, AuthConfig } from "../types/account";
import { AuthContext, type AuthState } from "./context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [user, setUser] = useState<AccountUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const firebase = useRef<FirebaseSession | null>(null);

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
        unsubscribe = fb.onUserChanged(async (fbUser) => {
          if (fbUser) await loadMe();
          else setUser(null);
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
  }, [loadMe]);

  const signIn = useCallback(async () => {
    setError(null);
    if (!firebase.current) {
      setError("Sign-in is not configured on this server.");
      return;
    }
    try {
      await firebase.current.signInWithGoogle();
    } catch (err) {
      setError(describeAuthError(err));
    }
  }, []);

  const signOut = useCallback(async () => {
    await firebase.current?.signOut();
    setUser(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ config, user, loading, error, signIn, signOut, refresh: loadMe }),
    [config, user, loading, error, signIn, signOut, loadMe],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
