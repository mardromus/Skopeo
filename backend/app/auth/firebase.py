"""Verification of Firebase Authentication ID tokens (Google sign-in) without the Admin SDK.

A Firebase ID token is an RS256 JWT signed by one of Google's rotating keys. A token is accepted
only when every check Firebase documents passes:

* header ``alg`` is RS256 and ``kid`` names a current Google signing certificate;
* signature verifies against that certificate;
* ``aud`` is the Firebase project id and ``iss`` is ``https://securetoken.google.com/<project id>``;
* ``exp`` is in the future, ``iat`` and ``auth_time`` are not in the future (60 s leeway);
* ``sub`` (the Firebase uid) is a non-empty string of at most 128 characters.

Certificates are cached for the ``max-age`` Google sends and refreshed when an unknown ``kid`` shows up.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx
import jwt
from cryptography.x509 import load_pem_x509_certificate

GOOGLE_CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
LEEWAY_SECONDS = 60
_MAX_AGE_RE = re.compile(r"max-age=(\d+)")

CertFetcher = Callable[[], tuple[dict[str, str], float]]
"""Returns ({kid: PEM certificate}, seconds the certificates may be cached)."""


class InvalidIdToken(ValueError):
    pass


def fetch_google_certs(timeout: float = 10.0) -> tuple[dict[str, str], float]:
    resp = httpx.get(GOOGLE_CERTS_URL, timeout=timeout, follow_redirects=False)
    resp.raise_for_status()
    certs = resp.json()
    if not isinstance(certs, dict) or not certs:
        raise InvalidIdToken("Google returned no signing certificates")
    match = _MAX_AGE_RE.search(resp.headers.get("cache-control", ""))
    return {str(k): str(v) for k, v in certs.items()}, float(match.group(1)) if match else 3600.0


class FirebaseTokenVerifier:
    def __init__(self, project_id: str, fetch_certs: CertFetcher | None = None, clock: Callable[[], float] = time.time) -> None:
        if not project_id:
            raise ValueError("Firebase project id is required")
        self.project_id = project_id
        self._fetch = fetch_certs or fetch_google_certs
        self._clock = clock
        self._certs: dict[str, str] = {}
        self._expires = 0.0
        self._lock = threading.Lock()

    def _certificate(self, kid: str) -> str:
        with self._lock:
            now = self._clock()
            if kid not in self._certs or now >= self._expires:
                try:
                    certs, max_age = self._fetch()
                except (httpx.HTTPError, ValueError) as exc:
                    if kid in self._certs:  # keep serving cached keys if Google is briefly unreachable
                        return self._certs[kid]
                    raise InvalidIdToken(f"could not load Google signing certificates: {type(exc).__name__}") from exc
                self._certs, self._expires = certs, now + max(60.0, max_age)
            if kid not in self._certs:
                raise InvalidIdToken("token signed with an unknown key")
            return self._certs[kid]

    def verify(self, token: str) -> dict[str, Any]:
        if not isinstance(token, str) or token.count(".") != 2 or len(token) > 8192:
            raise InvalidIdToken("malformed token")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise InvalidIdToken("malformed token header") from exc
        if header.get("alg") != "RS256":
            raise InvalidIdToken("unexpected signing algorithm")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise InvalidIdToken("token has no key id")
        public_key = load_pem_x509_certificate(self._certificate(kid).encode()).public_key()
        try:
            claims = jwt.decode(
                token,
                public_key,  # type: ignore[arg-type]
                algorithms=["RS256"],
                audience=self.project_id,
                issuer=f"https://securetoken.google.com/{self.project_id}",
                leeway=LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "aud", "iss", "sub"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise InvalidIdToken("token expired") from exc
        except jwt.PyJWTError as exc:
            raise InvalidIdToken(f"token rejected: {type(exc).__name__}") from exc
        now = self._clock()
        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub or len(sub) > 128:
            raise InvalidIdToken("token has an invalid subject")
        if float(claims.get("iat", 0)) > now + LEEWAY_SECONDS:
            raise InvalidIdToken("token issued in the future")
        auth_time = claims.get("auth_time")
        if auth_time is None or float(auth_time) > now + LEEWAY_SECONDS:
            raise InvalidIdToken("token has an invalid auth_time")
        return claims
