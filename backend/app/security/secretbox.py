"""Symmetric encryption for secrets Skopeo has to keep (users' GitHub tokens).

The key comes from ``SKOPEO_SECRET_KEY``; without it a random key is generated once and stored
next to the database (``secret.key``, mode 0600), so tokens survive restarts on the same volume.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings

_lock = threading.Lock()


def _key_file(settings: Settings) -> Path:
    url = settings.database_url
    if url.startswith("sqlite") and "///" in url and ":memory:" not in url:
        return Path(url.split("///", 1)[1]).parent / "secret.key"
    return settings.skopeo_workspace_dir.parent / "secret.key"


def _material(settings: Settings) -> bytes:
    if settings.skopeo_secret_key is not None and settings.skopeo_secret_key.get_secret_value().strip():
        return settings.skopeo_secret_key.get_secret_value().strip().encode()
    path = _key_file(settings)
    with _lock:
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(secrets.token_urlsafe(48))
        return path.read_text().strip().encode()


class SecretBox:
    def __init__(self, settings: Settings) -> None:
        digest = hashlib.sha256(b"skopeo-secretbox-v1:" + _material(settings)).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str | None:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except (InvalidToken, ValueError):
            return None
