# Build from the repository root:  docker build -f backend/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# git is required to clone repositories under investigation (via the allowlisted runner).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 skopeo

WORKDIR /app/backend
COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY backend/ /app/backend/
COPY examples/ /app/examples/

ENV SKOPEO_EXAMPLES_DIR=/app/examples \
    DATABASE_URL=sqlite:////data/skopeo.db \
    SKOPEO_WORKSPACE_DIR=/data/workspaces \
    LOG_JSON=true

RUN mkdir -p /data/workspaces && chown -R skopeo:skopeo /data /app
USER skopeo
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
