"""DATABASE_URL handling for hosted PostgreSQL (Neon, Supabase, Railway, Render)."""

from __future__ import annotations

import pytest

from app.config.settings import Settings


@pytest.mark.parametrize(
    "given, expected",
    [
        ("postgres://u:pw@ep-x.neon.tech/db?sslmode=require", "postgresql+psycopg://u:pw@ep-x.neon.tech/db?sslmode=require"),
        ("postgresql://u:pw@h:5432/db", "postgresql+psycopg://u:pw@h:5432/db"),
        ("postgresql+psycopg://u:pw@h/db", "postgresql+psycopg://u:pw@h/db"),
        ("sqlite:///./x.db", "sqlite:///./x.db"),
    ],
)
def test_postgres_urls_use_the_bundled_driver(given, expected, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", given)
    assert Settings().database_url == expected


def test_blank_database_url_falls_back_to_sqlite(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "  ")
    assert Settings().database_url.startswith("sqlite:///") and Settings().database_url.endswith("skopeo.db")


def test_database_password_is_redacted(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:s3cret-pw@h/db")
    assert "s3cret-pw" in Settings().secret_values()
