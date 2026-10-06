"""Secret scanning (high-recall detector) and placeholder recognition (used by the red-team)."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from app.security.redaction import mask_secret


@dataclass(frozen=True)
class SecretRule:
    rule_id: str
    title: str
    pattern: re.Pattern[str]
    severity: str
    group: int = 0


SECRET_RULES: list[SecretRule] = [
    SecretRule("secret.aws_access_key", "AWS access key ID", re.compile(r"\b((?:AKIA|ASIA)[0-9A-Z]{16})\b"), "high", 1),
    SecretRule(
        "secret.aws_secret_key",
        "AWS secret access key",
        re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*[\"']?([A-Za-z0-9/+=]{40})\b"),
        "high",
        1,
    ),
    SecretRule("secret.github_token", "GitHub token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36,255})\b"), "high", 1),
    SecretRule("secret.github_pat", "GitHub fine-grained token", re.compile(r"\b(github_pat_[A-Za-z0-9_]{60,255})\b"), "high", 1),
    SecretRule(
        "secret.private_key",
        "Private key material",
        re.compile(r"(-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----)"),
        "critical",
        1,
    ),
    SecretRule("secret.stripe_live", "Stripe live secret key", re.compile(r"\b(sk_live_[0-9A-Za-z]{24,})\b"), "critical", 1),
    SecretRule("secret.google_api_key", "Google API key", re.compile(r"\b(AIza[0-9A-Za-z\-_]{35})\b"), "high", 1),
    SecretRule("secret.slack_token", "Slack token", re.compile(r"\b(xox[abprs]-[0-9A-Za-z-]{10,})\b"), "high", 1),
    SecretRule(
        "secret.generic_assignment",
        "Hardcoded credential-like literal",
        re.compile(
            r"(?i)\b[A-Za-z0-9_]*(?:secret|password|passwd|api_?key|auth_?token|access_?token)[A-Za-z0-9_]*\s*[:=]\s*[\"']([^\"'\s]{12,})[\"']"
        ),
        "medium",
        1,
    ),
]

# Values published in vendor documentation as non-functional examples.
DOCUMENTED_PLACEHOLDERS = {
    "AKIAIOSFODNN7EXAMPLE": "AWS documentation example access key ID",
    "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY": "AWS documentation example secret access key",
    "AKIAI44QH8DHBEXAMPLE": "AWS documentation example access key ID",
    "je7MtGbClwBF/2Zp9Utk/h3yCo8nvbEXAMPLEKEY": "AWS documentation example secret access key",
}
PLACEHOLDER_MARKERS = (
    "example",
    "dummy",
    "placeholder",
    "changeme",
    "change_me",
    "fake",
    "sample",
    "xxxxxxxx",
    "your_",
    "your-",
    "<",
    "redacted",
    "insert",
)


@dataclass
class SecretMatch:
    rule_id: str
    title: str
    severity: str
    line: int
    value: str
    masked: str
    line_text: str


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    total = len(value)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def scan_text(text: str, max_matches: int = 50) -> list[SecretMatch]:
    matches: list[SecretMatch] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if len(line) > 4000:
            continue
        for rule in SECRET_RULES:
            m = rule.pattern.search(line)
            if not m:
                continue
            value = m.group(rule.group)
            if rule.rule_id == "secret.generic_assignment" and shannon_entropy(value) < 3.0:
                continue
            masked_line = line.replace(value, mask_secret(value)) if value else line
            matches.append(
                SecretMatch(rule.rule_id, rule.title, rule.severity, lineno, value, mask_secret(value), masked_line.strip()[:300])
            )
            break
        if len(matches) >= max_matches:
            break
    return matches


def placeholder_assessment(value: str, context: str = "") -> tuple[bool, str]:
    """Is ``value`` a documented / obvious placeholder rather than a live credential?"""
    if value in DOCUMENTED_PLACEHOLDERS:
        return True, f"value matches a documented placeholder ({DOCUMENTED_PLACEHOLDERS[value]})"
    lowered = value.lower()
    for marker in PLACEHOLDER_MARKERS:
        if marker in lowered:
            return True, f"value contains placeholder marker '{marker}'"
    ctx = context.lower()
    if any(word in ctx for word in ("placeholder", "dummy", "not a real", "grant no access", "example values", "fake credential")):
        return True, "surrounding text documents the value as a placeholder"
    return False, "no placeholder indicators"
