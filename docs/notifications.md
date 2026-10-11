# Notifications

Each user connects **channels** (where to send) and **rules** (what to send where) under
**Settings → Notifications**. Every attempt is written to the **delivery log**, including the
ones that were skipped and why.

## Events

| Event | When | Filters |
| --- | --- | --- |
| `investigation.completed` | an investigation you started finished | — |
| `investigation.failed` | it failed, was cancelled or interrupted | — |
| `investigation.risk` | a finished investigation has a verified risk at or above a priority | `min_priority` (P0–P3, default P1) |
| `watch.impact` | an upstream change touches code in your project | `min_impact` (low/medium/high/breaking, default medium), `project_id`, `watch_id` |
| `watch.update` | a watched upstream has new API changes or commits (digest, even with no impact) | `project_id`, `watch_id` |
| `watch.failed` | Skopeo could not check a watched repository | `project_id`, `watch_id` |

Adding a channel subscribes it to the usual set (`investigation.completed`,
`investigation.failed`, `watch.impact`, `watch.failed`); untick what you don't want. Rules can be
narrowed further, for example "only breaking impacts from `pyjwt`, to Slack".

## Channels

### Email (SMTP)

Any SMTP account works. Set on the server:

```bash
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_SECURITY=starttls        # starttls (587) | ssl (465) | none
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_FROM="Skopeo <alerts@example.com>"
PUBLIC_BASE_URL=https://skopeo.example.com   # links in messages
```

| Provider | Host / port | Username | Password |
| --- | --- | --- | --- |
| Gmail / Google Workspace | `smtp.gmail.com` / 587 | your address | an **App password** (Google Account → Security → 2-Step Verification → App passwords) |
| SendGrid | `smtp.sendgrid.net` / 587 | `apikey` | your API key |
| Resend | `smtp.resend.com` / 587 | `resend` | your API key |
| Mailgun | `smtp.mailgun.org` / 587 | SMTP login from the domain page | its password |
| Amazon SES | `email-smtp.<region>.amazonaws.com` / 587 | SMTP credentials (not IAM keys) | SMTP password |

`SMTP_FROM` must be an address or domain the provider lets you send from (a verified sender).

**Verification.** Your own Google sign-in address is trusted immediately. Any other address gets
a 6-digit code by email and receives nothing until the code is entered. Codes expire after
30 minutes, allow 5 attempts, and can be resent once a minute. This stops the server being used
to mail strangers.

### Slack

Slack → **Apps** → **Incoming Webhooks** → *Add to Slack* → pick a channel → copy the URL
(`https://hooks.slack.com/services/...`). Paste it as a Slack channel in Skopeo. Messages use
Block Kit with an **Open in Skopeo** button.

### Discord

Channel settings → **Integrations** → **Webhooks** → *New Webhook* → **Copy Webhook URL**
(`https://discord.com/api/webhooks/...`). Messages are embeds coloured by severity. Mentions are
disabled.

### Generic webhook

Any HTTPS endpoint (CI, a chat-ops bot, Zapier/Make/n8n, PagerDuty via a relay). Skopeo POSTs
JSON:

```json
{
  "id": "delivery uuid",
  "event": "watch.impact",
  "created_at": 1791715696,
  "subject": "jpadilla/pyjwt changes affect shopfront-api (breaking)",
  "text": "…summary…",
  "severity": "critical",
  "url": "https://skopeo.example.com/projects/…",
  "fields": {"Upstream": "jpadilla/pyjwt", "Impact": "breaking"},
  "items": ["[breaking] app/auth.py:9: Your call to `jwt.decode` will fail"],
  "data": {"report_id": "…", "watch_id": "…", "project_id": "…", "impact_level": "breaking", "stats": {}}
}
```

Headers: `X-Skopeo-Event`, `X-Skopeo-Delivery` and `X-Skopeo-Signature: t=<unix>,v1=<hex>`,
where `v1 = HMAC_SHA256(signing_secret, "<t>." + raw_body)`. The `whsec_…` signing secret is
shown once when you add the channel. **Rotate secret** issues a new one.

```python
import hashlib, hmac, time

def verify(secret: str, header: str, body: bytes, tolerance: int = 300) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(","))
    t = int(parts["t"])
    expected = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return abs(time.time() - t) <= tolerance and hmac.compare_digest(expected, parts["v1"])
```

```js
import crypto from "node:crypto";
export function verify(secret, header, rawBody, tolerance = 300) {
  const { t, v1 } = Object.fromEntries(header.split(",").map((p) => p.split("=")));
  const expected = crypto.createHmac("sha256", secret).update(`${t}.`).update(rawBody).digest("hex");
  return Math.abs(Date.now() / 1000 - Number(t)) <= tolerance && crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(v1));
}
```

## Safety

* Slack and Discord URLs must point at `hooks.slack.com` / `discord.com/api/webhooks`.
* Generic webhooks must be `https://` on port 443 with no credentials in the URL. The host is
  resolved before **every** delivery and refused if any address is private, loopback,
  link-local (cloud metadata), multicast or reserved. Set
  `NOTIFICATIONS_ALLOW_PRIVATE_WEBHOOKS=true` only for self-hosted setups that must reach an
  internal service.
* Requests time out after `NOTIFICATION_TIMEOUT_SECONDS` (10 s) and never follow redirects.
* Webhook URLs embed their own secret token, so the API and UI only ever show the host and the
  last 4 characters.
* All text is redacted for known secret formats before it is stored or sent. Email bodies are
  HTML-escaped and Slack text is escaped.
* A failing channel never breaks an investigation or a watch check. The error is shown on the
  channel and in the delivery log.

## Development

`NOTIFICATIONS_DRY_RUN=true` logs every delivery as **dry run** without sending, and returns
email verification codes in the API response (`dev_verification_code`) so you can confirm an
address without a mail server.
