# Google and GitHub sign-in with Firebase

Skopeo uses **Firebase Authentication** for "Sign in with Google" and "Sign in with GitHub". The browser signs in with
Firebase, then sends the Firebase **ID token** to the API with every request
(`Authorization: Bearer <token>`). The API verifies each token itself (RS256 signature against
Google's published certificates, audience, issuer, expiry), so the backend needs **no service
account and no Firebase Admin SDK**: only the project id.

Without `FIREBASE_PROJECT_ID` the server runs in **local mode**: no sign-in, and one built-in
"Local workspace" user owns all projects, watches and channels. That is the default for
development, and everything except sign-in works the same.

Allow about 10 minutes.

## 1. Create the Firebase project

1. Open <https://console.firebase.google.com> and click **Create a project** (or **Add project**).
2. Name it, for example `skopeo`. Note the **project ID** shown under the name (e.g. `skopeo-4f2a1`).
   This is not always identical to the name.
3. Google Analytics is not needed. You can turn it off.

## 2. Turn on Google sign-in

1. In the project, open **Build → Authentication → Get started**.
2. On **Sign-in method**, choose **Google**, switch it to **Enabled**, pick a **support email**
   and **Save**.

## 2b. Turn on GitHub sign-in (optional, lets users import their repositories)

Signing in with GitHub also hands Skopeo a GitHub access token, so users can pick repositories
from a list (**GitHub** in the top bar) and import them as cases or projects, and later ask the
agents questions about them. Google users can attach GitHub from **Account → GitHub**.

1. In Firebase: **Authentication → Sign-in method → Add new provider → GitHub → Enable**. Copy
   the **callback URL** it shows (`https://<project-id>.firebaseapp.com/__/auth/handler`).
2. On GitHub: **Settings → Developer settings → OAuth Apps → New OAuth App**.
   *Homepage URL*: your Skopeo URL. *Authorization callback URL*: the URL from step 1.
   Register it, then **Generate a new client secret**.
3. Back in Firebase, paste the GitHub **Client ID** and **Client secret** and **Save**.
4. On the server, keep `AUTH_GITHUB_ENABLED=true` (default) and set `SKOPEO_SECRET_KEY` to a long
   random value: GitHub tokens are stored encrypted with it and never returned by the API.
5. Private repositories are off by default. With `GITHUB_PRIVATE_REPOS=true` the sign-in also asks
   for GitHub's `repo` scope; a private repository is cloned with its owner's token (passed to git
   in the environment, never in the URL or on disk), and the case is visible only to its owner.

If an email address already belongs to a Google account, GitHub sign-in reports
`auth/account-exists-with-different-credential`: sign in with Google and connect GitHub from
**Account** instead. Without Firebase (local mode), connect GitHub with a **personal access
token** on the Account page.

## 3. Register the web app and copy its config

1. Open **Project settings** (gear icon) → **General** → **Your apps** → the **Web** icon (`</>`).
2. Give it a nickname (`skopeo-web`). Firebase Hosting is not needed. Click **Register app**.
3. Firebase shows a `firebaseConfig` object. You need four values from it:

| `firebaseConfig` field | Skopeo variable |
| --- | --- |
| `apiKey` | `FIREBASE_WEB_API_KEY` |
| `authDomain` | `FIREBASE_AUTH_DOMAIN` |
| `projectId` | `FIREBASE_PROJECT_ID` |
| `appId` | `FIREBASE_APP_ID` |

The web `apiKey` is **not a secret**: it identifies the project to Google and is served to every
browser. Access is protected by the authorized-domains list (next step) and by the backend's
token verification.

## 4. Authorize your domains

**Authentication → Settings → Authorized domains** must list every host the UI is served from:

* `localhost` is there by default (covers `http://localhost:5173` and `http://localhost:8000`);
* add your deployment's host, e.g. `skopeo.onrender.com` or `skopeo.example.com`.

Signing in from a domain that is not listed fails with `auth/unauthorized-domain`. Skopeo shows
that message with this fix.

## 5. Configure Skopeo

In `.env` (local) or your host's environment settings (Render, Railway, Fly, Cloud Run):

```bash
FIREBASE_PROJECT_ID=skopeo-4f2a1
FIREBASE_WEB_API_KEY=AIzaSy...
FIREBASE_AUTH_DOMAIN=skopeo-4f2a1.firebaseapp.com
FIREBASE_APP_ID=1:1234567890:web:abc123
# optional
AUTH_REQUIRE_LOGIN=false             # true: scanning repositories needs an account (the reference case stays public)
AUTH_SIGNED_IN_USERS_CAN_SCAN=true   # with SKOPEO_API_KEY set, signed-in users may scan without the shared key
PUBLIC_BASE_URL=https://skopeo.example.com   # links inside emails / Slack messages
```

Restart the API. `GET /api/auth/config` should now report `"mode": "firebase"`, and the top bar
shows **Sign in**.

No frontend rebuild is needed: the UI reads this configuration from the API at runtime and loads
the Firebase JS SDK (pinned by `FIREBASE_SDK_VERSION`, default `13.0.0`) from `www.gstatic.com`.
When Firebase is configured, the API's Content-Security-Policy automatically allows exactly
the origins sign-in needs (`www.gstatic.com`, `apis.google.com`, the Identity Toolkit and Secure
Token endpoints, your `authDomain` frame, and Google profile photos).

## 6. Try it

1. Open the UI and click **Sign in with Google**. A Google account chooser opens in a popup. If
   the browser blocks popups, Skopeo falls back to a full-page redirect.
2. After sign-in, your avatar appears top right. The landing page shows a **Get started**
   checklist: connect a notification channel → connect your project → watch a dependency.
3. `GET /api/auth/me` with the token returns your account. The first request creates it.

## How it is enforced

| Area | Without sign-in | Signed in |
| --- | --- | --- |
| Reference case, reading cases | open | open |
| Scanning a repository | open, or the shared `SKOPEO_API_KEY` if set; or blocked with `AUTH_REQUIRE_LOGIN=true` | allowed (owner recorded on the case) |
| Projects, watches, reports | 401 | only your own |
| Notification channels, rules, delivery log | 401 | only your own |
| `DELETE /api/auth/me` | — | deletes your account and everything it owns |

Each project, watch, report and channel query is scoped to the user who owns it. Another
account's row behaves exactly like a missing row (404).

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `auth/unauthorized-domain` | Add the host under Authentication → Settings → Authorized domains. |
| `auth/operation-not-allowed` | Enable the Google provider (step 2) or the GitHub provider (step 2b). |
| GitHub popup shows "redirect_uri is not associated" | The GitHub OAuth App's callback URL must be exactly Firebase's `/__/auth/handler` URL. |
| "Private repositories are not enabled" (403) on import | Set `GITHUB_PRIVATE_REPOS=true`, then reconnect GitHub so it grants the `repo` scope. |
| `auth/invalid-api-key` | `FIREBASE_WEB_API_KEY` is wrong; copy `apiKey` again from Project settings. |
| API returns 401 "token rejected: InvalidAudienceError" | `FIREBASE_PROJECT_ID` does not match the project the browser signed in to. |
| "could not load Google signing certificates" | The API cannot reach `www.googleapis.com`. Allow outbound HTTPS to it. |
| Sign-in works locally, not in production | `PUBLIC_BASE_URL` / authorized domain missing, or an old browser tab is still using the previous build; reload. |
