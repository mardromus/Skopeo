"""Programmatic Alembic upgrade so the API container migrates on start."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def alembic_config(engine: Engine | None = None) -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "migrations"))
    if engine is not None:
        cfg.attributes["engine"] = engine
    return cfg


def upgrade_to_head(engine: Engine) -> None:
    cfg = alembic_config(engine)
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
