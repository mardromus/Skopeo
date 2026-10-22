"""Where does the user's project use a library?

Python is analysed with the AST: imports and aliases (``import jwt as j``, ``from jwt import
decode as d``), calls with their positional and keyword arguments, attribute references
(``except jwt.InvalidTokenError``) and simple instance tracking (``client = lib.Client()`` then
``client.send(...)``). JavaScript / TypeScript use import / require patterns and member calls.
"""

from __future__ import annotations

import ast
import json
import re
import tomllib
from collections.abc import Iterable
from typing import Any

from app.tools.manifests import _python_requirement, is_requirements_file, normalize_name
from app.watch.surface import matching_paren, split_top_level

PY_SUFFIXES = (".py",)
JS_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
MAX_USAGES = 2000


def _dotted(expr: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    if isinstance(expr, ast.Name):
        parts.append(expr.id)
        return ".".join(reversed(parts))
    return None


def python_usages(path: str, text: str, roots: set[str]) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(text, filename=path)
    except (SyntaxError, ValueError):
        return []
    lines = text.splitlines()
    aliases: dict[str, str] = {}
    usages: list[dict[str, Any]] = []

    def snippet(line: int) -> str:
        return lines[line - 1].strip()[:200] if 0 < line <= len(lines) else ""

    def record(kind: str, symbol: str, node: ast.AST, **extra: Any) -> None:
        line = getattr(node, "lineno", 0)
        usages.append({"file": path, "line": line, "kind": kind, "symbol": symbol, "snippet": snippet(line), **extra})

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in roots:
                    aliases[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
                    record("import", a.name, node)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.split(".")[0] in roots:
            for a in node.names:
                if a.name == "*":
                    record("import", f"{node.module}.*", node)
                    continue
                aliases[a.asname or a.name] = f"{node.module}.{a.name}"
                record("import", f"{node.module}.{a.name}", node)
    if not aliases:
        return usages

    # x = lib.Client(...)  ->  x.method(...) resolves to lib.Client.method
    instances: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            callee = _dotted(node.value.func)
            resolved = _resolve(callee, aliases, {}) if callee else None
            # only calls to classes create instances (``client = lib.Client()``), not ``claims = jwt.decode(...)``
            if resolved and resolved.split(".")[0] in roots and resolved.rsplit(".", 1)[-1][:1].isupper():
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        instances[t.id] = resolved

    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    consumed: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            dotted = _dotted(node.func)
            resolved = _resolve(dotted, aliases, instances) if dotted else None
            if resolved and resolved.split(".")[0] in roots:
                consumed.add(id(node.func))
                record(
                    "call",
                    resolved,
                    node,
                    positional=sum(1 for a in node.args if not isinstance(a, ast.Starred)),
                    keywords=[k.arg for k in node.keywords if k.arg],
                    star_args=any(isinstance(a, ast.Starred) for a in node.args),
                    star_kwargs=any(k.arg is None for k in node.keywords),
                )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute | ast.Name) or id(node) in consumed:
            continue
        if not isinstance(getattr(node, "ctx", None), ast.Load) or isinstance(parents.get(id(node)), ast.Attribute):
            continue
        dotted = _dotted(node)
        if not dotted or dotted.split(".")[0] not in aliases:
            continue
        resolved = _resolve(dotted, aliases, instances)
        if resolved and resolved.split(".")[0] in roots and resolved not in roots:
            record("reference", resolved, node)
    return usages[:MAX_USAGES]


def _resolve(dotted: str, aliases: dict[str, str], instances: dict[str, str]) -> str | None:
    head, _, rest = dotted.partition(".")
    if head in aliases:
        return aliases[head] + ("." + rest if rest else "")
    if head in instances and rest:
        return f"{instances[head]}.{rest}"
    return None


_JS_IMPORT_RE = re.compile(
    r"import\s+(?:type\s+)?(?:([A-Za-z_$][\w$]*)\s*,?\s*)?(?:\{([^}]*)\}\s*)?(?:\*\s*as\s+([A-Za-z_$][\w$]*)\s*)?from\s*['\"]([^'\"]+)['\"]"
)
_JS_REQUIRE_RE = re.compile(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*require\(\s*['\"]([^'\"]+)['\"]\s*\)")
_JS_REQUIRE_DESTRUCTURE_RE = re.compile(r"(?:const|let|var)\s*\{([^}]*)\}\s*=\s*require\(\s*['\"]([^'\"]+)['\"]\s*\)")


def js_usages(path: str, text: str, packages: set[str]) -> list[dict[str, Any]]:
    def matches(spec: str) -> str | None:
        for p in packages:
            if spec == p or spec.startswith(p + "/"):
                return p
        return None

    def line_of(idx: int) -> int:
        return text.count("\n", 0, idx) + 1

    lines = text.splitlines()
    usages: list[dict[str, Any]] = []
    namespaces: dict[str, str] = {}
    named: dict[str, str] = {}

    def record(kind: str, symbol: str, idx: int, **extra: Any) -> None:
        ln = line_of(idx)
        usages.append(
            {
                "file": path,
                "line": ln,
                "kind": kind,
                "symbol": symbol,
                "snippet": lines[ln - 1].strip()[:200] if ln <= len(lines) else "",
                **extra,
            }
        )

    for m in _JS_IMPORT_RE.finditer(text):
        pkg = matches(m.group(4))
        if not pkg:
            continue
        default, braces, star = m.group(1), m.group(2), m.group(3)
        if default:
            named[default] = f"{pkg}.default"
            namespaces.setdefault(default, pkg)
        if star:
            namespaces[star] = pkg
        for part in (braces or "").split(","):
            part = part.strip().removeprefix("type ").strip()
            if not part:
                continue
            original, _, local = part.partition(" as ")
            named[(local or original).strip()] = f"{pkg}.{original.strip()}"
            record("import", f"{pkg}.{original.strip()}", m.start())
        if default or star:
            record("import", pkg, m.start())
    for m in _JS_REQUIRE_RE.finditer(text):
        pkg = matches(m.group(2))
        if pkg:
            namespaces[m.group(1)] = pkg
            named[m.group(1)] = f"{pkg}.default"
            record("import", pkg, m.start())
    for m in _JS_REQUIRE_DESTRUCTURE_RE.finditer(text):
        pkg = matches(m.group(2))
        if not pkg:
            continue
        for part in m.group(1).split(","):
            original, _, local = part.partition(":")
            if original.strip():
                named[(local or original).strip()] = f"{pkg}.{original.strip()}"
                record("import", f"{pkg}.{original.strip()}", m.start())

    def args_at(open_idx: int) -> int | None:
        close = matching_paren(text, open_idx)
        return len(split_top_level(text[open_idx + 1 : close])) if close != -1 else None

    for local, pkg in namespaces.items():
        for m in re.finditer(rf"(?<![\w$.]){re.escape(local)}\.([A-Za-z_$][\w$]*)\s*(\()?", text):
            if m.group(2):
                record(
                    "call",
                    f"{pkg}.{m.group(1)}",
                    m.start(),
                    positional=args_at(m.end() - 1),
                    keywords=[],
                    star_args=False,
                    star_kwargs=False,
                )
            else:
                record("reference", f"{pkg}.{m.group(1)}", m.start())
    for local, symbol in named.items():
        for m in re.finditer(rf"(?<![\w$.]){re.escape(local)}\s*\(", text):
            if text[max(0, m.start() - 9) : m.start()].rstrip().endswith(("function", "import")):
                continue
            record("call", symbol, m.start(), positional=args_at(m.end() - 1), keywords=[], star_args=False, star_kwargs=False)
    return usages[:MAX_USAGES]


def find_usages(files: Iterable[tuple[str, str]], *, ecosystem: str, import_names: list[str]) -> list[dict[str, Any]]:
    roots = set(import_names)
    out: list[dict[str, Any]] = []
    for path, text in files:
        if ecosystem == "npm" and path.endswith(JS_SUFFIXES) and not path.endswith(".d.ts"):
            out.extend(js_usages(path, text, roots))
        elif ecosystem != "npm" and path.endswith(PY_SUFFIXES):
            out.extend(python_usages(path, text, roots))
        if len(out) >= MAX_USAGES:
            break
    return out[:MAX_USAGES]


def _floor(spec: str, exact: str | None) -> str | None:
    """Lowest version a spec allows: the exact pin, or the bound of >=, ~= or ^."""
    if exact:
        return exact
    m = re.search(r"(?:>=|~=|\^|>)\s*([0-9][^,;\s]*)", spec)
    return m.group(1) if m else None


def find_pinned_version(files: Iterable[tuple[str, str]], package_name: str | None, ecosystem: str) -> dict[str, Any] | None:
    """The version (or spec) of ``package_name`` that the project's manifests ask for."""
    if not package_name:
        return None
    wanted = normalize_name(package_name, "PyPI" if ecosystem != "npm" else "npm")
    for path, text in files:
        name = path.rsplit("/", 1)[-1]
        if ecosystem == "npm" and name == "package.json":
            try:
                pkg = json.loads(text)
            except json.JSONDecodeError:
                continue
            for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                spec = (pkg.get(section) or {}).get(package_name) if isinstance(pkg, dict) else None
                if isinstance(spec, str):
                    exact = re.match(r"^[=v]?(\d+\.\d+\.\d+(?:[-+][\w.-]+)?)$", spec.strip())
                    floor = re.match(r"^[\^~>=]*\s*v?(\d+\.\d+\.\d+)", spec.strip())
                    return {
                        "manifest": path,
                        "spec": spec,
                        "version": exact.group(1) if exact else None,
                        "floor": floor.group(1) if floor else None,
                    }
        elif ecosystem != "npm" and is_requirements_file(path):
            for i, raw in enumerate(text.splitlines(), 1):
                dep = _python_requirement(raw, path, i)
                if dep and dep.name == wanted:
                    return {"manifest": path, "spec": dep.spec, "version": dep.version, "floor": _floor(dep.spec, dep.version), "line": i}
        elif ecosystem != "npm" and name == "pyproject.toml":
            try:
                data = tomllib.loads(text)
            except tomllib.TOMLDecodeError:
                continue
            deps = list((data.get("project") or {}).get("dependencies") or [])
            for group in ((data.get("project") or {}).get("optional-dependencies") or {}).values():
                deps += list(group or [])
            for raw in deps:
                dep = _python_requirement(str(raw), path, None)
                if dep and dep.name == wanted:
                    return {"manifest": path, "spec": dep.spec, "version": dep.version, "floor": _floor(dep.spec, dep.version)}
            poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
            for key, spec in poetry.items():
                if normalize_name(key, "PyPI") == wanted:
                    value = spec if isinstance(spec, str) else (spec or {}).get("version", "*")
                    exact = re.match(r"^=?=?\s*(\d[\w.]*)$", str(value))
                    floor = re.search(r"(\d+(?:\.\d+)+)", str(value))
                    return {
                        "manifest": path,
                        "spec": str(value),
                        "version": exact.group(1) if exact else None,
                        "floor": floor.group(1) if floor else None,
                    }
    return None
