# Deployment

Skopeo ships as **one container**: FastAPI serves the API under `/api` and the built UI for every
other path, on `$PORT` (default 8000). Anything that runs a Dockerfile can host it.

```bash
docker build -t skopeo .
docker run -p 8000:8000 -v skopeo-data:/data skopeo
```

Open http://localhost:8000. With Compose: `docker compose up --build`.

The image runs as a non-root user, keeps all state in `/data` (SQLite database and temporary
clones), deletes each clone when its investigation ends, and exposes `/api/health` for health checks.

## Using Groq as the LLM

Create a key at <https://console.groq.com/keys> and set, on any host:

```bash
SKOPEO_MODE=live
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
# optional overrides
GROQ_MODEL_REASONING=openai/gpt-oss-120b
GROQ_MODEL_FAST=openai/gpt-oss-20b
```

The Render blueprint and `docker-compose.yml` already set `SKOPEO_MODE=live` and `LLM_PROVIDER=groq`;
paste only the key (Render asks for it on the first deploy). Until a key is present the app runs its
deterministic policies, so a deploy without a key still works. `GET /api/health` shows
`"llm_provider": "groq"` and `"llm_key_configured": true` once Groq is active. Groq's free tier is
rate-limited; 429 responses are retried with back-off and any call that still fails falls back to
the deterministic policy for that decision.

## Keeping data on free hosting: PostgreSQL on Neon

Free container hosts (Render's free plan, Cloud Run) have no persistent disk, so the default SQLite
file is erased on every restart. Point Skopeo at a free hosted PostgreSQL database instead and
nothing is lost:

1. Create a free project at <https://neon.com> (no credit card). Pick the region closest to your
   host (Render's Oregon / Frankfurt / Singapore → the matching AWS region).
2. On the project dashboard click **Connect** and copy the connection string, e.g.
   `postgresql://neondb_owner:...@ep-xxx.region.aws.neon.tech/neondb?sslmode=require`.
3. Set it as `DATABASE_URL` on the host. `postgres://` and `postgresql://` URLs are accepted as
   given; the psycopg 3 driver is bundled. Migrations run automatically at start-up.
4. Set `SKOPEO_SECRET_KEY` (the Render blueprint generates it). Without it, the key that encrypts
   stored GitHub tokens would live on the erased disk.
5. Set `WATCH_SCHEDULER_INTERVAL_SECONDS=1800` (the blueprint does). Neon's free compute sleeps
   after 5 minutes without queries and allows 100 compute-hours a month; one scheduler query
   every 30 minutes keeps usage around 30 hours, where the default 60 s would keep it awake.

Cloned repositories still live on the container's temporary disk; they are deleted after each
case anyway. Any PostgreSQL works the same way (Supabase, Railway, a VM). To run the test suite
against PostgreSQL: `SKOPEO_TEST_DATABASE_URL=postgresql://... pytest` (it wipes that database's
public schema).

## Render (free tier)

The repository contains a blueprint (`render.yaml`).

1. Fork or use https://github.com/mardromus/Skopeo.
2. In Render: **New → Blueprint**, pick the repository, and apply. Or use the button in the README.
3. Render builds the Dockerfile, generates `SKOPEO_API_KEY`, and deploys at `https://skopeo-xxxx.onrender.com`.
4. Find the generated key under *Environment* if you want to scan real repositories; the
   reference case works without it.

The free plan sleeps after 15 minutes without traffic (the next request takes about a minute)
and has no persistent disk: set `DATABASE_URL` to a free Neon database (above) so accounts,
cases and watches survive restarts. On a paid plan the commented `disk:` block works too.
The free plan also blocks outbound SMTP ports 25, 465 and 587 (the error is
`SMTP error: OSError: [Errno 101] Network is unreachable`). Send email over HTTPS instead:
create a free [Brevo](https://www.brevo.com) account (about 300 emails a day, verify one sender
address, no domain needed), create an API key (SMTP & API → API Keys), then set
`EMAIL_PROVIDER=brevo`, `EMAIL_API_KEY=<key>` and `SMTP_FROM="Skopeo <your verified sender>"`.
Resend works the same way (`EMAIL_PROVIDER=resend`) but only delivers to other people once you
verify a domain. Leave the `SMTP_*` host and password empty.

## Railway

**New Project → Deploy from GitHub repo**. Railway detects the Dockerfile and sets `PORT`.
Add a volume mounted at `/data` to keep cases, and set the variables below.

## Fly.io

```bash
fly launch --no-deploy        # detects the Dockerfile; choose a region
fly volumes create skopeo_data --size 1
```

In `fly.toml`, set `internal_port = 8000` and mount the volume at `/data`, then `fly deploy`.

## Google Cloud Run

```bash
gcloud run deploy skopeo --source . --port 8000 --allow-unauthenticated \
  --set-env-vars SKOPEO_DEMO_MODE=true,MAX_CONCURRENT_INVESTIGATIONS=1 --no-cpu-throttling
```

Use `--no-cpu-throttling` (or a minimum of one instance): investigations run in background
threads after the HTTP request that started them returns. Storage is ephemeral unless you
attach a volume.

## A plain VM

```bash
git clone https://github.com/mardromus/Skopeo && cd Skopeo
cp .env.example .env            # set SKOPEO_API_KEY at least
docker compose up -d --build
```

Put a TLS-terminating reverse proxy (Caddy, nginx) in front of port 8000.

## Settings for a public deployment

| Variable | Recommended | Why |
| --- | --- | --- |
| `SKOPEO_API_KEY` | a long random string | anyone can otherwise make the server clone arbitrary repositories |
| `SKOPEO_DEMO_PUBLIC` | `true` | the reference case is offline and cheap, so evaluators can try it without the key |
| `RATE_LIMIT_PER_MINUTE` | `4` | investigations started per client address per minute |
| `MAX_CONCURRENT_INVESTIGATIONS` | `1` on small instances | each case uses one CPU while it runs |
| `DRY_RUN` | `true` | approved GitHub actions are recorded, never sent |
| `SKOPEO_SANDBOX_EXECUTION` | `false` | keeps untrusted repositories' tests and benchmarks from running |
| `SKOPEO_KEEP_WORKSPACES` | `false` (image default) | deletes clones after each case |
| `SKOPEO_MODE` / `OPENAI_API_KEY` | `mock`, or `live` + key | live mode sends redacted excerpts to the model provider |
| `CORS_ORIGINS` | empty | the UI is served from the same origin; only needed for a separately hosted UI |

With a key set, the UI shows an *Access key* field. The key is sent as `X-Skopeo-Key` (or
`Authorization: Bearer …`) and is required to start, cancel or approve anything; all reads stay public.

## Operating notes

* **Run one worker.** Investigations run in background threads of the API process. Several
  workers would each have their own threads, and a restart of one would mark another's cases as
  interrupted.
* **Restarts.** On start-up, investigations left running by a previous process are marked failed
  with *Interrupted: the server restarted …*, so nothing stays "running" forever.
* **Security headers.** API responses carry `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy` and `Permissions-Policy`; the UI page adds a Content-Security-Policy that only
  allows its own scripts and Google Fonts.
* **Logs** are JSON lines on stdout, with secrets redacted.
* **CI** (`.github/workflows/ci.yml`) lints and tests both halves, builds the image, starts it and
  runs the reference investigation inside it on every push.
