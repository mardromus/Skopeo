"""Deterministic Python static analysis helpers (AST based — no code is ever executed)."""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.tools.repository import RepositoryTools

_DECISION_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler, ast.With, ast.AsyncWith, ast.Assert)
_NESTING_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)


@dataclass
class FunctionMetrics:
    name: str
    qualname: str
    file: str
    lineno: int
    end_lineno: int
    complexity: int
    length: int
    max_nesting: int
    params: int
    has_docstring: bool

    @property
    def subject(self) -> str:
        return f"py:{self.file}::{self.qualname}"


@dataclass
class CallSite:
    dotted: str
    lineno: int
    end_lineno: int
    in_loop: bool
    loop_lineno: int | None
    function: str | None
    keywords: list[str] = field(default_factory=list)
    n_args: int = 0


def parse_python(text: str, filename: str = "<repo>") -> ast.Module | None:
    try:
        return ast.parse(text, filename=filename)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def cyclomatic_complexity(node: ast.AST) -> int:
    """McCabe-style complexity: 1 + decision points (branches, loops, handlers, boolean ops)."""
    complexity = 1
    for child in ast.walk(node):
        if child is not node and isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler, ast.Assert)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            complexity += 1 + len(child.ifs)
        elif isinstance(child, ast.match_case):
            complexity += 1
    return complexity


def max_nesting(node: ast.AST, depth: int = 0) -> int:
    best = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        child_depth = depth + 1 if isinstance(child, _NESTING_NODES) else depth
        best = max(best, max_nesting(child, child_depth))
    return best


def iter_functions(tree: ast.Module, file: str) -> list[FunctionMetrics]:
    out: list[FunctionMetrics] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{prefix}{child.name}"
                end = getattr(child, "end_lineno", child.lineno) or child.lineno
                args = child.args
                n_params = len(args.args) + len(args.kwonlyargs) + len(args.posonlyargs) + bool(args.vararg) + bool(args.kwarg)
                out.append(
                    FunctionMetrics(
                        name=child.name,
                        qualname=qual,
                        file=file,
                        lineno=child.lineno,
                        end_lineno=end,
                        complexity=cyclomatic_complexity(child),
                        length=end - child.lineno + 1,
                        max_nesting=max_nesting(child),
                        params=n_params,
                        has_docstring=ast.get_docstring(child) is not None,
                    )
                )
                visit(child, qual + ".")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")

    visit(tree, "")
    return out


def dotted_name(expr: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    if isinstance(expr, ast.Name):
        parts.append(expr.id)
    elif isinstance(expr, ast.Call):
        inner = dotted_name(expr.func)
        if inner:
            parts.append(inner + "()")
        else:
            return None
    else:
        return None
    return ".".join(reversed(parts))


def import_aliases(tree: ast.Module) -> dict[str, str]:
    """Map local names to fully-qualified import targets (``decode`` -> ``jwt.decode``)."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                aliases[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                aliases[a.asname or a.name] = f"{node.module}.{a.name}"
    return aliases


def resolve_call(dotted: str, aliases: dict[str, str]) -> str:
    head, _, rest = dotted.partition(".")
    if head in aliases:
        return aliases[head] + ("." + rest if rest else "")
    return dotted


def call_sites(tree: ast.Module) -> list[CallSite]:
    """All calls with loop context (used for N+1 / repeated-call detection and usage analysis)."""
    sites: list[CallSite] = []

    def visit(node: ast.AST, loop_line: int | None, function: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            fn = function
            ll = loop_line
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = child.name
                ll = None
            elif isinstance(child, (ast.For, ast.AsyncFor, ast.While)):
                # The iterable expression is evaluated once; only the body repeats.
                visit_expr = child.iter if isinstance(child, (ast.For, ast.AsyncFor)) else child.test
                visit(ast.Expr(value=visit_expr), loop_line, function)
                for stmt in child.body + child.orelse:
                    visit(ast.Module(body=[stmt], type_ignores=[]), child.lineno, function)
                continue
            elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                ll = child.lineno
            if isinstance(child, ast.Call):
                name = dotted_name(child.func)
                if name:
                    sites.append(
                        CallSite(
                            dotted=name,
                            lineno=child.lineno,
                            end_lineno=getattr(child, "end_lineno", child.lineno) or child.lineno,
                            in_loop=ll is not None,
                            loop_lineno=ll,
                            function=fn,
                            keywords=[k.arg for k in child.keywords if k.arg],
                            n_args=len(child.args),
                        )
                    )
            visit(child, ll, fn)

    visit(tree, None, None)
    return sites


def module_name(path: str) -> str | None:
    if not path.endswith(".py"):
        return None
    parts = path[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if parts and parts[0] == "src":
        parts = parts[1:]
    return ".".join(parts) if parts else None


class ImportGraph:
    """Internal import graph — used for reachability ("is this code actually used?")."""

    def __init__(self, tools: RepositoryTools) -> None:
        self.tools = tools
        self.modules: dict[str, str] = {}
        self.imports: dict[str, set[str]] = defaultdict(set)
        self.importers: dict[str, set[str]] = defaultdict(set)
        self.external_imports: dict[str, set[str]] = defaultdict(set)  # file -> top-level external names
        self._build()

    def _build(self) -> None:
        files = self.tools.list_files(suffixes=(".py",))
        for f in files:
            mod = module_name(f)
            if mod:
                self.modules[mod] = f
        for f in files:
            text = self.tools.try_get_file(f)
            tree = parse_python(text or "", f) if text else None
            if tree is None:
                continue
            for node in ast.walk(tree):
                targets: list[str] = []
                if isinstance(node, ast.Import):
                    targets = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level and node.level > 0:
                        base = (module_name(f) or "").split(".")
                        base = base[: len(base) - node.level + (1 if f.endswith("__init__.py") else 0)]
                        prefix = ".".join(base)
                        mod = f"{prefix}.{node.module}" if node.module else prefix
                    else:
                        mod = node.module or ""
                    targets = [mod] + [f"{mod}.{a.name}" for a in node.names]
                for t in targets:
                    internal = self._internal_module(t)
                    if internal:
                        if internal != module_name(f):
                            self.imports[f].add(self.modules[internal])
                            self.importers[self.modules[internal]].add(f)
                    elif t:
                        self.external_imports[f].add(t.split(".")[0])

    def _internal_module(self, name: str) -> str | None:
        parts = name.split(".")
        while parts:
            cand = ".".join(parts)
            if cand in self.modules:
                return cand
            parts = parts[:-1]
        return None

    def importers_of(self, file: str) -> set[str]:
        return set(self.importers.get(file, set()))

    def transitive_importers(self, file: str) -> set[str]:
        seen: set[str] = set()
        stack = [file]
        while stack:
            cur = stack.pop()
            for imp in self.importers.get(cur, ()):
                if imp not in seen:
                    seen.add(imp)
                    stack.append(imp)
        return seen

    def files_importing_external(self, package_import_name: str) -> list[str]:
        return sorted(f for f, names in self.external_imports.items() if package_import_name in names)
