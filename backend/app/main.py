"""FastAPI application factory.

In a single-container deployment the API also serves the built frontend (``frontend/dist``):
``/assets/*`` as immutable static files and every other non-API path as the SPA's
``index.html``, so deep links such as ``/investigations/<id>?tab=trace`` work.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.access import RateLimiter
from app.api.routes import router
from app.config import Settings, get_settings
from app.database import init_db
from app.observability import configure_logging, get_logger
from app.security.redaction import redact, register_secrets
from app.services.investigation_service import InvestigationService

log = get_logger("api")

# The SPA loads its own bundle plus Google Fonts; nothing else.
SPA_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    register_secrets(settings.secret_values())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        service = InvestigationService(settings)
        recovered = service.recover_interrupted()
        app.state.investigations = service
        log.info(
            "skopeo api started",
            extra={
                "event_type": "startup",
                "data": {
                    "mode": settings.skopeo_mode,
                    "dry_run": settings.dry_run,
                    "auth": settings.skopeo_api_key is not None,
                    "static": str(settings.static_dir) if settings.static_dir else None,
                    "recovered_interrupted": recovered,
                },
            },
        )
        yield
        service.shutdown()

    app = FastAPI(
        title="Skopeo API",
        version=__version__,
        description="Multi-Agent Repository Intelligence & Risk Analysis. All investigation data is read from the persisted Evidence Store.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Skopeo-Key", "Authorization"],
    )

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e.get("loc", [])), "msg": redact(str(e.get("msg", "")))} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    app.include_router(router)
    if settings.static_dir is not None:
        _mount_frontend(app, settings.static_dir)
    return app


def _mount_frontend(app: FastAPI, static: Path) -> None:
    root = static.resolve()
    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    def index() -> FileResponse:
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache", "Content-Security-Policy": SPA_CSP})

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa_root() -> FileResponse:
        return index()

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path.startswith("api/") or path == "api":
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (root / path).resolve()
        if candidate.is_file() and root in candidate.parents:
            return FileResponse(candidate, headers={"Cache-Control": "public, max-age=3600"})
        return index()


app = create_app()
