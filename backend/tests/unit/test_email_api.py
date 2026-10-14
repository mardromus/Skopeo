import httpx
import pytest

from app.config import Settings
from app.notifications import transports
from app.notifications.transports import DefaultTransport, DeliveryError, Message


def _msg():
    return Message(event="test", subject="Hi", text="Body")


def _post_capture(monkeypatch, status=200):
    seen = {}

    def fake_post(url, **kw):
        seen.update(url=url, **kw)
        return httpx.Response(status, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(transports.httpx, "post", fake_post)
    return seen


@pytest.mark.parametrize("provider,host", [("brevo", "api.brevo.com"), ("resend", "api.resend.com")])
def test_email_goes_over_https_api(monkeypatch, provider, host):
    seen = _post_capture(monkeypatch)
    s = Settings(email_provider=provider, email_api_key="k-123", smtp_from="Skopeo <a@example.com>")
    assert s.email_configured
    assert DefaultTransport(s).send("email", "u@example.com", _msg())["provider"] == provider
    assert host in seen["url"]


def test_api_error_does_not_leak_key(monkeypatch):
    _post_capture(monkeypatch, status=401)
    s = Settings(email_provider="brevo", email_api_key="k-123", smtp_from="a@example.com")
    with pytest.raises(DeliveryError) as exc:
        DefaultTransport(s).send("email", "u@example.com", _msg())
    assert "k-123" not in str(exc.value)


def test_api_provider_needs_key_and_sender():
    assert not Settings(email_provider="brevo", smtp_from="a@example.com").email_configured
    assert not Settings(email_provider="resend", email_api_key="k").email_configured
