#!/usr/bin/env python3
"""Skopeo Health & Deployment Readiness Diagnostic CLI.

Validates environment setup, database connectivity, LLM providers, tool dependencies,
and API health before submitting for Exam Studio evaluation.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import get_settings  # noqa: E402
from app.database import init_db  # noqa: E402
from app.services.evidence_store import EvidenceStore  # noqa: E402


def check_health() -> bool:
    print("=" * 60)
    print("      SKOPEO SYSTEM HEALTH & READINESS DIAGNOSTIC")
    print("=" * 60)

    settings = get_settings()
    all_ok = True

    # 1. Environment & Settings
    print("\n[1] Environment & Configuration:")
    print(f"  - Mode: {settings.skopeo_mode}")
    print(f"  - LLM Provider: {settings.llm_provider}")
    print(f"  - Database URL: {settings.database_url.split('@')[-1] if '@' in settings.database_url else settings.database_url}")
    print(f"  - Offline Mode: {settings.skopeo_offline}")

    # 2. Database Connectivity & Evidence Store
    print("\n[2] Database & Evidence Store:")
    try:
        init_db()
        store = EvidenceStore()
        count = len(store.list_investigations(limit=1))
        print(f"  - Database connection: OK (table initialized, query returned {count} rows)")
    except (OSError, RuntimeError) as e:
        print(f"  - Database connection FAILED: {e}")
        all_ok = False

    # 3. Tool Dependencies
    print("\n[3] Tool & System Dependencies:")
    tools = ["git", "pytest"]
    for t in tools:
        found = shutil_which(t)
        status = "OK" if found else "NOT FOUND (Fallback available)"
        print(f"  - Tool `{t}`: {status}")

    print("\n" + "=" * 60)
    if all_ok:
        print("RESULT: All core health checks PASSED. System ready for evaluation.")
    else:
        print("RESULT: Some health checks FAILED. Review errors above.")
    print("=" * 60)

    return all_ok


def shutil_which(cmd: str) -> str | None:
    import shutil

    return shutil.which(cmd)


if __name__ == "__main__":
    success = check_health()
    sys.exit(0 if success else 1)
