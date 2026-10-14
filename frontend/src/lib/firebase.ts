/**
 * Google and GitHub sign-in through Firebase Authentication.
 *
 * The Firebase JS SDK is loaded at runtime from Google's CDN (www.gstatic.com), pinned to the
 * version the server reports in /api/auth/config. Nothing Firebase-related is bundled, so a
 * server without Firebase configured never downloads it, and no npm install is needed.
 */
import type { FirebaseWebConfig } from "../types/account";

export interface FirebaseUser {
  uid: string;
  email: string | null;
  displayName: string | null;
  photoURL: string | null;
  getIdToken(forceRefresh?: boolean): Promise<string>;
}

interface FirebaseAuth {
  currentUser: FirebaseUser | null;
}

interface OAuthProvider {
  setCustomParameters(params: Record<string, string>): void;
  addScope?(scope: string): void;
}

interface SignInResult {
  user: FirebaseUser;
  providerId?: string | null;
}

interface OAuthCredential {
  accessToken?: string;
}

interface AppModule {
  initializeApp(config: Record<string, string>, name?: string): unknown;
}

interface AuthModule {
  getAuth(app: unknown): FirebaseAuth;
  GoogleAuthProvider: new () => OAuthProvider;
  GithubAuthProvider: (new () => OAuthProvider) & {
    credentialFromResult(result: SignInResult): OAuthCredential | null;
    credentialFromError(error: unknown): OAuthCredential | null;
  };
  signInWithPopup(auth: FirebaseAuth, provider: OAuthProvider): Promise<SignInResult>;
  signInWithRedirect(auth: FirebaseAuth, provider: OAuthProvider): Promise<never>;
  getRedirectResult(auth: FirebaseAuth): Promise<SignInResult | null>;
  linkWithPopup(user: FirebaseUser, provider: OAuthProvider): Promise<SignInResult>;
  reauthenticateWithPopup(user: FirebaseUser, provider: OAuthProvider): Promise<SignInResult>;
  signOut(auth: FirebaseAuth): Promise<void>;
  onIdTokenChanged(auth: FirebaseAuth, next: (user: FirebaseUser | null) => void): () => void;
}

export type SignInProvider = "google" | "github";

export interface FirebaseSession {
  auth: FirebaseAuth;
  /** Sign in; for GitHub, resolves with the GitHub OAuth access token (to list and import repositories). */
  signIn(provider: SignInProvider, opts?: { privateRepos?: boolean }): Promise<{ githubToken: string | null }>;
  /** Attach GitHub to the signed-in account (e.g. a Google user) and return a GitHub access token. */
  linkGitHub(opts?: { privateRepos?: boolean }): Promise<string | null>;
  /** GitHub token from a sign-in that finished through a full-page redirect, if any. */
  redirectGitHubToken(): Promise<string | null>;
  signOut(): Promise<void>;
  onUserChanged(next: (user: FirebaseUser | null) => void): () => void;
  idToken(): Promise<string | null>;
}

let session: Promise<FirebaseSession> | null = null;

export function loadFirebase(config: FirebaseWebConfig): Promise<FirebaseSession> {
  if (session) return session;
  const version = /^\d+\.\d+\.\d+$/.test(config.sdkVersion) ? config.sdkVersion : "13.0.0";
  const base = `https://www.gstatic.com/firebasejs/${version}`;
  session = (async () => {
    const appMod = (await import(/* @vite-ignore */ `${base}/firebase-app.js`)) as AppModule;
    const authMod = (await import(/* @vite-ignore */ `${base}/firebase-auth.js`)) as AuthModule;
    const app = appMod.initializeApp({
      apiKey: config.apiKey,
      authDomain: config.authDomain,
      projectId: config.projectId,
      ...(config.appId ? { appId: config.appId } : {}),
    });
    const auth = authMod.getAuth(app);
    const google = new authMod.GoogleAuthProvider();
    google.setCustomParameters({ prompt: "select_account" });
    const github = (privateRepos?: boolean) => {
      const p = new authMod.GithubAuthProvider();
      p.addScope?.("read:user");
      if (privateRepos) p.addScope?.("repo"); // read access to private repositories, only when the server allows them
      p.setCustomParameters({ allow_signup: "true" });
      return p;
    };
    const githubToken = (result: SignInResult | null) => (result ? (authMod.GithubAuthProvider.credentialFromResult(result)?.accessToken ?? null) : null);
    return {
      auth,
      async signIn(which, opts) {
        const provider = which === "github" ? github(opts?.privateRepos) : google;
        try {
          const result = await authMod.signInWithPopup(auth, provider);
          return { githubToken: which === "github" ? githubToken(result) : null };
        } catch (err) {
          const code = (err as { code?: string }).code ?? "";
          // Popups can be blocked (mobile browsers, strict settings): fall back to a full-page redirect.
          if (code === "auth/popup-blocked" || code === "auth/operation-not-supported-in-this-environment") {
            await authMod.signInWithRedirect(auth, provider);
            return { githubToken: null };
          }
          throw err;
        }
      },
      async linkGitHub(opts) {
        const user = auth.currentUser;
        if (!user) throw Object.assign(new Error("Sign in first."), { code: "auth/no-current-user" });
        const provider = github(opts?.privateRepos);
        try {
          return githubToken(await authMod.linkWithPopup(user, provider));
        } catch (err) {
          const code = (err as { code?: string }).code ?? "";
          // Already linked to this account: sign in to GitHub again to get a fresh token.
          if (code === "auth/provider-already-linked") return githubToken(await authMod.reauthenticateWithPopup(user, provider));
          throw err;
        }
      },
      async redirectGitHubToken() {
        try {
          const result = await authMod.getRedirectResult(auth);
          return result && result.providerId === "github.com" ? githubToken(result) : null;
        } catch {
          return null;
        }
      },
      signOut: () => authMod.signOut(auth),
      onUserChanged: (next) => authMod.onIdTokenChanged(auth, next),
      idToken: async () => (auth.currentUser ? auth.currentUser.getIdToken() : null),
    };
  })();
  session.catch(() => {
    session = null; // allow a retry after a network failure
  });
  return session;
}

export function describeAuthError(err: unknown): string {
  const code = (err as { code?: string })?.code ?? "";
  const known: Record<string, string> = {
    "auth/popup-closed-by-user": "The sign-in window was closed before finishing.",
    "auth/cancelled-popup-request": "Another sign-in is already open.",
    "auth/unauthorized-domain": "This domain is not authorised for sign-in. Add it under Firebase console > Authentication > Settings > Authorized domains.",
    "auth/operation-not-allowed": "This sign-in method is not enabled. Turn it on under Firebase console > Authentication > Sign-in method.",
    "auth/account-exists-with-different-credential":
      "An account with this email already exists with another sign-in method. Sign in with Google, then connect GitHub from Account settings.",
    "auth/credential-already-in-use": "That GitHub account is already used by another Skopeo account. Sign in with GitHub instead, or use a personal access token.",
    "auth/provider-already-linked": "GitHub is already linked to this account.",
    "auth/network-request-failed": "Network error while signing in. Check your connection and try again.",
    "auth/invalid-api-key": "The Firebase web API key is wrong (FIREBASE_WEB_API_KEY on the server).",
  };
  if (known[code]) return known[code];
  return err instanceof Error ? err.message : String(err);
}
