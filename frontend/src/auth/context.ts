import { createContext, useContext } from "react";
import type { AccountUser, AuthConfig, AuthProviderId } from "../types/account";

export interface AuthState {
  /** Server sign-in configuration; null until loaded. */
  config: AuthConfig | null;
  /** The account as the server knows it (local mode: the built-in local user). */
  user: AccountUser | null;
  /** True while the config, the Firebase SDK or the session are still loading. */
  loading: boolean;
  error: string | null;
  signIn: (provider?: AuthProviderId) => Promise<void>;
  /** Connect GitHub to the signed-in account through Firebase (GitHub OAuth); returns true when connected. */
  connectGitHub: () => Promise<boolean>;
  /** Bumped whenever the GitHub connection changes, so views can reload it. */
  githubVersion: number;
  signOut: () => Promise<void>;
  /** Reload the account from the server. */
  refresh: () => Promise<void>;
}

export const AuthContext = createContext<AuthState>({
  config: null,
  user: null,
  loading: true,
  error: null,
  signIn: async () => {},
  connectGitHub: async () => false,
  githubVersion: 0,
  signOut: async () => {},
  refresh: async () => {},
});

export function useAuth(): AuthState {
  return useContext(AuthContext);
}
