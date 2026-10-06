"""Shared, deterministic domain helpers used by several agents."""

from __future__ import annotations

import re

from app.tools.repository import is_fixture_path, is_test_path

_COMPONENT_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("authentication", re.compile(r"(^|/)(auth|authn|login|session|jwt|oauth|sso|token|passwords?|credentials?|security)([/_.]|$)", re.I)),
    ("authorization", re.compile(r"(^|/)(authz|permissions?|acl|rbac|policy)([/_.]|$)", re.I)),
    ("cryptography", re.compile(r"(^|/)(crypto|cipher|encrypt|hashing|keys?)([/_.]|$)", re.I)),
    ("payments", re.compile(r"(^|/)(payments?|billing|checkout|stripe)([/_.]|$)", re.I)),
    ("api", re.compile(r"(^|/)(api|routes?|views?|handlers?|controllers?|endpoints?)([/_.]|$)", re.I)),
    ("data-access", re.compile(r"(^|/)(db|database|models?|repositor(y|ies)|dao|orm|queries)([/_.]|$)", re.I)),
    ("vendored", re.compile(r"(^|/)(vendor|third_party|thirdparty|external)(/|$)", re.I)),
    ("configuration", re.compile(r"(^|/)(config|settings|conf)([/_.]|$)", re.I)),
]

# PyPI distribution name -> import name, where they differ.
IMPORT_NAMES = {
    "pyjwt": "jwt",
    "python-dateutil": "dateutil",
    "pyyaml": "yaml",
    "beautifulsoup4": "bs4",
    "pillow": "PIL",
    "scikit-learn": "sklearn",
    "opencv-python": "cv2",
    "python-jose": "jose",
    "pycryptodome": "Crypto",
    "protobuf": "google",
    "python-dotenv": "dotenv",
    "psycopg2-binary": "psycopg2",
    "attrs": "attr",
}

# Packages whose upgrade can plausibly change performance-sensitive behaviour.
PERFORMANCE_SENSITIVE_PACKAGES = {
    "sqlalchemy",
    "django",
    "psycopg2",
    "psycopg2-binary",
    "pymongo",
    "redis",
    "requests",
    "httpx",
    "aiohttp",
    "pandas",
    "numpy",
    "celery",
    "uvicorn",
    "gunicorn",
    "orjson",
    "ujson",
}

SECURITY_SENSITIVE_PACKAGES = {
    "pyjwt",
    "python-jose",
    "cryptography",
    "pycryptodome",
    "passlib",
    "bcrypt",
    "authlib",
    "oauthlib",
    "requests-oauthlib",
    "itsdangerous",
    "flask-login",
    "django-allauth",
    "jsonwebtoken",
    "jose",
    "paramiko",
}


def import_name_for(package: str, ecosystem: str = "PyPI") -> str:
    if ecosystem != "PyPI":
        return package
    return IMPORT_NAMES.get(package.lower(), package.lower().replace("-", "_"))


def components_for(path: str) -> list[str]:
    comps: list[str] = []
    if is_test_path(path):
        comps.append("tests")
    if is_fixture_path(path) and "tests" not in comps:
        comps.append("fixtures")
    for name, pattern in _COMPONENT_RULES:
        if pattern.search(path) and name not in comps:
            comps.append(name)
    if not comps:
        parts = path.split("/")
        comps.append(parts[-2] if len(parts) > 1 else "root")
    return comps


def module_label(path: str) -> str:
    return path[:-3].replace("/", ".") if path.endswith(".py") else path


def excerpt(lines: list[str], start: int, end: int | None = None, max_chars: int = 600) -> str:
    end = end or start
    chunk = "\n".join(lines[max(0, start - 1) : end])
    return chunk[:max_chars]
