"""Delivery of a notification over email (SMTP), Slack, Discord or a signed generic webhook."""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import smtplib
import ssl
import time
import uuid
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from typing import Any, Protocol

import httpx

from app.config import Settings
from app.security.redaction import redact
from app.security.webhook_validation import assert_public_destination

SEVERITY_COLOURS = {"critical": 0xB3261E, "warning": 0xC2531A, "success": 0x1C7533, "info": 0x0C6870}
SEVERITY_EMOJI = {"critical": ":rotating_light:", "warning": ":warning:", "success": ":white_check_mark:", "info": ":mag:"}


@dataclass
class Message:
    event: str
    subject: str
    text: str
    severity: str = "info"  # info | success | warning | critical
    url: str | None = None
    fields: list[tuple[str, str]] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


class DeliveryError(RuntimeError):
    pass


class Transport(Protocol):
    def send(self, kind: str, target: str, message: Message, *, signing_secret: str | None = None) -> dict[str, Any]: ...


# ---------------------------------------------------------------------- renderers
def render_text(m: Message) -> str:
    lines = [m.subject, "", m.text]
    if m.fields:
        lines.append("")
        lines.extend(f"{k}: {v}" for k, v in m.fields)
    if m.items:
        lines.append("")
        lines.extend(f"  - {i}" for i in m.items)
    if m.url:
        lines += ["", f"Open in Skopeo: {m.url}"]
    lines += ["", "--", "You receive this because of a notification rule in Skopeo (Settings > Notifications)."]
    return "\n".join(lines)


def render_html(m: Message) -> str:
    e = html.escape
    colour = f"#{SEVERITY_COLOURS.get(m.severity, SEVERITY_COLOURS['info']):06x}"
    rows = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#6f7785;white-space:nowrap">{e(k)}</td><td style="padding:4px 0">{e(v)}</td></tr>'
        for k, v in m.fields
    )
    items = "".join(f'<li style="margin:4px 0">{e(i)}</li>' for i in m.items)
    button = (
        f'<p style="margin:20px 0 0"><a href="{e(m.url, quote=True)}" style="background:{colour};color:#fff;text-decoration:none;padding:9px 16px;border-radius:4px;font-weight:600">Open in Skopeo</a></p>'
        if m.url
        else ""
    )
    paragraphs = "".join(f'<p style="margin:0 0 10px">{e(p)}</p>' for p in m.text.split("\n\n") if p.strip())
    return f"""<!doctype html><html><body style="margin:0;background:#f3f4f6;font-family:-apple-system,Segoe UI,Arial,sans-serif;color:#14181e">
<div style="max-width:620px;margin:0 auto;padding:24px">
<div style="background:#fff;border:1px solid #dcdfe5;border-top:4px solid {colour};border-radius:4px;padding:22px 24px">
<div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#6f7785;margin-bottom:6px">Skopeo</div>
<h1 style="font-size:20px;margin:0 0 14px">{e(m.subject)}</h1>
{paragraphs}
{f'<table style="font-size:14px;border-collapse:collapse;margin:10px 0">{rows}</table>' if rows else ""}
{f'<ul style="padding-left:18px;font-size:14px">{items}</ul>' if items else ""}
{button}
</div>
<p style="font-size:12px;color:#6f7785;margin:14px 2px">You receive this because of a notification rule in Skopeo (Settings &rsaquo; Notifications).</p>
</div></body></html>"""


def _slack_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def slack_payload(m: Message) -> dict[str, Any]:
    head = f"{SEVERITY_EMOJI.get(m.severity, '')} *{_slack_escape(m.subject)}*".strip()
    body = _slack_escape(m.text)
    blocks: list[dict[str, Any]] = [{"type": "section", "text": {"type": "mrkdwn", "text": f"{head}\n{body}"[:2900]}}]
    if m.fields:
        blocks.append(
            {
                "type": "section",
                "fields": [{"type": "mrkdwn", "text": f"*{_slack_escape(k)}*\n{_slack_escape(v)}"[:1900]} for k, v in m.fields[:10]],
            }
        )
    if m.items:
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(f"• {_slack_escape(i)}" for i in m.items[:12])[:2900]}}
        )
    if m.url:
        blocks.append(
            {"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": "Open in Skopeo"}, "url": m.url}]}
        )
    return {"text": f"{m.subject}: {m.text}"[:300], "blocks": blocks, "unfurl_links": False}


def discord_payload(m: Message) -> dict[str, Any]:
    description = m.text
    if m.items:
        description += "\n\n" + "\n".join(f"• {i}" for i in m.items[:12])
    embed: dict[str, Any] = {
        "title": m.subject[:256],
        "description": description[:3900],
        "color": SEVERITY_COLOURS.get(m.severity, SEVERITY_COLOURS["info"]),
        "fields": [{"name": k[:256], "value": (v or "-")[:1024], "inline": True} for k, v in m.fields[:10]],
        "footer": {"text": "Skopeo"},
    }
    if m.url:
        embed["url"] = m.url
    return {"username": "Skopeo", "embeds": [embed], "allowed_mentions": {"parse": []}}


def webhook_payload(m: Message, delivery_id: str) -> dict[str, Any]:
    return {
        "id": delivery_id,
        "event": m.event,
        "created_at": int(time.time()),
        "subject": m.subject,
        "text": m.text,
        "severity": m.severity,
        "url": m.url,
        "fields": dict(m.fields),
        "items": m.items,
        "data": m.data,
    }


def sign_webhook(secret: str, timestamp: int, body: bytes) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


# --------------------------------------------------------------------- transport
class DefaultTransport:
    """Sends for real. Each call is bounded by NOTIFICATION_TIMEOUT_SECONDS and never follows redirects."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, kind: str, target: str, message: Message, *, signing_secret: str | None = None) -> dict[str, Any]:
        if kind == "email":
            return self._email(target, message)
        if kind == "slack":
            return self._post(target, slack_payload(message))
        if kind == "discord":
            return self._post(target, discord_payload(message))
        if kind == "webhook":
            assert_public_destination(target, allow_private=self.settings.notifications_allow_private_webhooks)
            delivery_id = str(uuid.uuid4())
            body = json.dumps(webhook_payload(message, delivery_id), default=str).encode()
            headers = {"X-Skopeo-Event": message.event, "X-Skopeo-Delivery": delivery_id}
            if signing_secret:
                headers["X-Skopeo-Signature"] = sign_webhook(signing_secret, int(time.time()), body)
            return self._post(target, None, raw=body, headers=headers)
        raise DeliveryError(f"unknown channel kind {kind}")

    def _post(
        self, url: str, payload: dict[str, Any] | None, *, raw: bytes | None = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        body = raw if raw is not None else json.dumps(payload).encode()
        hdrs = {"Content-Type": "application/json", "User-Agent": "Skopeo-Notifications/1.0", **(headers or {})}
        try:
            resp = httpx.post(url, content=body, headers=hdrs, timeout=self.settings.notification_timeout_seconds, follow_redirects=False)
        except httpx.HTTPError as exc:
            raise DeliveryError(f"{type(exc).__name__}: {redact(str(exc))[:200]}") from exc
        if resp.status_code >= 300:
            raise DeliveryError(f"HTTP {resp.status_code}: {redact(resp.text)[:200]}")
        return {"http_status": resp.status_code}

    def _email(self, to: str, m: Message) -> dict[str, Any]:
        s = self.settings
        if not s.email_configured:
            raise DeliveryError("email is not configured on this server (set SMTP_HOST and SMTP_FROM)")
        sender = s.smtp_from.strip() or s.smtp_username.strip()
        name, addr = parseaddr(sender)
        msg = EmailMessage()
        msg["Subject"] = m.subject
        msg["From"] = formataddr((name or "Skopeo", addr))
        msg["To"] = to
        msg["Message-ID"] = make_msgid(domain=addr.rsplit("@", 1)[-1] if "@" in addr else None)
        msg["X-Skopeo-Event"] = m.event
        msg.set_content(render_text(m))
        msg.add_alternative(render_html(m), subtype="html")
        timeout = s.notification_timeout_seconds
        context = ssl.create_default_context()
        try:
            if s.smtp_security == "ssl":
                server: smtplib.SMTP = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=timeout, context=context)
            else:
                server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=timeout)
            with server:
                server.ehlo()
                if s.smtp_security == "starttls":
                    server.starttls(context=context)
                    server.ehlo()
                if s.smtp_username and s.smtp_password is not None:
                    server.login(s.smtp_username, s.smtp_password.get_secret_value())
                refused = server.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            raise DeliveryError(f"SMTP error: {type(exc).__name__}: {redact(str(exc))[:200]}") from exc
        if refused:
            raise DeliveryError(f"recipient refused: {to}")
        return {"smtp": s.smtp_host}
