"""Who is calling: resolve the signed-in user for a request.

* ``local`` mode (no ``FIREBASE_PROJECT_ID``): there are no accounts; every request acts as one
  built-in local user, so projects, watches and notifications work on a laptop with no setup.
* ``firebase`` mode: the browser signs in with Google through Firebase Authentication and sends
  the Firebase ID token as ``Authorization: Bearer <token>``. The token is verified on every
  request (signature, audience, issuer, expiry); the user row is created on first sign-in.

A bearer value that is not a JWT is left alone, so ``Authorization: Bearer <SKOPEO_API_KEY>``
keeps working for scripts.
"""

from __future__ import annotations

import threading
import time

from fastapi import Depends, Header, HTTPException, Request

from app.auth import FirebaseTokenVerifier, InvalidIdToken
from app.config import Settings
from app.models import User
from app.services.account_store import AccountStore

_CACHE_SECONDS = 300.0


def bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        value = authorization[7:].strip()
        return value or None
    return None


def looks_like_jwt(value: str | None) -> bool:
    return bool(value) and value.count(".") == 2 and len(value) > 40  # type: ignore[union-attr]


class UserResolver:
    def __init__(self, settings: Settings, store: AccountStore, verifier: FirebaseTokenVerifier | None = None) -> None:
        self.settings = settings
        self.store = store
        self.verifier = verifier
        if verifier is None and settings.auth_mode == "firebase":
            self.verifier = FirebaseTokenVerifier(settings.firebase_project_id.strip())
        self._recent: dict[str, tuple[str, float]] = {}  # firebase uid -> (user id, refreshed at)
        self._lock = threading.Lock()

    def resolve(self, authorization: str | None) -> User | None:
        if self.settings.auth_mode == "local":
            return self.store.get_or_create_local_user()
        token = bearer_token(authorization)
        if not looks_like_jwt(token):
            return None
        assert self.verifier is not None
        try:
            claims = self.verifier.verify(token)  # type: ignore[arg-type]
        except InvalidIdToken as exc:
            raise HTTPException(
                status_code=401,
                detail=f"Your sign-in is invalid or expired ({exc}). Sign in again.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        uid = str(claims["sub"])
        now = time.monotonic()
        with self._lock:
            cached = self._recent.get(uid)
        if cached and now - cached[1] < _CACHE_SECONDS:
            user = self.store.get_user(cached[0])
            if user is not None:
                return user
        user = self.store.upsert_firebase_user(claims)  # first sign-in, or profile refresh every few minutes
        with self._lock:
            self._recent[uid] = (user.id, now)
            if len(self._recent) > 5000:
                self._recent.clear()
        return user


def optional_user(request: Request, authorization: str | None = Header(default=None)) -> User | None:
    return request.app.state.user_resolver.resolve(authorization)


def require_user(request: Request, user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to use this feature.", headers={"WWW-Authenticate": "Bearer"})
    return user
