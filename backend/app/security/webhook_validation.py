"""Validation of notification targets (user input that makes the server send requests).

Slack and Discord webhooks must point at the vendors' own webhook endpoints. Generic webhooks
must be HTTPS on the default port, carry no credentials, and resolve only to public addresses
(checked again right before every delivery, which also narrows DNS-rebinding windows).
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlsplit


class InvalidNotificationTarget(ValueError):
    pass


SLACK_HOSTS = {"hooks.slack.com"}
SLACK_PATH_PREFIXES = ("/services/", "/triggers/", "/workflows/")
DISCORD_HOSTS = {"discord.com", "discordapp.com", "ptb.discord.com", "canary.discord.com"}
DISCORD_PATH_PREFIX = "/api/webhooks/"

_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
_HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")


def validate_email(address: str) -> str:
    value = (address or "").strip()
    if len(value) > 254 or not _EMAIL_RE.match(value):
        raise InvalidNotificationTarget("enter a valid email address")
    local, domain = value.rsplit("@", 1)
    return f"{local}@{domain.lower()}"


def _parts(url: str):
    value = (url or "").strip()
    if not value or len(value) > 2000 or any(ord(c) < 0x21 or ord(c) == 0x7F for c in value):
        raise InvalidNotificationTarget("webhook URL is empty, too long or contains forbidden characters")
    parts = urlsplit(value)
    if parts.scheme != "https":
        raise InvalidNotificationTarget("webhook URLs must use https://")
    if parts.username or parts.password or "@" in parts.netloc:
        raise InvalidNotificationTarget("credentials in webhook URLs are not allowed")
    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidNotificationTarget("invalid port") from exc
    if port not in (None, 443):
        raise InvalidNotificationTarget("webhooks must use the default HTTPS port")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host or not _HOST_RE.match(host):
        raise InvalidNotificationTarget("invalid webhook host")
    if parts.fragment:
        raise InvalidNotificationTarget("fragments are not allowed in webhook URLs")
    return value, parts, host


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def validate_webhook_url(kind: str, url: str, *, allow_private: bool = False) -> str:
    value, parts, host = _parts(url)
    if kind == "slack":
        if host not in SLACK_HOSTS or not parts.path.startswith(SLACK_PATH_PREFIXES):
            raise InvalidNotificationTarget("expected a Slack incoming webhook URL (https://hooks.slack.com/services/…)")
    elif kind == "discord":
        if host not in DISCORD_HOSTS or not parts.path.startswith(DISCORD_PATH_PREFIX):
            raise InvalidNotificationTarget("expected a Discord webhook URL (https://discord.com/api/webhooks/…)")
    elif kind == "webhook":
        try:
            literal = ipaddress.ip_address(host.strip("[]"))
        except ValueError:
            literal = None
        if literal is not None and not allow_private and not _is_public(literal):
            raise InvalidNotificationTarget("webhooks to private or local addresses are not allowed")
        if not allow_private and (host == "localhost" or host.endswith((".localhost", ".local", ".internal"))):
            raise InvalidNotificationTarget("webhooks to private or local addresses are not allowed")
    else:
        raise InvalidNotificationTarget(f"unknown webhook kind: {kind}")
    return value


def assert_public_destination(url: str, *, allow_private: bool = False) -> None:
    """Resolve the webhook host and refuse private, loopback, link-local or reserved addresses."""
    if allow_private:
        return
    _, _, host = _parts(url)
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise InvalidNotificationTarget(f"could not resolve {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        if not _is_public(ip):
            raise InvalidNotificationTarget(f"{host} resolves to a private or local address")
