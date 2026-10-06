"""Database engine / session management.

SQLite is the MVP backend. The models only use portable column types (String UUIDs,
JSON, DateTime with timezone) so PostgreSQL can be swapped in via DATABASE_URL.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.observability import get_logger

log = get_logger("database")

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_lock = threading.Lock()

# SQLite allows a single writer. All blackboard writes are serialised through this lock so
# parallel agents never hit "database is locked" errors. Reads remain concurrent (WAL mode).
write_lock = threading.RLock()


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _record):  # pragma: no cover - driver callback
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()


def create_db_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        if ":memory:" in url or url == "sqlite://":
            engine = create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True)
        else:
            db_path = url.split("///", 1)[-1]
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30}, future=True)
        _configure_sqlite(engine)
        return engine
    return create_engine(url, pool_pre_ping=True, future=True)


def get_engine() -> Engine:
    global _engine, _session_factory
    with _lock:
        if _engine is None:
            _engine = create_db_engine(get_settings().database_url)
            _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
        return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


def reset_engine() -> None:
    """Dispose the engine (used by tests that switch DATABASE_URL)."""
    global _engine, _session_factory
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _session_factory = None


@contextmanager
def session_scope(write: bool = False) -> Iterator[Session]:
    factory = get_session_factory()
    if write:
        with write_lock:
            session = factory()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
    else:
        session = factory()
        try:
            yield session
        finally:
            session.close()


def init_db() -> None:
    """Create / upgrade the schema.

    Runs Alembic migrations (the source of truth for the schema). Falls back to
    ``metadata.create_all`` when migrations are disabled (unit tests).
    """
    settings = get_settings()
    engine = get_engine()
    if settings.skopeo_run_migrations:
        from app.database.migrate import upgrade_to_head

        upgrade_to_head(engine)
    else:
        from app.models import Base

        Base.metadata.create_all(engine)
    log.info("database ready", extra={"event_type": "db_ready"})
