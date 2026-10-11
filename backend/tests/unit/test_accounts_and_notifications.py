"""Firebase ID-token verification, notification target validation, rules, verification codes and rendering."""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth import FirebaseTokenVerifier, InvalidIdToken
from app.config import get_settings
from app.models import NotificationRule
from app.notifications import Message, NotificationError, NotificationService
from app.notifications.transports import discord_payload, render_html, sign_webhook, slack_payload
from app.security.webhook_validation import InvalidNotificationTarget, validate_email, validate_webhook_url
from app.services.account_store import AccountStore
from tests.firebase_helpers import FakeFirebase


# ------------------------------------------------------------------ Firebase tokens
@pytest.fixture()
def fb() -> FakeFirebase:
    return FakeFirebase()


def test_valid_token_is_accepted(fb):
    claims = FirebaseTokenVerifier(fb.project_id, fb.fetch).verify(fb.token())
    assert claims["sub"] == "uid-alice" and claims["email"] == "alice@example.com"


@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"aud": "someone-else"}, "audience"),
        ({"iss": "https://securetoken.google.com/someone-else"}, "issuer"),
        ({"exp": int(time.time()) - 600}, "expired"),
        ({"iat": int(time.time()) + 3600}, "future"),
        ({"auth_time": int(time.time()) + 3600}, "auth_time"),
        ({"auth_time": None}, "auth_time"),
        ({"sub": ""}, "subject"),
    ],
)
def test_invalid_claims_are_rejected(fb, overrides, reason):
    with pytest.raises(InvalidIdToken):
        FirebaseTokenVerifier(fb.project_id, fb.fetch).verify(fb.token(**overrides))


def test_wrong_key_unknown_kid_and_alg_none_are_rejected(fb):
    verifier = FirebaseTokenVerifier(fb.project_id, fb.fetch)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(InvalidIdToken):
        verifier.verify(fb.token(key=other))
    with pytest.raises(InvalidIdToken, match="unknown key"):
        verifier.verify(fb.token(kid="nope"))
    unsigned = jwt.encode({"sub": "x", "aud": fb.project_id}, key=None, algorithm="none")
    with pytest.raises(InvalidIdToken):
        verifier.verify(unsigned)
    hs = jwt.encode({"sub": "x"}, "secret-secret-secret-secret-secret", algorithm="HS256", headers={"kid": fb.kid})
    with pytest.raises(InvalidIdToken, match="algorithm"):
        verifier.verify(hs)
    with pytest.raises(InvalidIdToken):
        verifier.verify("not-a-token")


def test_certificates_are_cached(fb):
    verifier = FirebaseTokenVerifier(fb.project_id, fb.fetch)
    for _ in range(3):
        verifier.verify(fb.token())
    assert fb.fetches == 1


# ------------------------------------------------------------- notification targets
def test_webhook_targets_are_restricted():
    assert validate_webhook_url("slack", "https://hooks.slack.com/services/T0/B0/xyz")
    assert validate_webhook_url("discord", "https://discord.com/api/webhooks/1/abc")
    assert validate_webhook_url("webhook", "https://example.com/hooks/skopeo")
    bad = [
        ("slack", "https://evil.example/services/T0"),
        ("slack", "http://hooks.slack.com/services/T0"),
        ("discord", "https://discord.com/channels/1"),
        ("webhook", "https://127.0.0.1/hook"),
        ("webhook", "https://10.0.0.5/hook"),
        ("webhook", "https://[::1]/hook"),
        ("webhook", "https://169.254.169.254/latest/meta-data"),
        ("webhook", "https://localhost/hook"),
        ("webhook", "https://user:pass@example.com/hook"),
        ("webhook", "https://example.com:8443/hook"),
        ("webhook", "ftp://example.com/hook"),
        ("webhook", "https://example.com/hook\r\nX: y"),
    ]
    for kind, url in bad:
        with pytest.raises(InvalidNotificationTarget):
            validate_webhook_url(kind, url)
    assert validate_webhook_url("webhook", "https://10.0.0.5/hook", allow_private=True)


def test_email_validation():
    assert validate_email(" Alice@Example.COM ") == "Alice@example.com"
    for bad in ("nope", "a@b", "a@b.c\r\nBcc: x@y.z", "@example.com", "a" * 250 + "@example.com"):
        with pytest.raises(InvalidNotificationTarget):
            validate_email(bad)


# ------------------------------------------------------------------- the service
class RecordingTransport:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[str, str, Message, str | None]] = []
        self.fail = fail

    def send(self, kind, target, message, *, signing_secret=None):
        from app.notifications import DeliveryError

        if self.fail:
            raise DeliveryError("HTTP 500: boom")
        self.sent.append((kind, target, message, signing_secret))
        return {"ok": True}


def _user(store: AccountStore, uid: str, email: str):
    return store.upsert_firebase_user({"sub": uid, "email": email, "email_verified": True, "name": uid})


def test_channels_rules_and_dispatch():
    store = AccountStore()
    transport = RecordingTransport()
    svc = NotificationService(get_settings().model_copy(update={"notifications_dry_run": False}), store, transport)
    alice = _user(store, "n-alice", "alice-n@example.com")
    bob = _user(store, "n-bob", "bob-n@example.com")

    own = svc.create_channel(alice, "email", "Me", "alice-n@example.com")
    assert own["channel"]["verified"] is True and own["verification_sent"] is False
    slack = svc.create_channel(alice, "slack", "Team", "https://hooks.slack.com/services/T/B/secret-token", ["watch.impact"])
    assert slack["channel"]["target"].startswith("https://hooks.slack.com/…") and "secret-token" not in slack["channel"]["target"]
    hook = svc.create_channel(alice, "webhook", "CI", "https://ci.example.com/skopeo")
    assert hook["signing_secret"].startswith("whsec_")

    subs = svc.subscriptions(alice.id)
    assert subs[slack["channel"]["channel_id"]] == ["watch.impact"]
    assert "investigation.completed" in subs[own["channel"]["channel_id"]]

    msg = Message(event="watch.impact", subject="tokenlib changes affect api", text="2 places break")
    results = svc.dispatch(alice.id, "watch.impact", msg, {"impact_level": "breaking", "project_id": "p1", "watch_id": "w1"})
    assert {r["status"] for r in results} == {"sent"} and len(results) == 3
    assert {t[0] for t in transport.sent} == {"email", "slack", "webhook"}
    assert next(t for t in transport.sent if t[0] == "webhook")[3] == hook["signing_secret"]

    # min_impact filter: a low impact does not reach the default "medium" rule
    transport.sent.clear()
    assert svc.dispatch(alice.id, "watch.impact", msg, {"impact_level": "low"}) == []
    # nothing leaks to another user
    assert svc.dispatch(bob.id, "watch.impact", msg, {"impact_level": "breaking"}) == []
    assert transport.sent == []
    with pytest.raises(LookupError):
        svc.test_channel(bob, slack["channel"]["channel_id"])

    # disabled channels are logged as skipped
    svc.update_channel(alice, slack["channel"]["channel_id"], enabled=False)
    results = svc.dispatch(alice.id, "watch.impact", msg, {"impact_level": "high"})
    assert {"skipped"} <= {r["status"] for r in results}
    log = store.list_deliveries(alice.id)
    assert any(d.status == "skipped" and d.error == "channel disabled" for d in log)


def test_failed_delivery_is_recorded_on_channel():
    store = AccountStore()
    svc = NotificationService(get_settings().model_copy(update={"notifications_dry_run": False}), store, RecordingTransport(fail=True))
    carol = _user(store, "n-carol", "carol@example.com")
    ch = svc.create_channel(carol, "discord", "", "https://discord.com/api/webhooks/1/abc")["channel"]
    out = svc.test_channel(carol, ch["channel_id"])
    assert out["status"] == "failed" and "HTTP 500" in out["error"]
    assert store.get_channel(carol.id, ch["channel_id"]).last_error.startswith("HTTP 500")


def test_email_verification_codes():
    store = AccountStore()
    transport = RecordingTransport()
    svc = NotificationService(get_settings().model_copy(update={"notifications_dry_run": False}), store, transport)
    dave = _user(store, "n-dave", "dave@example.com")
    created = svc.create_channel(dave, "email", "Work", "dave@work.example")
    assert created["channel"]["verified"] is False and created["verification_sent"] is True
    code = transport.sent[0][2].subject.rsplit(" ", 1)[-1]
    cid = created["channel"]["channel_id"]
    with pytest.raises(NotificationError, match="verify this channel first"):
        svc.test_channel(dave, cid)
    with pytest.raises(NotificationError, match="not right"):
        svc.verify_channel(dave, cid, "000000" if code != "000000" else "111111")
    assert svc.verify_channel(dave, cid, code)["verified"] is True
    with pytest.raises(NotificationError, match="already verified"):
        svc.resend_code(dave, cid)

    # five wrong codes lock the code
    other = svc.create_channel(dave, "email", "Old", "dave@old.example")["channel"]["channel_id"]
    for _ in range(5):
        with pytest.raises(NotificationError):
            svc.verify_channel(dave, other, "999999x")
    with pytest.raises(NotificationError, match="too many"):
        svc.verify_channel(dave, other, "123456")
    with pytest.raises(NotificationError, match="wait a minute"):
        svc.resend_code(dave, other)


def test_dry_run_returns_the_code_for_development():
    store = AccountStore()
    svc = NotificationService(get_settings().model_copy(update={"notifications_dry_run": True}), store, RecordingTransport())
    erin = _user(store, "n-erin", "erin@example.com")
    created = svc.create_channel(erin, "email", "", "erin@elsewhere.example")
    assert svc.verify_channel(erin, created["channel"]["channel_id"], created["dev_verification_code"])["verified"]
    assert svc.test_channel(erin, created["channel"]["channel_id"])["status"] == "dry_run"


def test_rule_filters():
    rule = NotificationRule(event="investigation.risk", filters={"min_priority": "P1"}, channel_ids=[])
    assert NotificationService.rule_matches(rule, {"top_priority": "P0"})
    assert NotificationService.rule_matches(rule, {"top_priority": "P1"})
    assert not NotificationService.rule_matches(rule, {"top_priority": "P2"})
    assert not NotificationService.rule_matches(rule, {})
    scoped = NotificationRule(event="watch.impact", filters={"min_impact": "high", "watch_id": "w1"}, channel_ids=[])
    assert NotificationService.rule_matches(scoped, {"impact_level": "breaking", "watch_id": "w1"})
    assert not NotificationService.rule_matches(scoped, {"impact_level": "breaking", "watch_id": "w2"})
    assert not NotificationService.rule_matches(scoped, {"impact_level": "medium", "watch_id": "w1"})


def test_renderers_escape_and_sign():
    m = Message(
        event="x", subject="<script>alert(1)</script>", text="a & b", url="https://skopeo.example/x", fields=[("k", "<v>")], items=["<i>"]
    )
    html = render_html(m)
    assert "<script>" not in html and "&lt;script&gt;" in html and "&lt;v&gt;" in html
    assert "<script>" not in slack_payload(m)["blocks"][0]["text"]["text"]
    d = discord_payload(m)
    assert d["allowed_mentions"] == {"parse": []} and d["embeds"][0]["url"] == m.url
    sig = sign_webhook("whsec_test", 1700000000, b'{"a":1}')
    assert sig.startswith("t=1700000000,v1=") and len(sig.split("v1=")[1]) == 64
