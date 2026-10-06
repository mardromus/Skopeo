"""Bearer-token authentication for Shopfront request handlers."""

import os

import jwt

SECRET_KEY = os.environ.get("SHOPFRONT_SECRET", "dev-insecure-secret-key")
TOKEN_TTL_SECONDS = 3600


class AuthError(Exception):
    """Raised when a request cannot be authenticated."""


def issue_token(user_id: str) -> str:
    token = jwt.encode({"sub": user_id}, SECRET_KEY, algorithm="HS256")
    return token.decode("utf-8")


def authenticate(headers: dict) -> dict:
    header = headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise AuthError("missing bearer token")
    token = header[len("Bearer ") :]
    try:
        return jwt.decode(token, SECRET_KEY)
    except jwt.InvalidTokenError as exc:
        raise AuthError(str(exc)) from exc


def require_auth(handler):
    """Decorator: authenticate the request before calling ``handler``."""

    def wrapper(request: dict):
        request["user"] = authenticate(request.get("headers", {}))
        return handler(request)

    wrapper.__name__ = handler.__name__
    return wrapper
