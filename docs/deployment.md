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

## Render (free tier)

The repository contains a blueprint (`render.yaml`).

1. Fork or use https://github.com/mardromus/Skopeo.
2. In Render: **New → Blueprint**, pick the repository, and apply. Or use the button in the README.
3. Render builds the Dockerfile, generates `SKOPEO_API_KEY`, and deploys at `https://skopeo-xxxx.onrender.com`.
4. Find the generated key under *Environment* if you want to scan real repositories; the
   reference case works without it.

The free plan sleeps when idle (the first request takes about a minute) and has no persistent
disk, so cases disappear on restart. Add the commented `disk:` block on a paid plan to keep them.

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
