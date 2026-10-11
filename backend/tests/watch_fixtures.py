"""A tiny upstream library in two versions, a downstream project that uses it, and a fake source."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from app.watch.sources import Checkout

UPSTREAM_URL = "https://github.com/example/tokenlib"

V1 = {
    "pyproject.toml": '[project]\nname = "tokenlib"\nversion = "1.7.1"\n',
    "CHANGELOG.md": "# Changelog\n\n## 1.7.1\n- Fix padding bug\n",
    "tokenlib/__init__.py": "from .api import Client, decode, encode, legacy_helper\nfrom .exceptions import InvalidToken\n\n__version__ = '1.7.1'\n",
    "tokenlib/exceptions.py": "class InvalidToken(Exception):\n    pass\n",
    "tokenlib/api.py": '''
class Client:
    def __init__(self, options=None):
        self.options = options or {}

    def decode(self, token, key="", verify=True, algorithms=None, options=None):
        """Decode a token."""
        return {"token": token}

    def encode(self, payload, key, algorithm="HS256"):
        return "x.y.z"


_default = Client()
decode = _default.decode
encode = _default.encode


def legacy_helper(value):
    return value
''',
    "tests/test_api.py": "def test_nothing():\n    assert True\n",
}

V2 = {
    "pyproject.toml": '[project]\nname = "tokenlib"\nversion = "2.0.0"\n',
    "CHANGELOG.md": (
        "# Changelog\n\n## 2.0.0\n- BREAKING: removed the `verify` argument of decode(); pass options instead\n"
        "- `algorithms` is now required\n- Default algorithm is now HS512\n- legacy_helper is deprecated\n\n## 1.7.1\n- Fix padding bug\n"
    ),
    "tokenlib/__init__.py": "from .api import Client, decode, encode, legacy_helper, new_helper\nfrom .errors import InvalidToken\n\n__version__ = '2.0.0'\n",
    "tokenlib/errors.py": "class InvalidToken(Exception):\n    pass\n",
    "tokenlib/api.py": '''
import warnings


class Client:
    def __init__(self, options=None):
        self.options = options or {}

    def decode(self, token, key="", *, algorithms, options=None):
        """Decode a token. `verify` was removed."""
        return {"token": token, "checked": True}

    def encode(self, payload, key, algorithm="HS512"):
        return "x.y.z"


_default = Client()
decode = _default.decode
encode = _default.encode


def legacy_helper(value):
    warnings.warn("use new_helper", DeprecationWarning, stacklevel=2)
    return value


def new_helper(value):
    return value
''',
}

PROJECT_FILES = {
    "requirements.txt": "fastapi==0.115.0\ntokenlib==1.7.1\n",
    "app/auth.py": """import tokenlib
from tokenlib.exceptions import InvalidToken
from tokenlib import legacy_helper


def check(token, key):
    try:
        return tokenlib.decode(token, key, verify=False)
    except InvalidToken:
        return None


def sign(payload, key):
    return tokenlib.encode(payload, key)


def normalise(value):
    return legacy_helper(value)
""",
    "app/safe.py": """import tokenlib


def strict(token, key):
    return tokenlib.decode(token, key, algorithms=["HS256"])
""",
    "app/unrelated.py": "import json\n\nprint(json.dumps({}))\n",
}


def write_tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


class FakeSource:
    """Stands in for GitSource: serves directories instead of cloning GitHub."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.trees: dict[tuple[str, str | None], tuple[Path, str]] = {}
        self.tags: list[str] = []
        self.checkouts: list[tuple[str, str | None]] = []

    def serve(self, url: str, ref: str | None, files: dict[str, str], sha: str) -> None:
        root = self.tmp / f"src-{len(self.trees)}"
        if root.exists():
            shutil.rmtree(root)
        self.trees[(url, ref)] = (write_tree(root, files), sha)

    def checkout(self, url: str, ref: str | None, dest: Path, depth: int) -> Checkout:
        self.checkouts.append((url, ref))
        if (url, ref) not in self.trees:
            raise RuntimeError(f"no such ref {url}@{ref}")
        src, sha = self.trees[(url, ref)]
        shutil.copytree(src, dest)
        return Checkout(root=dest, sha=sha, ref=ref or "main")

    def list_tags(self, url: str, workdir: Path) -> list[str]:
        return list(self.tags)

    def log(self, checkout: Checkout, base_sha: str | None, limit: int = 100) -> list[dict[str, Any]] | None:
        return [{"sha": checkout.sha, "author": "Maintainer", "date": "2026-10-01T00:00:00+00:00", "message": "Release 2.0.0"}]
