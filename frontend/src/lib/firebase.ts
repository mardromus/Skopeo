/**
 * Google sign-in through Firebase Authentication.
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

interface GoogleProvider {
  setCustomParameters(params: Record<string, string>): void;
}

interface AppModule {
  initializeApp(config: Record<string, string>, name?: string): unknown;
}

interface AuthModule {
  getAuth(app: unknown): FirebaseAuth;
  GoogleAuthProvider: new () => GoogleProvider;
  signInWithPopup(auth: FirebaseAuth, provider: GoogleProvider): Promise<{ user: FirebaseUser }>;
  signInWithRedirect(auth: FirebaseAuth, provider: GoogleProvider): Promise<never>;
  signOut(auth: FirebaseAuth): Promise<void>;
  onIdTokenChanged(auth: FirebaseAuth, next: (user: FirebaseUser | null) => void): () => void;
}

export interface FirebaseSession {
  auth: FirebaseAuth;
  signInWithGoogle(): Promise<void>;
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
    const provider = new authMod.GoogleAuthProvider();
    provider.setCustomParameters({ prompt: "select_account" });
    return {
      auth,
      async signInWithGoogle() {
        try {
          await authMod.signInWithPopup(auth, provider);
        } catch (err) {
          const code = (err as { code?: string }).code ?? "";
          // Popups can be blocked (mobile browsers, strict settings): fall back to a full-page redirect.
          if (code === "auth/popup-blocked" || code === "auth/operation-not-supported-in-this-environment") {
            await authMod.signInWithRedirect(auth, provider);
            return;
          }
          throw err;
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
    "auth/operation-not-allowed": "Google sign-in is not enabled. Turn it on under Firebase console > Authentication > Sign-in method.",
    "auth/network-request-failed": "Network error while signing in. Check your connection and try again.",
    "auth/invalid-api-key": "The Firebase web API key is wrong (FIREBASE_WEB_API_KEY on the server).",
  };
  if (known[code]) return known[code];
  return err instanceof Error ? err.message : String(err);
}
