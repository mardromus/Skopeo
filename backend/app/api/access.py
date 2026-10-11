"""Access control for a publicly reachable deployment.

* ``SKOPEO_API_KEY`` — when set, every endpoint that starts, cancels or approves work requires it
  (``X-Skopeo-Key: <key>`` or ``Authorization: Bearer <key>``). Read endpoints stay open.
* ``SKOPEO_DEMO_PUBLIC`` — keeps the bundled reference case open to everyone even with a key set;
  it runs offline against a fixture, so it cannot be used to make the server fetch anything.
* ``RATE_LIMIT_PER_MINUTE`` — sliding-window limit on starting investigations, per client address.
"""

from __future__ import annotations

import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request


class RateLimiter:
    def __init__(self, per_minute: int, window_seconds: float = 60.0) -> None:
        self.per_minute = per_minute
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, client: str) -> float | None:
        """Record a hit; return seconds to wait if the client is over the limit, else None."""
        if self.per_minute <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            hits = self._hits[client]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return max(0.0, self.window - (now - hits[0]))
            hits.append(now)
            if len(self._hits) > 10_000:  # bound memory under address churn
                for key in [k for k, v in self._hits.items() if not v][:5_000]:
                    del self._hits[key]
            return None


def client_address(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _provided_key(x_skopeo_key: str | None, authorization: str | None) -> str | None:
    if x_skopeo_key:
        return x_skopeo_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def require_write_access(
    request: Request,
    x_skopeo_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    settings = request.app.state.settings
    expected = settings.skopeo_api_key
    if expected is None or not expected.get_secret_value():
        return
    provided = _provided_key(x_skopeo_key, authorization)
    if provided and hmac.compare_digest(provided.encode(), expected.get_secret_value().encode()):
        return
    # With Google sign-in enabled, a signed-in user may act without the shared key.
    if settings.auth_mode == "firebase" and settings.auth_signed_in_users_can_scan:
        from app.api.auth import bearer_token, looks_like_jwt

        if looks_like_jwt(bearer_token(authorization)) and request.app.state.user_resolver.resolve(authorization) is not None:
            return
    raise HTTPException(
        status_code=401,
        detail="This server requires an access key (X-Skopeo-Key) or a Google sign-in to start or change investigations.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_login_for_scans(request: Request, authorization: str | None = Header(default=None)) -> None:
    """AUTH_REQUIRE_LOGIN: with Google sign-in enabled, scanning repositories needs an account."""
    settings = request.app.state.settings
    if settings.auth_mode != "firebase" or not settings.auth_require_login:
        return
    if request.app.state.user_resolver.resolve(authorization) is None:
        raise HTTPException(status_code=401, detail="Sign in with Google to start investigations.", headers={"WWW-Authenticate": "Bearer"})


def require_demo_access(
    request: Request,
    x_skopeo_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    if request.app.state.settings.skopeo_demo_public:
        return
    require_write_access(request, x_skopeo_key, authorization)


def rate_limit(request: Request) -> None:
    retry = request.app.state.rate_limiter.check(client_address(request))
    if retry is not None:
        wait = int(retry) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Too many investigations started from this address. Try again in {wait} s.",
            headers={"Retry-After": str(wait)},
        )


def account_rate_limit(request: Request) -> None:
    """Looser limit for account actions (send a test, resend a code, check a watch now)."""
    retry = request.app.state.account_rate_limiter.check(client_address(request))
    if retry is not None:
        wait = int(retry) + 1
        raise HTTPException(status_code=429, detail=f"Too many requests. Try again in {wait} s.", headers={"Retry-After": str(wait)})
