"""Accounts (Google sign-in) and notification settings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.api.access import account_rate_limit
from app.api.auth import optional_user, require_user
from app.models import User
from app.notifications import NotificationError, NotificationService, channel_out, rule_out
from app.schemas.accounts import ChannelCreate, ChannelUpdate, ChannelVerify, RuleCreate, RuleUpdate

router = APIRouter(prefix="/api")


def _notifier(request: Request) -> NotificationService:
    return request.app.state.notifier


def user_out(user: User) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "email": user.email,
        "email_verified": user.email_verified,
        "display_name": user.display_name,
        "photo_url": user.photo_url,
        "provider": user.provider,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
    }


def _bad(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc).strip("'"))
    return HTTPException(status_code=422, detail=str(exc))


# --------------------------------------------------------------------------- auth
@router.get("/auth/config")
def auth_config(request: Request) -> dict[str, Any]:
    """Public sign-in configuration for the browser (the Firebase web config is not secret)."""
    s = request.app.state.settings
    firebase = None
    if s.auth_mode == "firebase":
        firebase = {
            "apiKey": s.firebase_web_api_key,
            "authDomain": s.firebase_auth_domain or f"{s.firebase_project_id}.firebaseapp.com",
            "projectId": s.firebase_project_id,
            "appId": s.firebase_app_id or None,
            "sdkVersion": s.firebase_sdk_version,
        }
    return {
        "mode": s.auth_mode,
        "firebase": firebase,
        "require_login": s.auth_mode == "firebase" and s.auth_require_login,
        "email_configured": s.email_configured,
        "public_base_url": s.public_base_url or None,
        "providers": ["google", "github"] if s.auth_github_enabled else ["google"],
        "github": {"enabled": s.auth_github_enabled, "private_repos": s.github_private_repos},
    }


@router.get("/auth/me")
def me(user: User = Depends(require_user)) -> dict[str, Any]:
    return user_out(user)


@router.delete("/auth/me", status_code=204)
def delete_me(request: Request, user: User = Depends(require_user)) -> Response:
    """Delete the account and everything it owns (channels, rules, projects, watches, reports)."""
    if user.provider == "local":
        raise HTTPException(status_code=409, detail="the built-in local user cannot be deleted")
    request.app.state.accounts.delete_user(user.id)
    return Response(status_code=204)


@router.get("/auth/whoami")
def whoami(user: User | None = Depends(optional_user)) -> dict[str, Any]:
    return {"signed_in": user is not None, "user": user_out(user) if user else None}


# ------------------------------------------------------------------ notifications
@router.get("/notifications/catalog")
def catalog(request: Request) -> dict[str, Any]:
    return _notifier(request).catalog()


@router.get("/notifications/channels")
def list_channels(request: Request, user: User = Depends(require_user)) -> list[dict[str, Any]]:
    notifier = _notifier(request)
    subs = notifier.subscriptions(user.id)
    return [channel_out(c) | {"events": subs.get(c.id, [])} for c in notifier.store.list_channels(user.id)]


@router.post("/notifications/channels", status_code=201, dependencies=[Depends(account_rate_limit)])
def create_channel(body: ChannelCreate, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    notifier = _notifier(request)
    try:
        result = notifier.create_channel(user, body.kind, body.name, body.target, body.events)
    except NotificationError as exc:
        raise _bad(exc) from exc
    result["channel"]["events"] = notifier.subscriptions(user.id).get(result["channel"]["channel_id"], [])
    return result


@router.patch("/notifications/channels/{channel_id}")
def update_channel(channel_id: str, body: ChannelUpdate, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    notifier = _notifier(request)
    try:
        out = notifier.update_channel(user, channel_id, name=body.name, enabled=body.enabled)
        if body.events is not None:
            notifier.set_subscriptions(user, channel_id, body.events)
    except (NotificationError, LookupError) as exc:
        raise _bad(exc) from exc
    return out | {"events": notifier.subscriptions(user.id).get(channel_id, [])}


@router.delete("/notifications/channels/{channel_id}", status_code=204)
def delete_channel(channel_id: str, request: Request, user: User = Depends(require_user)) -> Response:
    if not _notifier(request).store.delete_channel(user.id, channel_id):
        raise HTTPException(status_code=404, detail="channel not found")
    return Response(status_code=204)


@router.post("/notifications/channels/{channel_id}/verify")
def verify_channel(channel_id: str, body: ChannelVerify, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    try:
        return _notifier(request).verify_channel(user, channel_id, body.code)
    except (NotificationError, LookupError) as exc:
        raise _bad(exc) from exc


@router.post("/notifications/channels/{channel_id}/resend", dependencies=[Depends(account_rate_limit)])
def resend_code(channel_id: str, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    try:
        return _notifier(request).resend_code(user, channel_id)
    except (NotificationError, LookupError) as exc:
        raise _bad(exc) from exc


@router.post("/notifications/channels/{channel_id}/test", dependencies=[Depends(account_rate_limit)])
def test_channel(channel_id: str, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    try:
        return _notifier(request).test_channel(user, channel_id)
    except (NotificationError, LookupError) as exc:
        raise _bad(exc) from exc


@router.post("/notifications/channels/{channel_id}/rotate-secret")
def rotate_secret(channel_id: str, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    try:
        return _notifier(request).rotate_secret(user, channel_id)
    except (NotificationError, LookupError) as exc:
        raise _bad(exc) from exc


@router.get("/notifications/rules")
def list_rules(request: Request, user: User = Depends(require_user)) -> list[dict[str, Any]]:
    return [rule_out(r) for r in _notifier(request).store.list_rules(user.id)]


@router.post("/notifications/rules", status_code=201)
def create_rule(body: RuleCreate, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    notifier = _notifier(request)
    try:
        channel_ids, filters = notifier.validate_rule(user, body.event, body.channel_ids, body.filters)
    except NotificationError as exc:
        raise _bad(exc) from exc
    if len(notifier.store.list_rules(user.id)) >= 100:
        raise HTTPException(status_code=422, detail="you can have at most 100 rules")
    return rule_out(notifier.store.add_rule(user.id, event=body.event, channel_ids=channel_ids, filters=filters, enabled=body.enabled))


@router.patch("/notifications/rules/{rule_id}")
def update_rule(rule_id: str, body: RuleUpdate, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    notifier = _notifier(request)
    rule = notifier.store.get_rule(user.id, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    try:
        channel_ids, filters = notifier.validate_rule(
            user,
            rule.event,
            body.channel_ids if body.channel_ids is not None else list(rule.channel_ids or []),
            body.filters if body.filters is not None else dict(rule.filters or {}),
        )
    except NotificationError as exc:
        raise _bad(exc) from exc
    fields: dict[str, Any] = {"channel_ids": channel_ids, "filters": filters}
    if body.enabled is not None:
        fields["enabled"] = body.enabled
    return rule_out(notifier.store.update_rule(rule.id, **fields))


@router.delete("/notifications/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: str, request: Request, user: User = Depends(require_user)) -> Response:
    if not _notifier(request).store.delete_rule(user.id, rule_id):
        raise HTTPException(status_code=404, detail="rule not found")
    return Response(status_code=204)


@router.get("/notifications/deliveries")
def deliveries(request: Request, user: User = Depends(require_user), limit: int = Query(50, ge=1, le=200)) -> list[dict[str, Any]]:
    return [
        {
            "delivery_id": d.id,
            "channel_id": d.channel_id,
            "rule_id": d.rule_id,
            "event": d.event,
            "subject": d.subject,
            "status": d.status,
            "error": d.error,
            "created_at": d.created_at,
        }
        for d in _notifier(request).store.list_deliveries(user.id, limit)
    ]
