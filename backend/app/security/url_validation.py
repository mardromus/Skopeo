"""Strict validation of repository URLs and branch names (untrusted user input)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit


class InvalidRepositoryURL(ValueError):
    pass


class InvalidBranchName(ValueError):
    pass


_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,199}$")
_ALLOWED_HOSTS = {"github.com", "www.github.com"}
_RESERVED_OWNERS = {"settings", "orgs", "marketplace", "explore", "topics", "login", "about", "features"}


@dataclass(frozen=True)
class RepositoryRef:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def canonical_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}"

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}.git"


def validate_repository_url(url: str) -> RepositoryRef:
    """Accept only ``https://github.com/<owner>/<repo>`` (optionally ``.git`` / trailing slash).

    Rejects credentials, ports, query strings, fragments, percent-encoding, control characters,
    alternative schemes (ssh, file, git, http) and non-GitHub hosts.
    """
    if not isinstance(url, str):
        raise InvalidRepositoryURL("repository_url must be a string")
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in url):
        raise InvalidRepositoryURL("repository_url contains control characters")
    raw = url.strip(" ")
    if not raw or len(raw) > 300:
        raise InvalidRepositoryURL("repository_url is empty or too long")
    if any(ord(c) < 0x21 for c in raw) or "%" in raw or "\\" in raw:
        raise InvalidRepositoryURL("repository_url contains forbidden characters")
    parts = urlsplit(raw)
    if parts.scheme != "https":
        raise InvalidRepositoryURL("only https:// GitHub URLs are supported")
    if parts.username or parts.password or "@" in parts.netloc:
        raise InvalidRepositoryURL("credentials in repository URLs are not allowed")
    if parts.port is not None or ":" in parts.netloc:
        raise InvalidRepositoryURL("custom ports are not allowed")
    if (parts.hostname or "").lower() not in _ALLOWED_HOSTS:
        raise InvalidRepositoryURL("only github.com repositories are supported")
    if parts.query or parts.fragment:
        raise InvalidRepositoryURL("query strings and fragments are not allowed")
    segments = [s for s in parts.path.split("/") if s]
    if len(segments) != 2:
        raise InvalidRepositoryURL("expected https://github.com/<owner>/<repository>")
    owner, name = segments
    if name.endswith(".git"):
        name = name[:-4]
    if not _OWNER_RE.match(owner) or owner.lower() in _RESERVED_OWNERS:
        raise InvalidRepositoryURL("invalid GitHub owner name")
    if not _REPO_RE.match(name) or name in {".", ".."} or name.startswith("."):
        raise InvalidRepositoryURL("invalid GitHub repository name")
    return RepositoryRef(owner=owner, name=name)


def validate_branch(branch: str) -> str:
    """Conservative subset of git ref-name rules; also blocks option injection (leading '-')."""
    if not isinstance(branch, str):
        raise InvalidBranchName("branch must be a string")
    value = branch.strip()
    if not _BRANCH_RE.match(value):
        raise InvalidBranchName("invalid branch name")
    if (
        ".." in value
        or "//" in value
        or "@{" in value
        or value.endswith("/")
        or value.endswith(".")
        or value.endswith(".lock")
        or "/." in value
    ):
        raise InvalidBranchName("invalid branch name")
    return value
