"""Join upstream changes with the project's usages: which lines of *your* code does a change touch?

For calls, the arguments are checked against the new signature, so a signature change that your
call still satisfies is reported as low impact, while ``jwt.decode(token, verify=False)`` against a
signature without ``verify`` is reported as certainly breaking.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

IMPACT_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "breaking": 4}


def _index(changes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for c in changes:
        if c["kind"] == "added":
            continue
        for name in {*c.get("names", []), c["symbol"], c.get("target", c["symbol"])}:
            index.setdefault(name, []).append(c)
    return index


def _module_changes(changes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {c["symbol"]: c for c in changes if c["kind"] == "module_removed"}


def check_call(usage: dict[str, Any], change: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return [(impact level, certainty, reason)] for one call against one signature or contract change."""
    d = change.get("params") or {}
    new_params: list[dict[str, Any]] = change.get("new_params") or []
    reasons: list[tuple[str, str, str]] = []
    kws: list[str] = usage.get("keywords") or []
    pos = usage.get("positional")
    star_args, star_kwargs = usage.get("star_args", False), usage.get("star_kwargs", False)
    old_pos: list[str] = d.get("old_positional", [])
    new_pos: list[str] = d.get("new_positional") or [p["name"] for p in new_params if p["kind"] in ("posonly", "pos")]
    deprecated_now = set(change.get("deprecated_in_new") or []) | set((change.get("deprecated_params") or {}).keys())

    def passes(name: str) -> bool:
        return name in kws or (pos is not None and name in new_pos and new_pos.index(name) < pos)

    if change["kind"] == "contract":
        for name, msg in (change.get("deprecated_params") or {}).items():
            if passes(name):
                reasons.append(("high", "certain", f"passes `{name}`, which upstream deprecated" + (f": \u201c{msg}\u201d" if msg else "")))
        for name, msg in (change.get("required_params") or {}).items():
            if not passes(name) and not star_kwargs:
                reasons.append(
                    (
                        "breaking",
                        "likely",
                        f"does not pass `{name}`; upstream now raises when it is missing" + (f": \u201c{msg}\u201d" if msg else ""),
                    )
                )
        return reasons

    for k in kws:
        if k in d.get("removed_params", []):
            if d.get("new_has_varkw"):
                reasons.append(
                    (
                        "high",
                        "likely",
                        f"passes `{k}=`, which is no longer a named parameter (it is now swallowed by **kwargs and probably ignored)",
                    )
                )
            else:
                reasons.append(("breaking", "certain", f"passes `{k}=`, which was removed (TypeError: unexpected keyword argument)"))
    if pos is not None and not star_args:
        if pos > len(new_pos) and not d.get("new_has_var"):
            reasons.append(
                ("breaking", "certain", f"passes {pos} positional argument(s); the new signature accepts at most {len(new_pos)}")
            )
        for name in d.get("became_kwonly", []):
            if name in old_pos and old_pos.index(name) < pos:
                reasons.append(("breaking", "certain", f"passes `{name}` positionally; it is keyword-only now"))
        if d.get("reordered"):
            shared = [n for n in old_pos[:pos] if n in new_pos]
            if any(new_pos.index(n) != old_pos.index(n) for n in shared):
                reasons.append(("breaking", "certain", "passes positional arguments whose order changed"))
        for name in [*d.get("added_required", []), *d.get("became_required", [])]:
            if not passes(name) and not star_kwargs:
                reasons.append(("breaking", "certain", f"does not pass `{name}`, which is now required"))
        for dc in d.get("default_changed", []):
            name = dc["name"]
            if name in deprecated_now or passes(name) or star_kwargs:
                continue
            reasons.append(
                (
                    "medium",
                    "possible",
                    f"relies on the default of `{name}`, which changed from {dc['old']} to {dc['new']}; check the new default behaves the same",
                )
            )
    elif pos is None and change.get("new_params") is not None:
        required = [p for p in new_params if p["kind"] in ("pos", "posonly", "kwonly") and p["default"] is None]
        if required:
            reasons.append(("medium", "possible", "the signature changed; Skopeo could not count the arguments of this call"))
    return reasons


def assess_impacts(changes: list[dict[str, Any]], usages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = _index(changes)
    modules = _module_changes(changes)
    impacts: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str, str]] = set()

    def add(
        level: str, certainty: str, usage: dict[str, Any], change: dict[str, Any], title: str, explanation: str, suggestion: str
    ) -> None:
        key = (usage["file"], usage["line"], change["kind"], change["symbol"])
        if key in seen:
            return
        seen.add(key)
        impacts.append(
            {
                "level": level,
                "certainty": certainty,
                "title": title,
                "explanation": explanation,
                "suggestion": suggestion,
                "file": usage["file"],
                "line": usage["line"],
                "snippet": usage.get("snippet", ""),
                "usage_kind": usage["kind"],
                "symbol": usage["symbol"],
                "change": {
                    k: change.get(k)
                    for k in ("kind", "severity", "symbol", "detail", "old_signature", "new_signature", "new_name", "file", "line")
                    if change.get(k) is not None
                },
            }
        )

    for u in usages:
        sym = u["symbol"]
        for module, change in modules.items():
            if sym == module or sym.startswith(module + "."):
                add(
                    "breaking",
                    "certain",
                    u,
                    change,
                    f"Module `{module}` was removed",
                    f"Your code imports or uses `{sym}`, but the module `{module}` no longer exists upstream.",
                    "Find where the functionality moved (see the changelog) and update the import.",
                )
        for change in index.get(sym, []):
            kind = change["kind"]
            if kind == "removed":
                add(
                    "breaking",
                    "certain",
                    u,
                    change,
                    f"`{sym}` was removed upstream",
                    f"Your code {('calls' if u['kind'] == 'call' else 'uses')} `{sym}`, which no longer exists. "
                    + (
                        "This import will fail with ImportError."
                        if u["kind"] == "import"
                        else "This will fail with AttributeError / ImportError."
                    ),
                    "Check the changelog for the replacement before upgrading, or pin the current version.",
                )
            elif kind == "moved":
                add(
                    "breaking",
                    "certain",
                    u,
                    change,
                    f"`{sym}` moved to `{change.get('new_name')}`",
                    f"Your code uses `{sym}`, which is no longer available under that name.",
                    f"Import it from its new location: `{change.get('new_name')}`.",
                )
            elif kind == "contract" and u["kind"] == "call":
                reasons = check_call(u, change)
                if reasons:
                    level = max((r[0] for r in reasons), key=lambda lv: IMPACT_ORDER[lv])
                    certainty = next(r[1] for r in reasons if r[0] == level)
                    add(
                        level,
                        certainty,
                        u,
                        change,
                        f"Your call to `{sym}` {'will fail' if level == 'breaking' else 'uses a deprecated argument'}",
                        "This call " + "; ".join(r[2] for r in reasons) + ".",
                        _contract_fix(u, change),
                    )
            elif kind == "signature":
                if u["kind"] == "call":
                    reasons = check_call(u, change)
                    if reasons:
                        level = max((r[0] for r in reasons), key=lambda lv: IMPACT_ORDER[lv])
                        certainty = next(r[1] for r in reasons if r[0] == level)
                        add(
                            level,
                            certainty,
                            u,
                            change,
                            f"Your call to `{sym}` {'breaks' if level == 'breaking' else 'is affected'}",
                            "This call " + "; ".join(r[2] for r in reasons) + ".",
                            f"Update the call to match `{change.get('new_signature')}`.",
                        )
                    elif change["severity"] != "info":
                        add(
                            "low",
                            "likely",
                            u,
                            change,
                            f"`{sym}` changed signature; your call still fits",
                            f"Upstream: {change.get('detail')}. The arguments your code passes are still accepted.",
                            "No change needed; re-run your tests after upgrading.",
                        )
                elif u["kind"] != "import" and change["severity"] == "breaking":
                    add(
                        "medium",
                        "possible",
                        u,
                        change,
                        f"`{sym}` changed signature",
                        f"Your code references `{sym}` (for example passing it as a callback). Upstream: {change.get('detail')}.",
                        f"Check every place that ends up calling it against `{change.get('new_signature')}`.",
                    )
            elif kind == "deprecated":
                add(
                    "medium",
                    "certain",
                    u,
                    change,
                    f"`{sym}` is deprecated",
                    f"Your code uses `{sym}`, which upstream now marks as deprecated; it will likely be removed in a future release.",
                    "Move to the recommended replacement (see the changelog) while both still work.",
                )
            elif kind == "behavior" and u["kind"] in ("call", "reference"):
                add(
                    "low",
                    "possible",
                    u,
                    change,
                    f"`{sym}` behaves differently",
                    f"The implementation of `{sym}` changed upstream while its signature stayed the same.",
                    "Review the upstream commits for this function and cover this call site with a test.",
                )
    # a line already reported as affected does not also need a "your call still fits" entry
    serious = {(i["file"], i["line"], i["symbol"]) for i in impacts if IMPACT_ORDER[i["level"]] >= IMPACT_ORDER["medium"]}
    impacts = [i for i in impacts if not (i["level"] == "low" and (i["file"], i["line"], i["symbol"]) in serious)]
    impacts.sort(key=lambda i: (-IMPACT_ORDER[i["level"]], i["file"], i["line"]))
    return impacts


def _contract_fix(usage: dict[str, Any], change: dict[str, Any]) -> str:
    kws = set(usage.get("keywords") or [])
    missing = [p for p in (change.get("required_params") or {}) if p not in kws]
    deprecated = [p for p in (change.get("deprecated_params") or {}) if p in kws]
    bits = []
    if missing:
        bits.append("pass " + ", ".join(f"`{p}=`" for p in missing) + " explicitly")
    if deprecated:
        bits.append("remove " + ", ".join(f"`{p}=`" for p in deprecated))
    return ("Before upgrading, " + " and ".join(bits) + ".") if bits else "Follow the upstream message above."


def impact_level(impacts: list[dict[str, Any]]) -> str:
    if not impacts:
        return "none"
    return max((i["level"] for i in impacts), key=lambda lv: IMPACT_ORDER[lv])


def usage_inventory(usages: list[dict[str, Any]], limit: int = 40) -> list[dict[str, Any]]:
    """Which library symbols the project uses, and how often (calls and references, not imports)."""
    counts: Counter[str] = Counter(u["symbol"] for u in usages if u["kind"] != "import")
    files: dict[str, set[str]] = {}
    for u in usages:
        files.setdefault(u["symbol"], set()).add(u["file"])
    return [{"symbol": s, "uses": n, "files": sorted(files[s])[:10]} for s, n in counts.most_common(limit)]
