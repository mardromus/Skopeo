"""Secret redaction applied to logs, tool output, LLM prompts and API responses.

Two layers:
1. Pattern-based redaction of well-known credential formats.
2. Exact-value redaction of secrets Skopeo itself holds (API keys / tokens from settings).
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterable

REDACTED = "[REDACTED]"

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,255}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,255}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}\b")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("bearer", re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-~+/]{16,}=*")),
    ("basic_auth_url", re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@")),
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    ),
    (
        "assignment",
        re.compile(
            r"(?i)\b((?:api[_-]?key|secret|token|password|passwd|authorization)[\"']?\s*[:=]\s*[\"']?)"
            r"([A-Za-z0-9/+_\-]{12,})"
        ),
    ),
]

_known_secrets: set[str] = set()
_lock = threading.Lock()


def register_secrets(values: Iterable[str]) -> None:
    """Register concrete secret values (e.g. tokens from env) for exact-match redaction."""
    with _lock:
        for value in values:
            if value and len(value) >= 6:
                _known_secrets.add(value)


def redact(text: str | None) -> str:
    if not text:
        return text or ""
    out = text
    with _lock:
        known = sorted(_known_secrets, key=len, reverse=True)
    for value in known:
        if value in out:
            out = out.replace(value, REDACTED)
    for name, pattern in _PATTERNS:
        if name in ("bearer", "basic_auth_url"):
            suffix = "@" if name == "basic_auth_url" else ""
            out = pattern.sub(lambda m, suffix=suffix: m.group(1) + REDACTED + suffix, out)
        elif name == "assignment":
            out = pattern.sub(lambda m: m.group(1) + REDACTED, out)
        else:
            out = pattern.sub(REDACTED, out)
    return out


def redact_obj(value: object) -> object:
    """Recursively redact strings inside dict/list payloads."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_obj(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_obj(v) for v in value]
    return value


def mask_secret(value: str, keep: int = 4) -> str:
    """Show a secret's shape without revealing it (used in findings about detected secrets)."""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return value[:keep] + "*" * (len(value) - keep * 2) + value[-keep:]
