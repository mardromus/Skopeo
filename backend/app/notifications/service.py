"""Notification channels, rules and dispatch.

A **channel** is somewhere to send a message (an email address, a Slack or Discord webhook, or a
signed generic webhook). A **rule** says which event goes to which channels, with optional filters.
Every attempt is written to the delivery log, including skipped ones, so users can see why a
message did or did not arrive.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Any

from app.config import Settings
from app.models import NotificationChannel, NotificationRule, User, utcnow
from app.notifications.transports import DefaultTransport, DeliveryError, Message, Transport
from app.observability import get_logger
from app.security.redaction import mask_secret, redact
from app.security.webhook_validation import InvalidNotificationTarget, validate_email, validate_webhook_url
from app.services.account_store import AccountStore

log = get_logger("notifications")

CHANNEL_KINDS = {
    "email": "Email (sent over the server's SMTP account)",
    "slack": "Slack incoming webhook",
    "discord": "Discord webhook",
    "webhook": "Generic HTTPS webhook (JSON, HMAC-signed)",
}

EVENTS: dict[str, dict[str, Any]] = {
    "investigation.completed": {"label": "Case finished", "description": "An investigation you started finished.", "filters": []},
    "investigation.failed": {
        "label": "Case failed",
        "description": "An investigation you started failed or was interrupted.",
        "filters": [],
    },
    "investigation.risk": {
        "label": "High-priority risk found",
        "description": "A finished investigation has a verified risk at or above the chosen priority.",
        "filters": ["min_priority"],
    },
    "watch.impact": {
        "label": "Upstream change affects my project",
        "description": "A watched upstream repository changed in a way that touches code in your project.",
        "filters": ["min_impact", "project_id", "watch_id"],
    },
    "watch.update": {
        "label": "Any upstream update",
        "description": "A watched upstream repository has new commits (digest, even when your code is not affected).",
        "filters": ["project_id", "watch_id"],
    },
    "watch.failed": {
        "label": "Watch check failed",
        "description": "Skopeo could not check a watched repository.",
        "filters": ["project_id", "watch_id"],
    },
}
DEFAULT_SUBSCRIPTIONS = ["investigation.completed", "investigation.failed", "watch.impact", "watch.failed"]

PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}
IMPACT_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "breaking": 4}

CODE_TTL = timedelta(minutes=30)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_CODE_ATTEMPTS = 5


class NotificationError(ValueError):
    """A user-facing problem (bad input, wrong code, not allowed)."""


def _code_hash(channel_id: str, code: str) -> str:
    return hashlib.sha256(f"{channel_id}:{code}".encode()).hexdigest()


def mask_target(channel: NotificationChannel) -> str:
    if channel.kind == "email":
        return channel.target
    # webhook URLs embed their own secret token: show the host and the last few characters only
    host = channel.target.split("/")[2] if channel.target.count("/") >= 2 else "webhook"
    return f"https://{host}/…{channel.target[-4:]}"


def channel_out(channel: NotificationChannel) -> dict[str, Any]:
    return {
        "channel_id": channel.id,
        "kind": channel.kind,
        "name": channel.name,
        "target": mask_target(channel),
        "verified": channel.verified,
        "enabled": channel.enabled,
        "has_signing_secret": bool(channel.signing_secret),
        "signing_secret_hint": mask_secret(channel.signing_secret) if channel.signing_secret else None,
        "last_used_at": channel.last_used_at,
        "last_error": channel.last_error,
        "created_at": channel.created_at,
    }


def rule_out(rule: NotificationRule) -> dict[str, Any]:
    return {
        "rule_id": rule.id,
        "event": rule.event,
        "channel_ids": list(rule.channel_ids or []),
        "filters": dict(rule.filters or {}),
        "enabled": rule.enabled,
        "created_at": rule.created_at,
    }


class NotificationService:
    def __init__(self, settings: Settings, store: AccountStore | None = None, transport: Transport | None = None) -> None:
        self.settings = settings
        self.store = store or AccountStore()
        self.transport: Transport = transport or DefaultTransport(settings)

    # ------------------------------------------------------------------ helpers
    def link(self, path: str) -> str | None:
        base = self.settings.public_base_url.strip().rstrip("/")
        return f"{base}{path}" if base else None

    def catalog(self) -> dict[str, Any]:
        return {
            "events": [{"event": k, **v} for k, v in EVENTS.items()],
            "channel_kinds": [{"kind": k, "label": v} for k, v in CHANNEL_KINDS.items()],
            "email_configured": self.settings.email_configured,
            "dry_run": self.settings.notifications_dry_run,
            "default_subscriptions": DEFAULT_SUBSCRIPTIONS,
            "priorities": list(PRIORITY_RANK),
            "impact_levels": [k for k in IMPACT_RANK if k != "none"],
        }

    # ----------------------------------------------------------------- channels
    def create_channel(self, user: User, kind: str, name: str, target: str, events: list[str] | None = None) -> dict[str, Any]:
        if kind not in CHANNEL_KINDS:
            raise NotificationError(f"unknown channel kind: {kind}")
        name = (name or "").strip()[:120] or CHANNEL_KINDS[kind].split(" (")[0]
        if len(self.store.list_channels(user.id)) >= 25:
            raise NotificationError("you can have at most 25 channels")
        try:
            if kind == "email":
                target = validate_email(target)
            else:
                target = validate_webhook_url(kind, target, allow_private=self.settings.notifications_allow_private_webhooks)
        except InvalidNotificationTarget as exc:
            raise NotificationError(str(exc)) from exc

        secret = f"whsec_{secrets.token_urlsafe(32)}" if kind == "webhook" else None
        # Your own Google address is already verified by Google; webhooks are verified by possession of the URL.
        own_email = kind == "email" and user.email_verified and (user.email or "").lower() == target.lower()
        verified = kind != "email" or own_email
        channel = self.store.add_channel(user.id, kind=kind, name=name, target=target, signing_secret=secret, verified=verified)
        result: dict[str, Any] = {"channel": channel_out(channel), "signing_secret": secret, "verification_sent": False}
        if not verified:
            result |= self._send_code(user, channel)
        self.set_subscriptions(user, channel.id, events if events is not None else DEFAULT_SUBSCRIPTIONS)
        result["channel"] = channel_out(self.store.get_channel(user.id, channel.id))  # type: ignore[arg-type]
        return result

    def _send_code(self, user: User, channel: NotificationChannel) -> dict[str, Any]:
        code = f"{secrets.randbelow(1_000_000):06d}"
        self.store.update_channel(
            channel.id,
            verification_code_hash=_code_hash(channel.id, code),
            verification_expires_at=utcnow() + CODE_TTL,
            verification_attempts=0,
        )
        message = Message(
            event="channel.verification",
            subject=f"Your Skopeo verification code: {code}",
            text=(
                f"Enter {code} in Skopeo to confirm that notifications may be sent to this address. "
                "The code expires in 30 minutes. If you did not ask for this, ignore this email."
            ),
        )
        out: dict[str, Any] = {"verification_sent": False}
        if self.settings.notifications_dry_run:
            out |= {"verification_sent": True, "dev_verification_code": code}
            self.store.add_delivery(user.id, channel_id=channel.id, event=message.event, subject="Verification code", status="dry_run")
            return out
        try:
            self.transport.send("email", channel.target, message)
            out["verification_sent"] = True
            self.store.update_channel(channel.id, last_error=None)
            self.store.add_delivery(user.id, channel_id=channel.id, event=message.event, subject="Verification code", status="sent")
        except (DeliveryError, InvalidNotificationTarget) as exc:
            error = redact(str(exc))[:500]
            self.store.update_channel(channel.id, last_error=error)
            self.store.add_delivery(
                user.id, channel_id=channel.id, event=message.event, subject="Verification code", status="failed", error=error
            )
            out["verification_error"] = error
        return out

    def resend_code(self, user: User, channel_id: str) -> dict[str, Any]:
        channel = self._own_channel(user, channel_id)
        if channel.verified:
            raise NotificationError("this channel is already verified")
        if channel.verification_expires_at is not None:
            sent_at = channel.verification_expires_at - CODE_TTL
            if utcnow() - _aware(sent_at) < RESEND_COOLDOWN:
                raise NotificationError("wait a minute before requesting another code")
        return self._send_code(user, channel)

    def verify_channel(self, user: User, channel_id: str, code: str) -> dict[str, Any]:
        channel = self._own_channel(user, channel_id)
        if channel.verified:
            return channel_out(channel)
        if not channel.verification_code_hash or channel.verification_expires_at is None:
            raise NotificationError("no code was sent; request a new one")
        if channel.verification_attempts >= MAX_CODE_ATTEMPTS:
            raise NotificationError("too many wrong codes; request a new one")
        if utcnow() > _aware(channel.verification_expires_at):
            raise NotificationError("the code expired; request a new one")
        if not hmac.compare_digest(channel.verification_code_hash, _code_hash(channel.id, (code or "").strip())):
            self.store.update_channel(channel.id, verification_attempts=channel.verification_attempts + 1)
            raise NotificationError("that code is not right")
        updated = self.store.update_channel(
            channel.id, verified=True, verification_code_hash=None, verification_expires_at=None, verification_attempts=0, last_error=None
        )
        return channel_out(updated)

    def update_channel(self, user: User, channel_id: str, *, name: str | None = None, enabled: bool | None = None) -> dict[str, Any]:
        channel = self._own_channel(user, channel_id)
        fields: dict[str, Any] = {}
        if name is not None:
            fields["name"] = name.strip()[:120] or channel.name
        if enabled is not None:
            fields["enabled"] = enabled
        return channel_out(self.store.update_channel(channel.id, **fields) if fields else channel)

    def rotate_secret(self, user: User, channel_id: str) -> dict[str, Any]:
        channel = self._own_channel(user, channel_id)
        if channel.kind != "webhook":
            raise NotificationError("only generic webhooks have a signing secret")
        secret = f"whsec_{secrets.token_urlsafe(32)}"
        return {"channel": channel_out(self.store.update_channel(channel.id, signing_secret=secret)), "signing_secret": secret}

    def subscriptions(self, user_id: str) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for rule in self.store.list_rules(user_id):
            for cid in rule.channel_ids or []:
                out.setdefault(cid, [])
                if rule.event not in out[cid]:
                    out[cid].append(rule.event)
        return out

    def set_subscriptions(self, user: User, channel_id: str, events: list[str]) -> list[str]:
        """Make ``channel_id`` part of exactly the given events' rules (creating a default rule per event if needed)."""
        self._own_channel(user, channel_id)
        wanted = {e for e in events if e in EVENTS}
        rules = self.store.list_rules(user.id)
        for event in EVENTS:
            event_rules = [r for r in rules if r.event == event]
            if event in wanted:
                if not any(channel_id in (r.channel_ids or []) for r in event_rules):
                    if event_rules:
                        r = event_rules[0]
                        self.store.update_rule(r.id, channel_ids=[*(r.channel_ids or []), channel_id])
                    else:
                        defaults = (
                            {"min_priority": "P1"}
                            if event == "investigation.risk"
                            else {"min_impact": "medium"}
                            if event == "watch.impact"
                            else {}
                        )
                        self.store.add_rule(user.id, event=event, channel_ids=[channel_id], filters=defaults, enabled=True)
            else:
                for r in event_rules:
                    if channel_id in (r.channel_ids or []):
                        self.store.update_rule(r.id, channel_ids=[c for c in r.channel_ids if c != channel_id])
        return sorted(wanted)

    def _own_channel(self, user: User, channel_id: str) -> NotificationChannel:
        channel = self.store.get_channel(user.id, channel_id)
        if channel is None:
            raise LookupError("channel not found")
        return channel

    # -------------------------------------------------------------------- rules
    def validate_rule(self, user: User, event: str, channel_ids: list[str], filters: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        if event not in EVENTS:
            raise NotificationError(f"unknown event: {event}")
        own = {c.id for c in self.store.list_channels(user.id)}
        unknown = [c for c in channel_ids if c not in own]
        if unknown:
            raise NotificationError("unknown channel in rule")
        allowed = set(EVENTS[event]["filters"])
        clean: dict[str, Any] = {}
        for key, value in (filters or {}).items():
            if key not in allowed or value in (None, ""):
                continue
            if key == "min_priority" and value not in PRIORITY_RANK:
                raise NotificationError("min_priority must be P0-P4")
            if key == "min_impact" and value not in IMPACT_RANK:
                raise NotificationError("min_impact must be low, medium, high or breaking")
            if key == "project_id" and self.store.get_project(user.id, str(value)) is None:
                raise NotificationError("unknown project")
            if key == "watch_id" and self.store.get_watch(user.id, str(value)) is None:
                raise NotificationError("unknown watch")
            clean[key] = value
        return list(dict.fromkeys(channel_ids)), clean

    @staticmethod
    def rule_matches(rule: NotificationRule, context: dict[str, Any]) -> bool:
        f = rule.filters or {}
        if "min_priority" in f:
            top = context.get("top_priority")
            if top is None or PRIORITY_RANK.get(top, 9) > PRIORITY_RANK[f["min_priority"]]:
                return False
        if "min_impact" in f and IMPACT_RANK.get(context.get("impact_level", "none"), 0) < IMPACT_RANK[f["min_impact"]]:
            return False
        return all(not f.get(key) or f[key] == context.get(key) for key in ("project_id", "watch_id"))

    # ----------------------------------------------------------------- dispatch
    def test_channel(self, user: User, channel_id: str) -> dict[str, Any]:
        channel = self._own_channel(user, channel_id)
        if not channel.verified:
            raise NotificationError("verify this channel first")
        message = Message(
            event="channel.test",
            subject="Skopeo test notification",
            text=f"This is a test from Skopeo. If you can read it, the channel “{channel.name}” works.",
            severity="success",
            url=self.link("/settings/notifications"),
            fields=[("Channel", channel.name), ("Type", channel.kind)],
        )
        return self._deliver(user.id, channel, message, rule_id=None)

    def dispatch(self, user_id: str, event: str, message: Message, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Send ``message`` to every enabled, verified channel whose rule for ``event`` matches ``context``."""
        context = context or {}
        sent_to: set[str] = set()
        results: list[dict[str, Any]] = []
        channels = {c.id: c for c in self.store.list_channels(user_id)}
        for rule in self.store.list_rules(user_id, event):
            if not rule.enabled or not self.rule_matches(rule, context):
                continue
            for cid in rule.channel_ids or []:
                channel = channels.get(cid)
                if channel is None or cid in sent_to:
                    continue
                sent_to.add(cid)
                if not channel.enabled or not channel.verified:
                    reason = "channel disabled" if not channel.enabled else "channel not verified"
                    self.store.add_delivery(
                        user_id, channel_id=cid, rule_id=rule.id, event=event, subject=message.subject, status="skipped", error=reason
                    )
                    results.append({"channel_id": cid, "status": "skipped", "error": reason})
                    continue
                results.append(self._deliver(user_id, channel, message, rule_id=rule.id))
        return results

    def _deliver(self, user_id: str, channel: NotificationChannel, message: Message, rule_id: str | None) -> dict[str, Any]:
        common = {"channel_id": channel.id, "rule_id": rule_id, "event": message.event, "subject": message.subject[:500]}
        if self.settings.notifications_dry_run:
            d = self.store.add_delivery(user_id, status="dry_run", detail={"kind": channel.kind}, **common)
            return {"delivery_id": d.id, "channel_id": channel.id, "status": "dry_run"}
        try:
            detail = self.transport.send(channel.kind, channel.target, message, signing_secret=channel.signing_secret)
        except (DeliveryError, InvalidNotificationTarget, OSError) as exc:
            error = redact(str(exc))[:500]
            self.store.update_channel(channel.id, last_error=error)
            d = self.store.add_delivery(user_id, status="failed", error=error, detail={"kind": channel.kind}, **common)
            log.warning(
                "notification failed", extra={"event_type": "notification_failed", "data": {"kind": channel.kind, "error": error[:200]}}
            )
            return {"delivery_id": d.id, "channel_id": channel.id, "status": "failed", "error": error}
        self.store.update_channel(channel.id, last_used_at=utcnow(), last_error=None)
        d = self.store.add_delivery(user_id, status="sent", detail={"kind": channel.kind, **(detail or {})}, **common)
        return {"delivery_id": d.id, "channel_id": channel.id, "status": "sent"}

    def safe_dispatch(self, user_id: str, event: str, message: Message, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """dispatch() for background callers: never raises."""
        try:
            return self.dispatch(user_id, event, message, context)
        except Exception as exc:  # noqa: BLE001 - notifications must never break an investigation or a watch
            log.exception("notification dispatch crashed", extra={"event_type": "notification_crash", "data": {"event": event}})
            return [{"status": "failed", "error": f"{type(exc).__name__}"}]


def _aware(value):
    """SQLite returns naive datetimes; treat them as UTC."""
    from datetime import UTC

    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
