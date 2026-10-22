"""Compare two API surfaces of the same library and classify every change.

Each change is self-contained (it carries the old and new parameter lists), so the impact
analysis can be re-run later against new project code without the old snapshot.

Change kinds and their default severity:

* ``removed``     breaking   - a public name no longer exists
* ``moved``       breaking   - the name disappeared here but the same definition exists elsewhere
* ``signature``   breaking   - removed / newly required / now keyword-only / fewer positional params
                  behavior   - only defaults changed
                  info       - only new optional parameters
* ``contract``    breaking   - the body now raises when an argument is missing (``if not algorithms: raise``)
                  deprecation - an argument is now deprecated (``if verify is not None: warnings.warn(...)``)
* ``deprecated``  deprecation
* ``behavior``    behavior   - same signature, different implementation
* ``added``       info
* ``module_removed`` breaking
"""

from __future__ import annotations

import re
from typing import Any

SEVERITY_ORDER = {"breaking": 4, "deprecation": 3, "behavior": 2, "info": 1}
CHANGELOG_KEYWORDS = re.compile(
    r"\b(break(ing)?|backwards?[- ]incompatible|remov(e|ed|al)|deprecat\w*|drop(ped)?|renam\w*|no longer|security|cve-\d{4}-\d+|ghsa-|vulnerab\w*|default\w*)\b",
    re.IGNORECASE,
)


def positional(params: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in params if p["kind"] in ("posonly", "pos")]


def compare_params(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> dict[str, Any]:
    old_by = {p["name"]: p for p in old if p["kind"] not in ("var", "varkw")}
    new_by = {p["name"]: p for p in new if p["kind"] not in ("var", "varkw")}
    new_has_var = any(p["kind"] == "var" for p in new)
    new_has_varkw = any(p["kind"] == "varkw" for p in new)
    removed = [n for n in old_by if n not in new_by]
    added_required = [n for n, p in new_by.items() if n not in old_by and p["default"] is None]
    added_optional = [n for n, p in new_by.items() if n not in old_by and p["default"] is not None]
    became_kwonly = [n for n, p in new_by.items() if n in old_by and old_by[n]["kind"] in ("pos", "posonly") and p["kind"] == "kwonly"]
    became_posonly = [n for n, p in new_by.items() if n in old_by and old_by[n]["kind"] in ("pos", "kwonly") and p["kind"] == "posonly"]
    became_required = [n for n, p in new_by.items() if n in old_by and old_by[n]["default"] is not None and p["default"] is None]
    default_changed = [
        {"name": n, "old": old_by[n]["default"], "new": p["default"]}
        for n, p in new_by.items()
        if n in old_by and old_by[n]["default"] is not None and p["default"] is not None and old_by[n]["default"] != p["default"]
    ]
    old_pos = [p["name"] for p in positional(old)]
    new_pos = [p["name"] for p in positional(new)]
    shared = [n for n in old_pos if n in new_pos]
    reordered = shared != [n for n in new_pos if n in old_pos]
    breaking = bool(
        (removed and not new_has_varkw)
        or added_required
        or became_kwonly
        or became_posonly
        or became_required
        or reordered
        or (len(new_pos) < len(old_pos) and not new_has_var)
    )
    return {
        "removed_params": removed,
        "added_required": added_required,
        "added_optional": added_optional,
        "became_kwonly": became_kwonly,
        "became_posonly": became_posonly,
        "became_required": became_required,
        "default_changed": default_changed,
        "reordered": reordered,
        "old_positional": old_pos,
        "new_positional": new_pos,
        "new_has_var": new_has_var,
        "new_has_varkw": new_has_varkw,
        "breaking": breaking,
    }


def format_signature(name: str, params: list[dict[str, Any]] | None) -> str:
    if params is None:
        return name.rsplit(".", 1)[-1]
    out, kwonly_marked = [], False
    for p in params:
        if p["kind"] == "kwonly" and not kwonly_marked and not any(q["kind"] == "var" for q in params):
            out.append("*")
            kwonly_marked = True
        prefix = "*" if p["kind"] == "var" else "**" if p["kind"] == "varkw" else ""
        out.append(
            f"{prefix}{p['name']}"
            + (
                f"={p['default']}"
                if p["default"] is not None and p["default"] != "undefined"
                else "?"
                if p["default"] == "undefined"
                else ""
            )
        )
    return f"{name.rsplit('.', 1)[-1]}({', '.join(out)})"


def _describe(d: dict[str, Any]) -> str:
    bits = []
    if d["removed_params"]:
        bits.append("removed " + ", ".join(f"`{n}`" for n in d["removed_params"]))
    if d["added_required"]:
        bits.append("new required " + ", ".join(f"`{n}`" for n in d["added_required"]))
    if d["became_required"]:
        bits.append("now required " + ", ".join(f"`{n}`" for n in d["became_required"]))
    if d["became_kwonly"]:
        bits.append("keyword-only now " + ", ".join(f"`{n}`" for n in d["became_kwonly"]))
    if d["became_posonly"]:
        bits.append("positional-only now " + ", ".join(f"`{n}`" for n in d["became_posonly"]))
    if d["reordered"]:
        bits.append("positional parameters reordered")
    if d["default_changed"]:
        bits.append("defaults changed: " + ", ".join(f"`{c['name']}` {c['old']} → {c['new']}" for c in d["default_changed"]))
    if d["added_optional"]:
        bits.append("new optional " + ", ".join(f"`{n}`" for n in d["added_optional"][:6]))
    return "; ".join(bits)


def diff_surfaces(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    old_syms: dict[str, dict[str, Any]] = old.get("symbols") or {}
    new_syms: dict[str, dict[str, Any]] = new.get("symbols") or {}
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    def add(kind: str, severity: str, name: str, target: str, **fields: Any) -> None:
        key = (kind, target)
        if key in grouped:
            if name not in grouped[key]["names"]:
                grouped[key]["names"].append(name)
            return
        grouped[key] = {"kind": kind, "severity": severity, "symbol": name, "target": target, "names": [name], **fields}

    new_by_tail: dict[str, list[str]] = {}
    for q in new_syms:
        new_by_tail.setdefault(q.rsplit(".", 1)[-1], []).append(q)

    def inherited(name: str, candidates: list[str]) -> bool:
        """``Cls.meth`` vanished but ``Cls`` still exists and inherits ``meth`` from a base that now defines it."""
        owner, _, meth = name.rpartition(".")
        cls = new_syms.get(owner)
        if not cls or cls.get("kind") != "class":
            return False
        holders = {c.rpartition(".")[0].rsplit(".", 1)[-1] for c in candidates if c.rsplit(".", 1)[-1] == meth}
        seen: set[str] = set()
        queue = [b.rsplit(".", 1)[-1] for b in cls.get("bases") or []]
        while queue:
            base = queue.pop()
            if base in seen:
                continue
            seen.add(base)
            if base in holders:
                return True
            for q, sym in new_syms.items():
                if sym.get("kind") == "class" and q.rsplit(".", 1)[-1] == base:
                    queue.extend(b.rsplit(".", 1)[-1] for b in sym.get("bases") or [])
        return False

    for name, o in old_syms.items():
        target = o.get("target", name)
        n = new_syms.get(name)
        if n is None and o.get("kind") in ("method", "function") and inherited(name, new_by_tail.get(name.rsplit(".", 1)[-1], [])):
            continue
        if n is None:
            same = [q for q in new_by_tail.get(name.rsplit(".", 1)[-1], []) if new_syms[q]["kind"] == o["kind"] and q not in old_syms]
            if same:
                add(
                    "moved",
                    "breaking",
                    name,
                    target,
                    new_name=same[0],
                    detail=f"`{name}` is no longer available under this name; it now lives at `{same[0]}`.",
                    old_signature=format_signature(name, o.get("params")),
                    new_signature=format_signature(same[0], new_syms[same[0]].get("params")),
                    file=new_syms[same[0]].get("file"),
                    line=new_syms[same[0]].get("line"),
                )
            else:
                add(
                    "removed",
                    "breaking",
                    name,
                    target,
                    detail=f"`{name}` was removed.",
                    old_signature=format_signature(name, o.get("params")),
                    old_params=o.get("params"),
                    file=o.get("file"),
                    line=o.get("line"),
                )
            continue
        o_params, n_params = o.get("params"), n.get("params")
        signature_changed = False
        if o_params is not None and n_params is not None and o_params != n_params:
            d = compare_params(o_params, n_params)
            only_names_kinds_same = (
                not any(
                    d[k]
                    for k in (
                        "removed_params",
                        "added_required",
                        "added_optional",
                        "became_kwonly",
                        "became_posonly",
                        "became_required",
                        "default_changed",
                    )
                )
                and not d["reordered"]
            )
            if not only_names_kinds_same:
                signature_changed = True
                severity = "breaking" if d["breaking"] else "behavior" if d["default_changed"] else "info"
                add(
                    "signature",
                    severity,
                    name,
                    n.get("target", name),
                    detail=_describe(d),
                    old_signature=format_signature(name, o_params),
                    new_signature=format_signature(name, n_params),
                    old_params=o_params,
                    new_params=n_params,
                    params=d,
                    deprecated_in_new=sorted((n.get("deprecated_params") or {}).keys()),
                    file=n.get("file"),
                    line=n.get("line"),
                )
        new_dep = {k: v for k, v in (n.get("deprecated_params") or {}).items() if k not in (o.get("deprecated_params") or {})}
        new_req = {k: v for k, v in (n.get("required_params") or {}).items() if k not in (o.get("required_params") or {})}
        if new_dep or new_req:
            bits = []
            if new_req:
                bits.append("now raises when " + ", ".join(f"`{k}`" for k in new_req) + " is not passed")
            if new_dep:
                bits.append("deprecated argument(s) " + ", ".join(f"`{k}`" for k in new_dep))
            add(
                "contract",
                "breaking" if new_req else "deprecation",
                name,
                n.get("target", name),
                detail="; ".join(bits) + ".",
                deprecated_params=new_dep,
                required_params=new_req,
                new_params=n_params,
                new_signature=format_signature(name, n_params),
                file=n.get("file"),
                line=n.get("line"),
            )
        if n.get("deprecated") and not o.get("deprecated"):
            add(
                "deprecated",
                "deprecation",
                name,
                n.get("target", name),
                detail=f"`{name}` is now deprecated.",
                file=n.get("file"),
                line=n.get("line"),
            )
        if not signature_changed and o.get("body") and n.get("body") and o["body"] != n["body"]:
            add(
                "behavior",
                "behavior",
                name,
                n.get("target", name),
                detail=f"The implementation of `{name}` changed (same signature).",
                new_signature=format_signature(name, n_params),
                file=n.get("file"),
                line=n.get("line"),
            )

    moved_targets = {c["new_name"] for c in grouped.values() if c["kind"] == "moved"}
    for name, n in new_syms.items():
        if name not in old_syms and name not in moved_targets:
            add(
                "added",
                "info",
                name,
                n.get("target", name),
                detail=f"New: `{format_signature(name, n.get('params'))}`.",
                file=n.get("file"),
                line=n.get("line"),
            )

    old_modules, new_modules = set(old.get("modules") or []), set(new.get("modules") or [])
    for module in sorted(old_modules - new_modules):
        if not any(p.startswith("_") for p in module.split(".")[1:]):
            add("module_removed", "breaking", module, module, detail=f"Module `{module}` was removed.")

    changes = list(grouped.values())
    changes.sort(key=lambda c: (-SEVERITY_ORDER[c["severity"]], c["kind"] == "added", c["symbol"]))
    return changes


def _entries(text: str) -> list[str]:
    """Split a changelog into entries: bullets and paragraphs, with wrapped lines joined."""
    entries: list[str] = []
    current: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        starts = bool(re.match(r"^([-*+]|\d+\.)\s", line)) or bool(re.match(r"^(#+\s|[=~^`-]{3,}$)", line))
        if not line or starts:
            if current:
                entries.append(" ".join(current))
            current = []
        if line and not re.match(r"^[=~^`-]{3,}$", line):
            current.append(line.lstrip("-*+ ").lstrip("#").strip())
    if current:
        entries.append(" ".join(current))
    return [e for e in entries if e]


def _clean_entry(text: str) -> str:
    """reStructuredText / Markdown markup to plain text with `code` spans (links keep their label)."""
    text = re.sub(r"`([^`<]+?)\s*<[^>]+>`_{1,2}", r"\1", text)  # `GHSA-x <https://...>`__ -> GHSA-x
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # [label](url) -> label
    text = re.sub(r":[a-z]+:`([^`]+)`", r"`\1`", text)  # :func:`x` -> `x`
    text = text.replace("``", "`")
    text = re.sub(r"\s*<https?://[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def changelog_highlights(old: dict[str, Any] | None, new: dict[str, Any] | None, limit: int = 25) -> list[str]:
    """Changelog entries added since ``old`` that mention breaking changes, removals, deprecations or security."""
    if not new or not new.get("text"):
        return []
    old_entries = set(_entries((old or {}).get("text", ""))) if old else set()
    added = [e for e in _entries(new["text"]) if e not in old_entries]
    if not old:
        added = added[:150]  # without a previous changelog, only look at the newest entries
    hits = [_clean_entry(e) for e in added if CHANGELOG_KEYWORDS.search(e) and len(e) > 12]
    return [h[:400] for h in hits[:limit]]
