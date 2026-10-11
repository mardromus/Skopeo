"""Mint Firebase-shaped ID tokens signed by a throwaway key, for tests."""

from __future__ import annotations

import datetime as dt
import time
from typing import Any

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

PROJECT_ID = "skopeo-test"


class FakeFirebase:
    def __init__(self, project_id: str = PROJECT_ID) -> None:
        self.project_id = project_id
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "securetoken.system.gserviceaccount.com")])
        now = dt.datetime.now(dt.UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(self.key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=1))
            .sign(self.key, hashes.SHA256())
        )
        self.kid = "test-kid-1"
        self.certs = {self.kid: cert.public_bytes(serialization.Encoding.PEM).decode()}
        self.fetches = 0

    def fetch(self) -> tuple[dict[str, str], float]:
        self.fetches += 1
        return dict(self.certs), 3600.0

    def token(self, uid: str = "uid-alice", email: str = "alice@example.com", *, kid: str | None = None, key=None, **overrides: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": f"https://securetoken.google.com/{self.project_id}",
            "aud": self.project_id,
            "auth_time": now - 10,
            "user_id": uid,
            "sub": uid,
            "iat": now - 10,
            "exp": now + 3600,
            "email": email,
            "email_verified": True,
            "name": uid.removeprefix("uid-").title(),
            "picture": "https://lh3.googleusercontent.com/a/photo",
            "firebase": {"identities": {"google.com": ["123"]}, "sign_in_provider": "google.com"},
        }
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, key or self.key, algorithm="RS256", headers={"kid": kid or self.kid})
