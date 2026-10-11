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
from app.api.account_routes import router as account_router
from app.api.auth import UserResolver
from app.api.project_routes import router as project_router
from app.api.routes import router
from app.config import Settings, get_settings
from app.database import init_db
from app.notifications import NotificationService
from app.observability import configure_logging, get_logger
from app.security.redaction import redact, register_secrets
from app.services.account_store import AccountStore
from app.services.investigation_service import InvestigationService
from app.watch import WatchService

log = get_logger("api")

# The SPA loads its own bundle plus Google Fonts; nothing else.
SPA_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


def spa_csp(settings: Settings) -> str:
    """With Google sign-in on, also allow the Firebase SDK (gstatic), its auth endpoints and the sign-in frame."""
    if settings.auth_mode != "firebase":
        return SPA_CSP
    auth_domain = settings.firebase_auth_domain.strip() or f"{settings.firebase_project_id.strip()}.firebaseapp.com"
    return (
        "default-src 'self'; script-src 'self' https://www.gstatic.com https://apis.google.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https://lh3.googleusercontent.com; "
        "connect-src 'self' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com https://www.googleapis.com; "
        f"frame-src https://{auth_domain} https://accounts.google.com; "
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

    accounts = AccountStore()
    notifier = NotificationService(settings, accounts)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        service = InvestigationService(settings, notifier)
        recovered = service.recover_interrupted()
        app.state.investigations = service
        watches = WatchService(settings, accounts, notifier)
        app.state.watches = watches
        watches.start_scheduler()
        log.info(
            "skopeo api started",
            extra={
                "event_type": "startup",
                "data": {
                    "mode": settings.skopeo_mode,
                    "dry_run": settings.dry_run,
                    "auth": settings.skopeo_api_key is not None,
                    "accounts": settings.auth_mode,
                    "email": settings.email_configured,
                    "static": str(settings.static_dir) if settings.static_dir else None,
                    "recovered_interrupted": recovered,
                },
            },
        )
        yield
        watches.shutdown()
        service.shutdown()

    app = FastAPI(
        title="Skopeo API",
        version=__version__,
        description="Multi-Agent Repository Intelligence & Risk Analysis. All investigation data is read from the persisted Evidence Store.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)
    app.state.account_rate_limiter = RateLimiter(0 if settings.rate_limit_per_minute <= 0 else max(30, settings.rate_limit_per_minute * 5))
    app.state.accounts = accounts
    app.state.notifier = notifier
    app.state.user_resolver = UserResolver(settings, accounts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
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
    app.include_router(account_router)
    app.include_router(project_router)
    if settings.static_dir is not None:
        _mount_frontend(app, settings.static_dir, spa_csp(settings))
    return app


def _mount_frontend(app: FastAPI, static: Path, csp: str = SPA_CSP) -> None:
    root = static.resolve()
    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    def index() -> FileResponse:
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache", "Content-Security-Policy": csp})

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
