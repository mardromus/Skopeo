# Single-container image: the API serves the built UI. Deploys anywhere that runs a Dockerfile
# (Render, Railway, Fly.io, Cloud Run, a VM). Listens on $PORT (default 8000).
#
#   docker build -t skopeo .
#   docker run -p 8000:8000 -v skopeo-data:/data skopeo

# ---- 1. build the frontend ----------------------------------------------------------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. runtime ------------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# git clones the repositories under investigation (through Skopeo's allowlisted runner).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 skopeo

WORKDIR /app/backend
COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY backend/ /app/backend/
COPY examples/ /app/examples/
COPY --from=web /web/dist /app/frontend/dist

ENV PORT=8000 \
    SKOPEO_EXAMPLES_DIR=/app/examples \
    SKOPEO_STATIC_DIR=/app/frontend/dist \
    DATABASE_URL=sqlite:////data/skopeo.db \
    SKOPEO_WORKSPACE_DIR=/data/workspaces \
    SKOPEO_KEEP_WORKSPACES=false \
    LOG_JSON=true

RUN mkdir -p /data/workspaces && chown -R skopeo:skopeo /data /app
USER skopeo
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=40s --retries=5 \
  CMD python -c "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health', timeout=4).status == 200 else 1)"

# One worker on purpose: investigations run in background threads of this process.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
