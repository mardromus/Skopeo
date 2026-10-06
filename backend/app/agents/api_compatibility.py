"""API Compatibility Agent — public API surface, deprecations, history-based breaking changes and
dependency-upgrade compatibility (against a curated migration knowledge base)."""

from __future__ import annotations

import ast
import json
from collections import defaultdict
from pathlib import Path

from app.agents.base import AgentContext, SpecialistAgent, Step
from app.agents.common import components_for, excerpt
from app.schemas import Category, EvidenceDraft, FindingDraft, Severity, SourceType
from app.tools.advisories import parse_version
from app.tools.python_ast import dotted_name, import_aliases, module_name, parse_python, resolve_call
from app.tools.repository import is_test_path

KB_PATH = Path(__file__).resolve().parents[1] / "data" / "api_migrations.json"


def _public_signatures(tree: ast.Module) -> dict[str, list[str]]:
    sigs: dict[str, list[str]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            sigs[node.name] = [a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            sigs[node.name] = ["<class>"]
    return sigs


class ApiCompatibilityAgent(SpecialistAgent):
    name = "api_compatibility_agent"
    display_name = "API Compatibility Agent"
    category = "api_compatibility"
    description = "Public API extraction, deprecated API usage, git-history breaking-change detection, dependency upgrade compatibility."
    modes = {
        "full": "public API and compatibility review",
        "upgrade_compatibility": "check whether upgrading a dependency breaks existing call sites",
    }

    def plan(self, ctx: AgentContext) -> list[Step]:
        if ctx.task.mode == "upgrade_compatibility":
            return [("check upgrade compatibility against migration knowledge base", self._upgrade)]
        return [
            ("extract public API surface", self._public_api),
            ("find deprecated APIs still in use", self._deprecations),
            ("compare public API across git history", self._history),
        ]

    def _python_modules(self, ctx: AgentContext) -> list[str]:
        packages = set(ctx.profile.get("python_packages") or [])
        return [
            f
            for f in ctx.tools.list_files(suffixes=(".py",), include_tests=False)
            if f.split("/")[0] in packages or (f.startswith("src/") and len(f.split("/")) > 2)
        ]

    def _public_api(self, ctx: AgentContext) -> None:
        total = 0
        exported = []
        for rel in self._python_modules(ctx):
            tree = parse_python(ctx.tools.try_get_file(rel) or "", rel)
            if tree is None:
                continue
            sigs = _public_signatures(tree)
            total += len(sigs)
            if rel.endswith("__init__.py"):
                for node in tree.body:
                    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
                        exported.append(rel)
        self.public_count = total
        ctx.analyzed(
            f"{total} public functions/classes across {len(self._python_modules(ctx))} package modules; __all__ declared in {len(exported)} package(s)"
        )
        if not self._python_modules(ctx):
            ctx.limitation("No importable Python package found — public API analysis limited")

    def _deprecations(self, ctx: AgentContext) -> None:
        deprecated: dict[str, tuple[str, int]] = {}
        for rel in ctx.tools.list_files(suffixes=(".py",), include_tests=False):
            tree = parse_python(ctx.tools.try_get_file(rel) or "", rel)
            if tree is None:
                continue
            for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                for call in [n for n in ast.walk(fn) if isinstance(n, ast.Call)]:
                    name = dotted_name(call.func) or ""
                    if name.endswith("warn") and any(
                        isinstance(a, ast.Name) and a.id in ("DeprecationWarning", "PendingDeprecationWarning")
                        for a in list(call.args) + [k.value for k in call.keywords]
                    ):
                        deprecated[fn.name] = (rel, fn.lineno)
        if not deprecated:
            ctx.analyzed("No functions emitting DeprecationWarning")
            return
        callers: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
        for rel in ctx.tools.list_files(suffixes=(".py",)):
            text = ctx.tools.try_get_file(rel) or ""
            tree = parse_python(text, rel)
            if tree is None:
                continue
            for call in [n for n in ast.walk(tree) if isinstance(n, ast.Call)]:
                name = (dotted_name(call.func) or "").split(".")[-1]
                if name in deprecated and deprecated[name][0] != rel:
                    callers[name].append((rel, call.lineno, text.splitlines()[call.lineno - 1].strip()))
        for fn_name, (rel, lineno) in deprecated.items():
            users = [c for c in callers.get(fn_name, []) if not is_test_path(c[0])]
            if not users:
                continue
            lines = (ctx.tools.try_get_file(rel) or "").splitlines()
            ctx.publish(
                FindingDraft(
                    category=Category.API_COMPATIBILITY,
                    rule_id="api.deprecated_api_in_use",
                    title=f"Deprecated {fn_name}() is still called from {len(users)} production site(s)",
                    description=f"{fn_name} (defined in {rel}:{lineno}) emits DeprecationWarning but is used by "
                    + ", ".join(f"{u[0]}:{u[1]}" for u in users[:5])
                    + ". Removing it would be a breaking change.",
                    severity=Severity.LOW,
                    subject=f"py:{rel}::{fn_name}",
                    affected_files=sorted({rel} | {u[0] for u in users}),
                    affected_components=components_for(rel),
                    attributes={"function": fn_name, "callers": [f"{u[0]}:{u[1]}" for u in users]},
                    reasoning_summary="AST: function emits DeprecationWarning; call sites found in non-test modules.",
                    recommended_action=f"Migrate callers off {fn_name}() before removing it; announce the removal in release notes.",
                ),
                [
                    EvidenceDraft(
                        source_type=SourceType.STATIC_ANALYSIS,
                        source=f"{rel}:{lineno}",
                        tool="skopeo-python-ast",
                        file=rel,
                        line_start=lineno,
                        line_end=lineno + 2,
                        excerpt=excerpt(lines, lineno, lineno + 2),
                        confidence=0.9,
                    )
                ]
                + [
                    EvidenceDraft(
                        source_type=SourceType.STATIC_ANALYSIS,
                        source=f"{u[0]}:{u[1]}",
                        tool="skopeo-python-ast",
                        file=u[0],
                        line_start=u[1],
                        line_end=u[1],
                        excerpt=u[2],
                        confidence=0.9,
                    )
                    for u in users[:5]
                ],
            )

    def _history(self, ctx: AgentContext) -> None:
        commits = ctx.tool("get_git_log", ctx.tools.get_git_log, 200)
        if len(commits) < 2:
            ctx.limitation(f"INSUFFICIENT EVIDENCE for breaking-change detection: git history has {len(commits)} commit(s)")
            return
        old = commits[-1].sha
        removed: list[tuple[str, str, str]] = []
        for rel in self._python_modules(ctx):
            new_tree = parse_python(ctx.tools.try_get_file(rel) or "", rel)
            old_text = ctx.tool("git_show_file", ctx.tools.git_show_file, old, rel)
            old_tree = parse_python(old_text or "", rel) if old_text else None
            if new_tree is None or old_tree is None:
                continue
            new_sigs, old_sigs = _public_signatures(new_tree), _public_signatures(old_tree)
            for name, params in old_sigs.items():
                if name not in new_sigs:
                    removed.append((rel, name, "removed"))
                elif params != ["<class>"] and new_sigs[name] != ["<class>"]:
                    dropped = [p for p in params if p not in new_sigs[name] and p not in ("self", "cls")]
                    if dropped:
                        removed.append((rel, name, f"parameter(s) removed: {', '.join(dropped)}"))
        ctx.analyzed(f"Compared public API of HEAD against {old[:10]} ({len(commits)} commits back)")
        for rel, name, change in removed[:10]:
            ctx.publish(
                FindingDraft(
                    category=Category.API_COMPATIBILITY,
                    rule_id="api.breaking_change",
                    title=f"Public API change in {module_name(rel)}: {name} {change}",
                    description=f"Between {old[:10]} and HEAD the public symbol {name} in {rel} was changed ({change}). Downstream users may break.",
                    severity=Severity.MEDIUM,
                    subject=f"py:{rel}::{name}",
                    affected_files=[rel],
                    affected_components=components_for(rel),
                    attributes={"symbol": name, "change": change, "base_commit": old},
                    reasoning_summary="AST comparison of module-level public signatures at two git revisions.",
                    recommended_action="Keep a deprecation shim or bump the major version.",
                ),
                [
                    EvidenceDraft(
                        source_type=SourceType.GIT,
                        source=f"git show {old[:10]}:{rel}",
                        tool="git",
                        file=rel,
                        excerpt=f"{name}: {change}",
                        confidence=0.85,
                    )
                ],
            )

    def _upgrade(self, ctx: AgentContext) -> None:
        focus = ctx.task.focus
        package = focus.get("package", "")
        current = focus.get("current_version")
        target = focus.get("target_version")
        kb = json.loads(KB_PATH.read_text(encoding="utf-8"))["rules"]
        cur_v, tgt_v = parse_version(current, "PyPI"), parse_version(target, "PyPI") if target else None
        rules = []
        for rule in kb:
            if rule["package"] != package:
                continue
            brk = parse_version(rule["breaking_in"], "PyPI")
            if cur_v is not None and brk is not None and cur_v < brk and (tgt_v is None or tgt_v >= brk):
                rules.append(rule)
        if not rules:
            ctx.message(
                "orchestrator",
                f"No documented breaking changes for {package} {current} -> {target} in the migration knowledge base",
                payload={"package": package},
            )
            ctx.limitation(f"Upgrade compatibility for {package}: no knowledge-base rules (INSUFFICIENT EVIDENCE beyond static search)")
            return
        matches = []
        for rel in ctx.tools.list_files(suffixes=(".py",), include_tests=False):
            text = ctx.tools.try_get_file(rel) or ""
            tree = parse_python(text, rel)
            if tree is None:
                continue
            lines = text.splitlines()
            aliases = import_aliases(tree)
            assigned_from: dict[str, str] = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                    callee = resolve_call(dotted_name(node.value.func) or "", aliases)
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            assigned_from[t.id] = callee
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                full = resolve_call(dotted_name(node.func) or "", aliases)
                kws = {k.arg for k in node.keywords if k.arg}
                for rule in rules:
                    hit = False
                    if (
                        rule["condition"] == "missing_keyword"
                        and full == rule["call"]
                        and rule["keyword"] not in kws
                        or rule["condition"] == "has_keyword"
                        and full == rule["call"]
                        and rule["keyword"] in kws
                        or rule["condition"] == "called"
                        and (full == rule["call"] or (rule["call"].startswith("*.") and full.endswith(rule["call"][1:])))
                    ):
                        hit = True
                    elif (
                        rule["condition"] == "result_method_called"
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == rule["method"]
                    ):
                        base = node.func.value
                        if (
                            isinstance(base, ast.Call)
                            and resolve_call(dotted_name(base.func) or "", aliases) == rule["call"]
                            or isinstance(base, ast.Name)
                            and assigned_from.get(base.id) == rule["call"]
                        ):
                            hit = True
                    if hit:
                        matches.append(
                            (
                                rule,
                                rel,
                                node.lineno,
                                getattr(node, "end_lineno", node.lineno),
                                excerpt(lines, node.lineno, getattr(node, "end_lineno", node.lineno)),
                            )
                        )
        if not matches:
            ctx.message(
                "orchestrator",
                f"Upgrade {package} {current} -> {target}: no call sites match {len(rules)} documented breaking change(s)",
                payload={"package": package, "rules": [r["id"] for r in rules]},
            )
            ctx.analyzed(f"Upgrade compatibility checked for {package}: compatible with documented changes")
            return
        files = sorted({m[1] for m in matches})
        evidence = [
            EvidenceDraft(
                source_type=SourceType.STATIC_ANALYSIS,
                source=f"{rel}:{line}",
                tool="skopeo-api-migration-check",
                file=rel,
                line_start=line,
                line_end=end,
                excerpt=snippet,
                raw_reference=rule["source"],
                confidence=0.9,
                data={"rule": rule["id"], "breaking_in": rule["breaking_in"]},
            )
            for rule, rel, line, end, snippet in matches[:12]
        ]
        ctx.publish(
            FindingDraft(
                category=Category.API_COMPATIBILITY,
                rule_id="api.upgrade_breaking_changes",
                title=f"Upgrading {package} {current} -> {target or 'latest'} breaks {len(matches)} call site(s) in {', '.join(files)}",
                description=" ".join(f"[{r['id']}] {r['description']} ({rel}:{line})" for r, rel, line, _, _ in matches[:6]),
                severity=Severity.MEDIUM,
                subject=f"upgrade:{package}",
                affected_files=files,
                affected_components=sorted({c for f in files for c in components_for(f)}),
                attributes={
                    "package": package,
                    "current_version": current,
                    "target_version": target,
                    "breaking_rules": sorted({m[0]["id"] for m in matches}),
                    "call_sites": [f"{m[1]}:{m[2]}" for m in matches],
                    "fixes": sorted({m[0]["fix"] for m in matches}),
                    "upgrade_blocked": True,
                },
                reasoning_summary=f"Follow-up from orchestrator. {len(rules)} documented breaking change(s) between {current} and {target}; AST matched {len(matches)} affected call site(s).",
                recommended_action="Update the listed call sites in the same change as the version bump: "
                + " ".join(sorted({m[0]["fix"] for m in matches})),
            ),
            evidence,
        )
        ctx.message(
            "orchestrator",
            f"Upgrade of {package} is not drop-in: {len(matches)} call site(s) need changes",
            payload={"package": package, "call_sites": [f"{m[1]}:{m[2]}" for m in matches]},
        )
