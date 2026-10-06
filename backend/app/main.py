"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import router
from app.config import Settings, get_settings
from app.database import init_db
from app.observability import configure_logging, get_logger
from app.security.redaction import redact, register_secrets
from app.services.investigation_service import InvestigationService

log = get_logger("api")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    register_secrets(settings.secret_values())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        app.state.investigations = InvestigationService(settings)
        log.info("skopeo api started", extra={"event_type": "startup", "data": {"mode": settings.skopeo_mode, "dry_run": settings.dry_run}})
        yield
        app.state.investigations.shutdown()

    app = FastAPI(
        title="Skopeo API",
        version=__version__,
        description="Multi-Agent Repository Intelligence & Risk Analysis. All investigation data is read from the persisted Evidence Store.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e.get("loc", [])), "msg": redact(str(e.get("msg", "")))} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    app.include_router(router)
    return app


app = create_app()
