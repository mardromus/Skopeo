"""Upstream API diff, downstream usage discovery and impact assessment."""

from __future__ import annotations

from pathlib import Path

from app.watch.diff import changelog_highlights, compare_params, diff_surfaces
from app.watch.impact import assess_impacts, impact_level, usage_inventory
from app.watch.sources import read_project_tree, tag_for_version
from app.watch.surface import extract_surface, js_params
from app.watch.usage import find_pinned_version, find_usages, js_usages, python_usages
from tests.watch_fixtures import PROJECT_FILES, V1, V2, write_tree


def _surfaces(tmp_path: Path):
    old = extract_surface(write_tree(tmp_path / "v1", V1))
    new = extract_surface(write_tree(tmp_path / "v2", V2))
    return old, new


def test_surface_resolves_reexports_and_bound_methods(tmp_path: Path):
    old, _ = _surfaces(tmp_path)
    assert old["ecosystem"] == "PyPI" and old["package_name"] == "tokenlib" and old["version"] == "1.7.1"
    assert old["import_names"] == ["tokenlib"]
    syms = old["symbols"]
    # `decode = _default.decode` re-exported from the package resolves to the method that runs
    assert syms["tokenlib.decode"]["target"] == "tokenlib.api.Client.decode"
    assert [p["name"] for p in syms["tokenlib.decode"]["params"]] == ["token", "key", "verify", "algorithms", "options"]
    assert syms["tokenlib.Client.decode"]["target"] == "tokenlib.api.Client.decode"
    assert "tokenlib.exceptions.InvalidToken" in syms
    assert not any(k.startswith("tests") for k in syms), "test files are not public API"
    assert old["changelog"]["file"] == "CHANGELOG.md"


def test_diff_classifies_changes(tmp_path: Path):
    old, new = _surfaces(tmp_path)
    changes = diff_surfaces(old, new)
    by = {(c["kind"], c["target"]): c for c in changes}
    decode = by[("signature", "tokenlib.api.Client.decode")]
    assert decode["severity"] == "breaking"
    assert decode["params"]["removed_params"] == ["verify"]
    assert decode["params"]["became_required"] == ["algorithms"] and decode["params"]["became_kwonly"] == ["algorithms", "options"]
    assert "tokenlib.decode" in decode["names"]
    encode = by[("signature", "tokenlib.api.Client.encode")]
    assert encode["severity"] == "behavior" and encode["params"]["default_changed"][0]["new"] == "'HS512'"
    assert ("deprecated", "tokenlib.api.legacy_helper") in by
    assert any(c["kind"] == "moved" and c["symbol"] == "tokenlib.exceptions.InvalidToken" for c in changes)
    assert any(c["kind"] == "module_removed" and c["symbol"] == "tokenlib.exceptions" for c in changes)
    assert any(c["kind"] == "added" and c["symbol"].endswith("new_helper") for c in changes)
    assert changes[0]["severity"] == "breaking"


def test_compare_params_positional_and_defaults():
    old = [{"name": "a", "kind": "pos", "default": None}, {"name": "b", "kind": "pos", "default": "1"}]
    new = [
        {"name": "a", "kind": "pos", "default": None},
        {"name": "b", "kind": "pos", "default": "2"},
        {"name": "c", "kind": "kwonly", "default": None},
    ]
    d = compare_params(old, new)
    assert d["breaking"] and d["added_required"] == ["c"] and d["default_changed"] == [{"name": "b", "old": "1", "new": "2"}]


def test_python_usages_track_aliases_calls_and_references():
    usages = python_usages("app/auth.py", PROJECT_FILES["app/auth.py"], {"tokenlib"})
    calls = [u for u in usages if u["kind"] == "call"]
    decode = next(u for u in calls if u["symbol"] == "tokenlib.decode")
    assert decode["line"] == 8 and decode["positional"] == 2 and decode["keywords"] == ["verify"]
    assert any(u["symbol"] == "tokenlib.legacy_helper" for u in calls)
    assert any(u["kind"] == "reference" and u["symbol"] == "tokenlib.exceptions.InvalidToken" for u in usages)
    assert any(u["kind"] == "import" and u["symbol"] == "tokenlib.exceptions.InvalidToken" for u in usages)

    inst = python_usages("x.py", "from tokenlib import Client\nc = Client()\nc.decode('t', algorithms=['HS256'])\n", {"tokenlib"})
    assert any(u["symbol"] == "tokenlib.Client.decode" and u["kind"] == "call" for u in inst)


def test_impacts_point_at_the_exact_lines(tmp_path: Path):
    old, new = _surfaces(tmp_path)
    changes = diff_surfaces(old, new)
    usages = find_usages(PROJECT_FILES.items(), ecosystem="PyPI", import_names=["tokenlib"])
    impacts = assess_impacts(changes, usages)
    assert impact_level(impacts) == "breaking"
    decode = next(i for i in impacts if i["file"] == "app/auth.py" and i["line"] == 8)
    assert decode["level"] == "breaking" and decode["certainty"] == "certain"
    assert "`verify=`" in decode["explanation"] and "`algorithms`" in decode["explanation"]
    encode = next(i for i in impacts if i["symbol"] == "tokenlib.encode")
    assert encode["level"] == "medium" and encode["certainty"] == "possible" and "HS512" in encode["explanation"]
    assert any(i["symbol"] == "tokenlib.legacy_helper" and i["level"] == "medium" for i in impacts)
    assert any(i["change"]["kind"] in ("moved", "module_removed") and i["file"] == "app/auth.py" and i["line"] == 2 for i in impacts)
    # the strict call already passes algorithms by keyword: compatible
    safe = [i for i in impacts if i["file"] == "app/safe.py"]
    assert safe and all(i["level"] == "low" for i in safe)
    assert not any(i["file"] == "app/unrelated.py" for i in impacts)
    inventory = usage_inventory(usages)
    assert inventory[0]["symbol"] == "tokenlib.decode" and inventory[0]["uses"] == 2


def test_changelog_highlights_only_new_relevant_lines(tmp_path: Path):
    old, new = _surfaces(tmp_path)
    hl = changelog_highlights(old["changelog"], new["changelog"])
    assert any("BREAKING" in h for h in hl) and any("deprecated" in h for h in hl)
    assert not any("padding" in h for h in hl)
    from app.watch.diff import _clean_entry

    assert _clean_entry("Harden ``decode()``. See `GHSA-r6x4 <https://github.com/x>`__ and :func:`jwt.decode`.") == (
        "Harden `decode()`. See GHSA-r6x4 and `jwt.decode`."
    )


def test_pinned_version_detection():
    pin = find_pinned_version(PROJECT_FILES.items(), "tokenlib", "PyPI")
    assert pin == {"manifest": "requirements.txt", "spec": "==1.7.1", "version": "1.7.1", "floor": "1.7.1", "line": 2}
    pkg = '{"dependencies": {"left-pad": "^1.3.0"}}'
    assert find_pinned_version([("package.json", pkg)], "left-pad", "npm")["floor"] == "1.3.0"
    pyproject = '[project]\ndependencies = ["Token_Lib>=2.1,<3"]\n'
    assert find_pinned_version([("pyproject.toml", pyproject)], "token-lib", "PyPI")["floor"] == "2.1"
    assert tag_for_version(["v1.7.0", "v1.7.1", "2.0.0"], "1.7.1") == "v1.7.1"
    assert tag_for_version(["tokenlib-1.7.1"], "1.7.1", "tokenlib") == "tokenlib-1.7.1"
    assert tag_for_version(["v2"], "1.7.1") is None


def test_javascript_surface_and_usages(tmp_path: Path):
    v1 = {
        "package.json": '{"name": "fetchy", "version": "1.0.0"}',
        "src/index.ts": "export function get(url: string, opts?: Options) {}\nexport const post = (url: string, body: unknown) => {}\nexport class Client {}\n",
    }
    v2 = {
        "package.json": '{"name": "fetchy", "version": "2.0.0"}',
        "src/index.ts": "/** @deprecated use request() */\nexport function get(url: string, opts: Options, retries: number) {}\nexport class Client {}\nexport function request(url: string) {}\n",
    }
    old = extract_surface(write_tree(tmp_path / "a", v1))
    new = extract_surface(write_tree(tmp_path / "b", v2))
    assert old["ecosystem"] == "npm" and old["package_name"] == "fetchy"
    assert [p["name"] for p in old["symbols"]["fetchy.get"]["params"]] == ["url", "opts"]
    assert new["symbols"]["fetchy.get"]["deprecated"] is True
    changes = diff_surfaces(old, new)
    kinds = {(c["kind"], c["symbol"]) for c in changes}
    assert ("removed", "fetchy.post") in kinds and ("signature", "fetchy.get") in kinds and ("deprecated", "fetchy.get") in kinds
    project = (
        "import { get, post as send } from 'fetchy';\nconst f = require('fetchy');\nget('/a');\nsend('/b', {x: 1});\nf.get('/c', {}, 3);\n"
    )
    usages = js_usages("src/app.ts", project, {"fetchy"})
    calls = {(u["symbol"], u["line"], u.get("positional")) for u in usages if u["kind"] == "call"}
    assert ("fetchy.get", 3, 1) in calls and ("fetchy.post", 4, 2) in calls and ("fetchy.get", 5, 3) in calls
    impacts = assess_impacts(changes, usages)
    assert any(i["symbol"] == "fetchy.post" and i["level"] == "breaking" for i in impacts)
    assert any(i["line"] == 3 and i["level"] == "breaking" for i in impacts), "get('/a') misses the new required arguments"
    assert js_params("a, b = 2, ...rest")[1]["default"] == "2"


def test_project_tree_reader_skips_vendored_code(tmp_path: Path):
    root = write_tree(tmp_path / "p", {**PROJECT_FILES, "node_modules/x/index.js": "x", ".venv/lib/a.py": "a", "README.md": "hi"})
    paths = {p for p, _ in read_project_tree(root)}
    assert "app/auth.py" in paths and "requirements.txt" in paths
    assert not any(p.startswith(("node_modules", ".venv")) or p == "README.md" for p in paths)


PYJWT_LIKE_V1 = {
    "pyproject.toml": '[project]\nname = "pyjwt-like"\nversion = "1.7.1"\n',
    "jwtl/__init__.py": "from .api_jwt import decode\n",
    "jwtl/api_jwt.py": """
class PyJWT:
    def decode(self, jwt, key="", verify=True, algorithms=None, options=None):
        return self._decode_complete(jwt, key, verify=verify, algorithms=algorithms)

    def _decode_complete(self, jwt, key, verify=True, algorithms=None):
        return {}


_obj = PyJWT()
decode = _obj.decode
""",
}

PYJWT_LIKE_V2 = {
    "pyproject.toml": '[project]\nname = "pyjwt-like"\nversion = "2.0.0"\n',
    "jwtl/__init__.py": "from .api_jwt import decode\n",
    "jwtl/api_jws.py": """
class DecodeError(Exception):
    pass


class PyJWS:
    def decode_complete(self, jwt, key="", algorithms=None, options=None, detached_payload=None):
        verify_signature = True
        if verify_signature and not algorithms:
            raise DecodeError('It is required that you pass in a value for the "algorithms" argument when calling decode().')
        if jwt.startswith("x"):
            if detached_payload is None:
                raise DecodeError("detached payload required for b64=false tokens")
        return {}


_jws_global_obj = PyJWS()
decode_complete = _jws_global_obj.decode_complete
""",
    "jwtl/api_jwt.py": """
import warnings

from . import api_jws


class PyJWT:
    def decode(self, jwt, key="", algorithms=None, options=None, verify=None, audience=None):
        return self._decode_complete(jwt, key, algorithms, options, verify=verify, audience=audience)

    def _decode_complete(self, jwt, key="", algorithms=None, options=None, verify=None, audience=None):
        if verify is not None:
            warnings.warn("The `verify` argument to `decode` does nothing in 2.0 and newer.", category=DeprecationWarning)
        decoded = api_jws.decode_complete(jwt, key=key, algorithms=algorithms, options=options)
        self._validate_aud(decoded, audience)
        return decoded

    def _validate_aud(self, payload, audience):
        if audience is None:
            if "aud" not in payload:
                return
            raise ValueError("Invalid audience")


_obj = PyJWT()
decode = _obj.decode
""",
}


def test_contracts_hidden_in_helpers_are_detected(tmp_path: Path):
    old = extract_surface(write_tree(tmp_path / "a", PYJWT_LIKE_V1))
    new = extract_surface(write_tree(tmp_path / "b", PYJWT_LIKE_V2))
    rec = new["symbols"]["jwtl.decode"]
    assert "verify" in rec["deprecated_params"] and "does nothing" in rec["deprecated_params"]["verify"]
    assert "algorithms" in rec["required_params"] and "required" in rec["required_params"]["algorithms"]
    # conditional raises (only when the token has a claim / a header) are not requirements
    assert "audience" not in rec["required_params"]
    assert "detached_payload" not in new["symbols"]["jwtl.api_jws.PyJWS.decode_complete"].get("required_params", {})
    changes = diff_surfaces(old, new)
    contract = next(c for c in changes if c["kind"] == "contract")
    assert contract["severity"] == "breaking" and "jwtl.decode" in contract["names"]

    code = (
        "import jwt_unused\nimport jwtl\n\n"
        "def read(token, key):\n    return jwtl.decode(token, key, verify=False)\n\n"
        "def strict(token, key):\n    claims = jwtl.decode(token, key, algorithms=['HS256'])\n    return claims.get('role')\n"
    )
    usages = python_usages("app/auth.py", code, {"jwtl"})
    assert not any(u["symbol"].endswith(".get") for u in usages), "a function result is not a class instance"
    impacts = assess_impacts(changes, usages)
    read = [i for i in impacts if i["line"] == 5]
    assert read and read[0]["level"] == "breaking"
    assert "upstream now raises" in read[0]["explanation"] and "deprecated" in read[0]["explanation"]
    strict = [i for i in impacts if i["line"] == 8]
    assert all(i["level"] in ("low",) for i in strict), strict
