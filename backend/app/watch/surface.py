"""Public API surface of a library checkout: what a downstream project can call.

The surface is a JSON-serialisable snapshot, stored after every check so the next check can diff
against it without keeping the old checkout:

* **Python** (AST): public functions, classes, methods and their parameters (kind and default),
  deprecation markers, a hash of each body (to spot behaviour changes), and re-exports such as
  ``from .api_jwt import decode`` or ``decode = _jwt_global_obj.decode`` so ``jwt.decode`` resolves
  to the method that actually runs.
* **JavaScript / TypeScript** (patterns): exported functions, arrow functions, classes and
  CommonJS exports with their parameter lists and ``@deprecated`` JSDoc tags.
* Package metadata (distribution name, version, import names) and the changelog text.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import tomllib
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MAX_FILES = 3000
MAX_FILE_BYTES = 400_000
MAX_SYMBOLS = 8000
MAX_CHANGELOG_CHARS = 120_000

EXCLUDED_DIRS = {
    ".git",
    ".github",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "site-packages",
    "tests",
    "test",
    "testing",
    "docs",
    "doc",
    "examples",
    "example",
    "samples",
    "benchmarks",
    "bench",
    "scripts",
    "fixtures",
    "e2e",
    "build",
    "dist",
    "coverage",
    "vendor",
    "third_party",
}
NON_PACKAGE_MODULES = {"setup", "conftest", "noxfile", "tasks", "fabfile", "manage", "docs", "test", "tests"}
CHANGELOG_RE = re.compile(r"^(CHANGELOG|CHANGES|HISTORY|NEWS|RELEASE[_-]?NOTES)(\.[A-Za-z]+)?$", re.IGNORECASE)
DEPRECATION_WARNINGS = {"DeprecationWarning", "PendingDeprecationWarning", "FutureWarning"}
JS_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".cjs", ".jsx")


# ----------------------------------------------------------------------------- utils
def _walk(root: Path, suffixes: tuple[str, ...], extra_excluded: set[str] | None = None) -> list[str]:
    out: list[str] = []
    excluded = EXCLUDED_DIRS | (extra_excluded or set())
    stack = [root]
    while stack and len(out) < MAX_FILES:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name not in excluded and not entry.name.startswith("."):
                    stack.append(entry)
            elif entry.name.endswith(suffixes) and entry.stat().st_size <= MAX_FILE_BYTES:
                out.append(entry.relative_to(root).as_posix())
    return sorted(out)


def _read(root: Path, rel: str) -> str | None:
    try:
        return (root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode(), usedforsecurity=False).hexdigest()[:16]


# ------------------------------------------------------------------------ metadata
def package_metadata(root: Path) -> dict[str, Any]:
    meta: dict[str, Any] = {"python_name": None, "python_version": None, "npm_name": None, "npm_version": None}
    pyproject = _read(root, "pyproject.toml") if (root / "pyproject.toml").is_file() else None
    if pyproject:
        try:
            data = tomllib.loads(pyproject)
            project = data.get("project") or {}
            poetry = (data.get("tool") or {}).get("poetry") or {}
            meta["python_name"] = project.get("name") or poetry.get("name")
            version = project.get("version") or poetry.get("version")
            meta["python_version"] = version if isinstance(version, str) else None
        except tomllib.TOMLDecodeError:
            pass
    if not meta["python_name"] and (root / "setup.cfg").is_file():
        text = _read(root, "setup.cfg") or ""
        m = re.search(r"^\s*name\s*=\s*([A-Za-z0-9._-]+)\s*$", text, re.MULTILINE)
        meta["python_name"] = m.group(1) if m else None
        v = re.search(r"^\s*version\s*=\s*([0-9][^\s]*)\s*$", text, re.MULTILINE)
        meta["python_version"] = meta["python_version"] or (v.group(1) if v else None)
    if not meta["python_name"] and (root / "setup.py").is_file():
        text = _read(root, "setup.py") or ""
        m = re.search(r"\bname\s*=\s*['\"]([A-Za-z0-9._-]+)['\"]", text)
        meta["python_name"] = m.group(1) if m else None
        v = re.search(r"\bversion\s*=\s*['\"]([0-9][^'\"]*)['\"]", text)
        meta["python_version"] = meta["python_version"] or (v.group(1) if v else None)
    if (root / "package.json").is_file():
        try:
            pkg = json.loads(_read(root, "package.json") or "{}")
            if isinstance(pkg, dict):
                meta["npm_name"] = pkg.get("name") if isinstance(pkg.get("name"), str) else None
                meta["npm_version"] = pkg.get("version") if isinstance(pkg.get("version"), str) else None
                meta["npm_types"] = pkg.get("types") or pkg.get("typings")
        except json.JSONDecodeError:
            pass
    return meta


def find_changelog(root: Path) -> dict[str, Any] | None:
    candidates = [p for p in sorted(root.iterdir()) if p.is_file() and CHANGELOG_RE.match(p.name)] if root.is_dir() else []
    for sub in ("docs", "doc"):
        d = root / sub
        if d.is_dir():
            candidates += [p for p in sorted(d.iterdir()) if p.is_file() and CHANGELOG_RE.match(p.name)]
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        return {"file": path.relative_to(root).as_posix(), "text": text[:MAX_CHANGELOG_CHARS]}
    return None


# -------------------------------------------------------------------------- python
def detect_python_packages(root: Path) -> dict[str, str]:
    """{import name: directory (or module file) relative to root}."""
    found: dict[str, str] = {}
    for base in (root, root / "src", root / "lib"):
        if not base.is_dir():
            continue
        for entry in sorted(base.iterdir()):
            if entry.is_symlink() or entry.name.startswith((".", "_")) or entry.name in EXCLUDED_DIRS:
                continue
            if entry.is_dir() and (entry / "__init__.py").is_file() and entry.name.isidentifier():
                found.setdefault(entry.name, entry.relative_to(root).as_posix())
        if found:
            return found
    for entry in sorted(root.glob("*.py")):  # single-module distributions (e.g. six.py)
        if entry.stem.isidentifier() and entry.stem not in NON_PACKAGE_MODULES and not entry.stem.startswith("_"):
            found[entry.stem] = entry.relative_to(root).as_posix()
    return found


def _params(fn: ast.FunctionDef | ast.AsyncFunctionDef, drop_first: bool) -> list[dict[str, Any]]:
    a = fn.args
    out: list[dict[str, Any]] = []
    positional = [(p, "posonly") for p in a.posonlyargs] + [(p, "pos") for p in a.args]
    defaults = [None] * (len(positional) - len(a.defaults)) + list(a.defaults)
    for (p, kind), d in zip(positional, defaults, strict=True):
        out.append({"name": p.arg, "kind": kind, "default": _unparse(d)})
    if a.vararg:
        out.append({"name": a.vararg.arg, "kind": "var", "default": None})
    for p, d in zip(a.kwonlyargs, a.kw_defaults, strict=True):
        out.append({"name": p.arg, "kind": "kwonly", "default": _unparse(d)})
    if a.kwarg:
        out.append({"name": a.kwarg.arg, "kind": "varkw", "default": None})
    if drop_first and out and out[0]["kind"] in ("posonly", "pos"):
        out = out[1:]
    return out


def _unparse(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)[:80]
    except (ValueError, TypeError, AttributeError):  # pragma: no cover - malformed AST
        return "…"


def _decorator_names(fn: ast.AST) -> list[str]:
    names = []
    for d in getattr(fn, "decorator_list", []):
        target = d.func if isinstance(d, ast.Call) else d
        names.append(_unparse(target) or "")
    return names


def _is_deprecated(node: ast.AST) -> bool:
    if any("deprecat" in n.lower() for n in _decorator_names(node)):
        return True
    doc = ast.get_docstring(node) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) else None
    if doc and (".. deprecated::" in doc or doc.lstrip().lower().startswith("deprecated")):
        return True
    body = node.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) else []
    for sub in (n for stmt in body for n in ast.walk(stmt)):
        if isinstance(sub, ast.Call) and (_unparse(sub.func) or "").split(".")[-1] == "warn":
            category = sub.args[1] if len(sub.args) > 1 else next((k.value for k in sub.keywords if k.arg == "category"), None)
            if category is not None and (_unparse(category) or "").split(".")[-1] in DEPRECATION_WARNINGS:
                return True
    return False


def _body_hash(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]  # docstring edits are not behaviour changes
    return _hash("".join(ast.dump(s) for s in body))


def _message(node: ast.AST | None) -> str:
    """Readable text of a warning / exception message argument."""
    if node is None:
        return ""
    if isinstance(node, ast.Call):  # raise SomeError("...")
        node = node.args[0] if node.args else None
        if node is None:
            return ""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value[:300]
    if isinstance(node, ast.BinOp | ast.JoinedStr):
        parts = [v.value for v in ast.walk(node) if isinstance(v, ast.Constant) and isinstance(v.value, str)]
        return "".join(parts)[:300]
    return (_unparse(node) or "")[:300]


def _negated_params(test: ast.AST, params: set[str]) -> set[str]:
    """Parameters a condition treats as missing: ``not p`` or ``p is None``."""
    out = set()
    for n in ast.walk(test):
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not) and isinstance(n.operand, ast.Name) and n.operand.id in params:
            out.add(n.operand.id)
        elif (
            isinstance(n, ast.Compare)
            and isinstance(n.left, ast.Name)
            and n.left.id in params
            and len(n.ops) == 1
            and isinstance(n.ops[0], ast.Is)
            and isinstance(n.comparators[0], ast.Constant)
            and n.comparators[0].value is None
        ):
            out.add(n.left.id)
    return out


_FLOW = (ast.If, ast.Return, ast.Try, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Continue, ast.Break)


def _unconditional_raise(body: list[ast.stmt]) -> ast.Raise | None:
    """The raise an ``if`` body always reaches (no early return or nested condition before it)."""
    for stmt in body:
        if isinstance(stmt, ast.Raise):
            return stmt
        if isinstance(stmt, _FLOW):
            return None
    return None


def _attribute_types(cls_node: ast.ClassDef, module: str) -> dict[str, str]:
    """``self._jws = PyJWS(...)`` in ``__init__`` -> {"_jws": "<module>.PyJWS"} (resolved through imports later)."""
    out: dict[str, str] = {}
    for item in cls_node.body:
        if not (isinstance(item, ast.FunctionDef) and item.name == "__init__"):
            continue
        for node in ast.walk(item):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                callee = _unparse(node.value.func) or ""
                if not re.fullmatch(r"[A-Za-z_][\w.]*", callee):
                    continue
                for t in node.targets:
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                        out[t.attr] = f"{module}.{callee}"
    return out


def _contracts(
    fn: ast.FunctionDef | ast.AsyncFunctionDef, module: str, cls: str | None, attr_types: dict[str, str] | None = None
) -> dict[str, Any]:
    """Parameter rules that live in the body rather than the signature.

    Only ``if`` statements at the top level of the function count, so a rule that depends on
    something else (the token's claims, a header) is not mistaken for a requirement:

    * deprecated: ``if verify is not None: warnings.warn("...", DeprecationWarning)``
    * required in practice: ``if not algorithms: raise DecodeError("... required ...")``
    * delegation: ``self.decode_complete(jwt, key, verify=verify)`` or ``api_jws.decode_complete(...)``
      (the callee's rules apply to the arguments forwarded to it; resolved package-wide later)
    """
    a = fn.args
    params = {p.arg for p in [*a.posonlyargs, *a.args, *a.kwonlyargs]} - {"self", "cls"}
    deprecated: dict[str, str] = {}
    required: dict[str, str] = {}
    delegates: list[dict[str, Any]] = []
    for node in fn.body:
        if not isinstance(node, ast.If):
            continue
        mentioned = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name) and n.id in params}
        if not mentioned:
            continue
        missing = _negated_params(node.test, params)
        for sub in (x for stmt in node.body for x in ast.walk(stmt)):
            if isinstance(sub, ast.Call) and (_unparse(sub.func) or "").split(".")[-1] == "warn":
                category = sub.args[1] if len(sub.args) > 1 else next((k.value for k in sub.keywords if k.arg == "category"), None)
                if category is not None and (_unparse(category) or "").split(".")[-1] in DEPRECATION_WARNINGS:
                    for p in mentioned - missing:
                        deprecated.setdefault(p, _message(sub.args[0] if sub.args else None))
        raise_stmt = _unconditional_raise(node.body)
        if raise_stmt is not None:
            for p in missing:
                required.setdefault(p, _message(raise_stmt.exc))
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in ("self", "cls") and cls:
            candidate = f"{module}.{cls}.{func.attr}"
        elif (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Attribute)
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "self"
            and func.value.attr in (attr_types or {})
        ):
            candidate = f"{(attr_types or {})[func.value.attr]}.{func.attr}"  # self._jws.decode_complete(...)
        elif isinstance(func, ast.Name):
            candidate = f"{module}.{func.id}"
        elif isinstance(func, ast.Attribute) and (dotted := _unparse(func)) and re.fullmatch(r"[A-Za-z_][\w.]*", dotted):
            candidate = f"{module}.{dotted}"
        else:
            continue
        kw = {k.arg: k.value.id for k in node.keywords if k.arg and isinstance(k.value, ast.Name) and k.value.id in params}
        pos = {i: v.id for i, v in enumerate(node.args) if isinstance(v, ast.Name) and v.id in params}
        if kw or pos:
            delegates.append({"target": candidate, "kw": kw, "pos": pos})
    return {"deprecated": deprecated, "required": required, "delegates": delegates}


def _inherit_contracts(registry: dict[str, dict[str, Any]], resolve) -> None:
    """Propagate callee rules to callers that forward the same argument (three rounds covers helper chains)."""
    for _ in range(3):
        for rec in registry.values():
            for d in rec["contracts"]["delegates"]:
                target = resolve(d["target"])
                callee = registry.get(target) if target else None
                if callee is None or callee is rec:
                    continue
                callee_pos = [p["name"] for p in callee["params"] if p["kind"] in ("posonly", "pos")]
                mapping = dict(d["kw"]) | {callee_pos[i]: ours for i, ours in d["pos"].items() if i < len(callee_pos)}
                for callee_param, ours in mapping.items():
                    if callee_param in callee["contracts"]["deprecated"]:
                        rec["contracts"]["deprecated"].setdefault(ours, callee["contracts"]["deprecated"][callee_param])
                    if callee_param in callee["contracts"]["required"]:
                        rec["contracts"]["required"].setdefault(ours, callee["contracts"]["required"][callee_param])


def _contract_fields(contracts: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if contracts["deprecated"]:
        out["deprecated_params"] = dict(contracts["deprecated"])
    if contracts["required"]:
        out["required_params"] = dict(contracts["required"])
    return out


def _module_name(rel: str, package_dir: str, import_name: str) -> str:
    if rel.endswith(".py") and "/" not in package_dir and package_dir.endswith(".py"):
        return import_name
    inner = rel[len(package_dir) :].lstrip("/")
    parts = inner[:-3].split("/") if inner.endswith(".py") else inner.split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join([import_name, *[p for p in parts if p]])


def _resolve_relative(module: str, is_package: bool, level: int, target: str | None) -> str:
    base = module.split(".")
    if not is_package:
        base = base[:-1]
    if level > 1:
        base = base[: len(base) - (level - 1)]
    return ".".join([*base, *([target] if target else [])])


def python_surface(root: Path, import_names: list[str] | None = None) -> dict[str, Any]:
    packages = detect_python_packages(root)
    if import_names:
        packages = {k: v for k, v in packages.items() if k in import_names} or {n: n for n in import_names if (root / n).is_dir()}
    symbols: dict[str, dict[str, Any]] = {}
    aliases: dict[str, str] = {}  # public name -> target qualname
    all_aliases: dict[str, str] = {}  # every name binding, private ones included (for delegation)
    registry: dict[str, dict[str, Any]] = {}  # every function and method, private ones included
    star_imports: list[tuple[str, str]] = []  # (module, source module)
    modules: list[str] = []
    files_parsed = 0
    for import_name, package_dir in packages.items():
        rels = [package_dir] if package_dir.endswith(".py") else [package_dir + "/" + r for r in _walk(root / package_dir, (".py",))]
        for rel in rels:
            text = _read(root, rel)
            if text is None:
                continue
            try:
                tree = ast.parse(text, filename=rel)
            except (SyntaxError, ValueError):
                continue
            files_parsed += 1
            module = _module_name(rel, package_dir, import_name)
            is_package = rel.endswith("__init__.py")
            private_module = any(p.startswith("_") for p in module.split(".")[1:])
            modules.append(module)
            instances: dict[str, str] = {}
            for node in tree.body:
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    q = f"{module}.{node.name}"
                    params = _params(node, drop_first=False)
                    registry[q] = {"params": params, "contracts": _contracts(node, module, None)}
                    if not node.name.startswith("_"):
                        symbols[q] = {
                            "kind": "function",
                            "file": rel,
                            "line": node.lineno,
                            "params": params,
                            "deprecated": _is_deprecated(node),
                            "body": _body_hash(node),
                            "private_module": private_module,
                        }
                elif isinstance(node, ast.ClassDef):
                    q = f"{module}.{node.name}"
                    public_class = not node.name.startswith("_")
                    attr_types = _attribute_types(node, module)
                    init = next(
                        (n for n in node.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == "__init__"), None
                    )
                    if public_class:
                        symbols[q] = {
                            "kind": "class",
                            "file": rel,
                            "line": node.lineno,
                            "params": _params(init, drop_first=True) if init else None,
                            "deprecated": _is_deprecated(node) or (init is not None and _is_deprecated(init)),
                            "body": None,
                            "bases": [_unparse(b) for b in node.bases][:5],
                            "methods": [],
                            "private_module": private_module,
                        }
                    for item in node.body:
                        if not isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                            continue
                        static = "staticmethod" in _decorator_names(item)
                        mq = f"{q}.{item.name}"
                        params = _params(item, drop_first=not static)
                        registry[mq] = {"params": params, "contracts": _contracts(item, module, node.name, attr_types)}
                        if not public_class or (item.name.startswith("_") and item.name != "__call__"):
                            continue
                        symbols[mq] = {
                            "kind": "method",
                            "file": rel,
                            "line": item.lineno,
                            "params": params,
                            "deprecated": _is_deprecated(item),
                            "body": _body_hash(item),
                            "private_module": private_module,
                        }
                        symbols[q]["methods"].append(item.name)
                elif isinstance(node, ast.ImportFrom) and (node.level > 0 or (node.module or "").split(".")[0] == import_name):
                    source = _resolve_relative(module, is_package, node.level, node.module) if node.level else str(node.module)
                    for a in node.names:
                        if a.name == "*":
                            star_imports.append((module, source))
                            continue
                        all_aliases[f"{module}.{a.asname or a.name}"] = f"{source}.{a.name}"
                        if not (a.asname or a.name).startswith("_"):
                            aliases[f"{module}.{a.asname or a.name}"] = f"{source}.{a.name}"
                elif isinstance(node, ast.Import):
                    for a in node.names:
                        if a.name.split(".")[0] == import_name and a.asname:
                            all_aliases[f"{module}.{a.asname}"] = a.name
                elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    name, value = node.targets[0].id, node.value
                    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                        instances[name] = f"{module}.{value.func.id}"  # e.g. _jwt_global_obj = PyJWT()
                    target = None
                    if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name) and value.value.id in instances:
                        target = f"{instances[value.value.id]}.{value.attr}"  # decode = _jwt_global_obj.decode
                    elif isinstance(value, ast.Name) and not value.id.startswith("__"):
                        target = f"{module}.{value.id}"
                    elif isinstance(value, ast.Attribute):
                        dotted = _unparse(value) or ""
                        if dotted.split(".")[0] == import_name:
                            target = dotted
                    if target:
                        all_aliases[f"{module}.{name}"] = target
                        if not name.startswith("_"):
                            aliases[f"{module}.{name}"] = target

    # `from .x import *` re-exports every public name of x
    for module, source in star_imports:
        prefix = source + "."
        for q in list(symbols):
            rest = q[len(prefix) :] if q.startswith(prefix) else None
            if rest and "." not in rest:
                aliases.setdefault(f"{module}.{rest}", q)
                all_aliases.setdefault(f"{module}.{rest}", q)

    def resolve(q: str, depth: int = 0) -> str | None:
        if q in registry:
            return q
        if depth > 8:
            return None
        if q in all_aliases:
            return resolve(all_aliases[q], depth + 1)
        parts = q.split(".")
        for i in range(len(parts) - 1, 0, -1):
            head = ".".join(parts[:i])
            if head in all_aliases:
                return resolve(all_aliases[head] + "." + ".".join(parts[i:]), depth + 1)
        return None

    _inherit_contracts(registry, resolve)
    for q, rec in symbols.items():
        if q in registry:
            rec.update(_contract_fields(registry[q]["contracts"]))

    public = _resolve_public(symbols, aliases)
    return {"symbols": public, "modules": sorted(set(modules)), "import_names": sorted(packages), "files_parsed": files_parsed}


def _resolve_public(symbols: dict[str, dict[str, Any]], aliases: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Every name a user can import, mapped to the record that actually runs (``target``)."""

    def resolve(name: str, hops: int = 0) -> str | None:
        if name in symbols:
            return name
        if hops > 6 or name not in aliases:
            return None
        return resolve(aliases[name], hops + 1)

    public: dict[str, dict[str, Any]] = {}
    for q, rec in symbols.items():
        if not rec.get("private_module"):
            public[q] = {**rec, "target": q}
    for alias in sorted(aliases):
        if any(p.startswith("_") for p in alias.split(".")[1:]):
            continue
        target = resolve(alias)
        if target is None:
            continue
        rec = symbols[target]
        public.setdefault(alias, {**rec, "target": target})
        if rec["kind"] == "class":  # jwt.PyJWT.decode -> jwt.api_jwt.PyJWT.decode
            for m in rec.get("methods") or []:
                mq = f"{target}.{m}"
                if mq in symbols:
                    public.setdefault(f"{alias}.{m}", {**symbols[mq], "target": mq})
    for rec in public.values():
        rec.pop("private_module", None)
    if len(public) > MAX_SYMBOLS:  # keep the shallowest names: those are the ones people import
        keep = sorted(public, key=lambda k: (k.count("."), k))[:MAX_SYMBOLS]
        public = {k: public[k] for k in keep}
    return public


# --------------------------------------------------------------------- javascript
_JS_FUNC_RE = re.compile(r"export\s+(?:declare\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*(?:<[^>()]*>)?\s*\(")
_JS_CONST_RE = re.compile(
    r"export\s+(?:declare\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=;]{0,200})?=\s*(?:async\s*)?(?:function\s*\*?\s*[\w$]*\s*)?(?:<[^>()]*>)?\s*\("
)
_JS_CLASS_RE = re.compile(r"export\s+(?:declare\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)")
_JS_CJS_RE = re.compile(r"(?:module\.)?exports\.([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\s*\*?\s*[\w$]*\s*)?\(")
_JS_NAMED_RE = re.compile(r"export\s*(?:type\s*)?\{([^}]*)\}")
_JS_MODULE_EXPORTS_RE = re.compile(r"module\.exports\s*=\s*\{([^}]*)\}")
_JSDOC_BEFORE_RE = re.compile(r"/\*\*((?:(?!\*/).)*)\*/\s*$", re.DOTALL)


def matching_paren(text: str, open_idx: int, limit: int = 4000) -> int:
    depth = 0
    quote: str | None = None
    end = min(len(text), open_idx + limit)
    i = open_idx
    while i < end:
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "'\"`":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def split_top_level(text: str) -> list[str]:
    parts, depth, current, quote = [], 0, [], None
    for c in text:
        if quote:
            current.append(c)
            if c == quote:
                quote = None
            continue
        if c in "'\"`":
            quote = c
        elif c in "([{<":
            depth += 1
        elif c in ")]}>":
            depth -= 1
        if c == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(c)
    if "".join(current).strip():
        parts.append("".join(current).strip())
    return [p for p in parts if p]


def js_params(param_text: str) -> list[dict[str, Any]]:
    out = []
    for raw in split_top_level(param_text):
        p = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL).strip()
        if not p or p == "this" or p.startswith("this:"):
            continue
        rest = p.startswith("...")
        name_match = re.match(r"(?:\.\.\.)?\s*([A-Za-z_$][\w$]*)", p)
        name = name_match.group(1) if name_match else ("{…}" if p.startswith("{") else "[…]" if p.startswith("[") else p[:20])
        depth, has_default = 0, False
        for c in p:
            depth += c in "([{<"
            depth -= c in ")]}>"
            if c == "=" and depth == 0:
                has_default = True
                break
        optional = has_default or bool(re.match(r"(?:\.\.\.)?\s*[A-Za-z_$][\w$]*\s*\?", p))
        default = p.split("=", 1)[1].strip()[:80] if has_default else None
        out.append(
            {
                "name": name,
                "kind": "var" if rest else "pos",
                "default": default if default is not None else ("undefined" if optional else None),
            }
        )
    return out


def js_surface(root: Path, package_name: str) -> dict[str, Any]:
    symbols: dict[str, dict[str, Any]] = {}
    files = [f for f in _walk(root, JS_SUFFIXES, {"lib-cov", "types-tests"}) if not re.search(r"\.(test|spec|stories)\.", f)]
    for rel in files:
        text = _read(root, rel)
        if text is None:
            continue
        declaration = rel.endswith(".d.ts")

        def add(
            name: str,
            kind: str,
            start: int,
            params: list[dict[str, Any]] | None,
            rel: str = rel,
            text: str = text,
            declaration: bool = declaration,
        ) -> None:
            key = f"{package_name}.{name}"
            line = text.count("\n", 0, start) + 1
            block = _JSDOC_BEFORE_RE.search(text[max(0, start - 800) : start])
            deprecated = bool(block and "@deprecated" in block.group(1))
            existing = symbols.get(key)
            if existing and (existing["params"] is not None or params is None) and not declaration:
                return
            symbols[key] = {
                "kind": kind,
                "file": rel,
                "line": line,
                "params": params,
                "deprecated": deprecated,
                "body": None,
                "target": key,
            }

        for regex, kind in ((_JS_FUNC_RE, "function"), (_JS_CONST_RE, "function"), (_JS_CJS_RE, "function")):
            for m in regex.finditer(text):
                open_idx = m.end() - 1
                close = matching_paren(text, open_idx)
                params = js_params(text[open_idx + 1 : close]) if close != -1 else None
                add(m.group(1), kind, m.start(), params)
        for m in _JS_CLASS_RE.finditer(text):
            add(m.group(1), "class", m.start(), None)
        for regex in (_JS_NAMED_RE, _JS_MODULE_EXPORTS_RE):
            for m in regex.finditer(text):
                for part in m.group(1).split(","):
                    name = part.strip().split(" as ")[-1].split(":")[0].strip()
                    if re.fullmatch(r"[A-Za-z_$][\w$]*", name or "") and f"{package_name}.{name}" not in symbols:
                        add(name, "export", m.start(), None)
    return {
        "symbols": dict(list(symbols.items())[:MAX_SYMBOLS]),
        "modules": [package_name],
        "import_names": [package_name],
        "files_parsed": len(files),
    }


# ---------------------------------------------------------------------- entrypoint
def extract_surface(root: Path, *, ecosystem: str | None = None, import_names: list[str] | None = None) -> dict[str, Any]:
    meta = package_metadata(root)
    if ecosystem is None:
        if detect_python_packages(root) and (meta["python_name"] or not meta["npm_name"]):
            ecosystem = "PyPI"
        elif meta["npm_name"] or any((root / d).is_dir() for d in ("src", "lib")):
            ecosystem = "npm"
        else:
            ecosystem = "PyPI"
    if ecosystem == "npm":
        name = meta["npm_name"] or (import_names[0] if import_names else root.name)
        api = js_surface(root, name)
        package_name, version = name, meta["npm_version"]
    else:
        api = python_surface(root, import_names)
        package_name, version = meta["python_name"] or (api["import_names"][0] if api["import_names"] else None), meta["python_version"]
        if version is None:
            for imp in api["import_names"]:
                for candidate in (
                    f"{imp}/__init__.py",
                    f"src/{imp}/__init__.py",
                    f"{imp}/__version__.py",
                    f"{imp}/version.py",
                    f"{imp}/_version.py",
                ):
                    text = _read(root, candidate) if (root / candidate).is_file() else None
                    m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", text or "")
                    if m:
                        version = m.group(1)
                        break
                if version:
                    break
    return {
        "schema": SCHEMA_VERSION,
        "ecosystem": ecosystem,
        "package_name": package_name,
        "version": version,
        "import_names": api["import_names"],
        "symbols": api["symbols"],
        "modules": api["modules"],
        "changelog": find_changelog(root),
        "stats": {"files_parsed": api["files_parsed"], "symbols": len(api["symbols"])},
    }
