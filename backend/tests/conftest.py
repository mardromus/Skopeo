"""Test configuration: isolated temp database + workspace, mock LLM, offline data, no pacing.

Environment is set *before* any app module reads settings.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="skopeo-tests-"))
os.environ.update(
    {
        # SKOPEO_TEST_DATABASE_URL runs the suite against another database, e.g. PostgreSQL
        # (its public schema is wiped first, so point it at a throwaway database).
        "DATABASE_URL": os.environ.get("SKOPEO_TEST_DATABASE_URL") or f"sqlite:///{(_TMP / 'test.db').as_posix()}",
        "SKOPEO_WORKSPACE_DIR": str(_TMP / "workspaces"),
        "SKOPEO_MODE": "mock",
        "LLM_PROVIDER": "mock",
        "SKOPEO_OFFLINE": "true",
        "SKOPEO_RUN_MIGRATIONS": "true",
        "SKOPEO_DEMO_STEP_DELAY_MS": "0",
        "SKOPEO_FAULT_INJECTION": "",
        "LOG_JSON": "false",
        "LOG_LEVEL": "WARNING",
        "DRY_RUN": "true",
        "GITHUB_TOKEN": "",
        "OPENAI_API_KEY": "",
    }
)

from app.config import get_settings, reset_settings_cache  # noqa: E402
from app.database import init_db, reset_engine  # noqa: E402

reset_settings_cache()
reset_engine()

BACKEND = Path(__file__).resolve().parents[1]
DEMO_REPO = BACKEND.parent / "examples" / "vulnerable-demo-repo"


@pytest.fixture(scope="session", autouse=True)
def _database():
    if os.environ.get("SKOPEO_TEST_DATABASE_URL"):
        from sqlalchemy import text

        from app.database import get_engine

        with get_engine().begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    init_db()
    yield
    reset_engine()
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def tmp_root() -> Path:
    return _TMP


@pytest.fixture()
def demo_repo_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DEMO_REPO, dest, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    return dest
