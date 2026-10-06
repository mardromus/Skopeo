"""Test Reliability Agent — discovers tests, analyses assertion quality and flakiness indicators,
maps tests to code, and *actually runs* the suite (with coverage) when the trust policy allows.

Test results are never fabricated: every number comes from the executed command, which is
recorded (argv, exit code, duration, output tail) as evidence.
"""

from __future__ import annotations

import ast
from collections import defaultdict

from app.agents.base import AgentContext, SpecialistAgent, Step
from app.agents.common import components_for, excerpt
from app.schemas import Category, EvidenceDraft, FindingDraft, Severity, SourceType
from app.services.risk_scoring import SECURITY_CRITICAL_COMPONENTS
from app.tools.python_ast import ImportGraph, dotted_name, parse_python
from app.tools.repository import is_test_path

_FLAKY_CALLS = {
    "time.sleep": "sleep-based timing",
    "random.random": "unseeded randomness",
    "random.randint": "unseeded randomness",
    "random.choice": "unseeded randomness",
    "datetime.now": "wall-clock dependency",
    "datetime.datetime.now": "wall-clock dependency",
    "requests.get": "real network call",
    "requests.post": "real network call",
}


def _is_weak_assert(node: ast.Assert) -> str | None:
    test = node.test
    if isinstance(test, ast.Constant) and test.value:
        return "assert of a truthy constant"
    if (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.IsNot)
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value is None
    ):
        return "only checks the result is not None"
    if isinstance(test, ast.Name):
        return "only checks truthiness"
    return None


class TestReliabilityAgent(SpecialistAgent):
    __test__ = False  # not a pytest test class

    name = "test_reliability_agent"
    display_name = "Test Reliability Agent"
    category = "testing"
    description = "Test discovery, assertion quality, flakiness indicators, test-to-code mapping, real test execution with coverage."
    modes = {
        "full": "complete test reliability review",
        "dependency_coverage": "determine whether code that uses a given dependency is covered by tests",
    }

    def plan(self, ctx: AgentContext) -> list[Step]:
        if ctx.task.mode == "dependency_coverage":
            return [("map tests to code using the dependency", self._dependency_coverage)]
        steps: list[Step] = [
            ("discover test framework & suites", self._discover),
            ("analyse assertion quality & flakiness indicators", self._static_quality),
            ("map tests to production modules", self._mapping),
        ]
        if ctx.profile.get("trusted_execution"):
            steps.append(("execute test suite with coverage", self._execute))
        else:
            ctx.limitation(
                "Tests NOT executed: repository code is untrusted and SKOPEO_SANDBOX_EXECUTION is disabled (static analysis only)"
            )
        return steps

    def _discover(self, ctx: AgentContext) -> None:
        files = ctx.tools.list_files()
        self.py_tests = [
            f for f in files if f.endswith(".py") and is_test_path(f) and f.split("/")[-1].startswith("test") or f.endswith("_test.py")
        ]
        self.frameworks = []
        if self.py_tests:
            self.frameworks.append("pytest")
        if any(f.endswith((".test.js", ".test.ts", ".spec.ts", ".spec.js", ".test.tsx")) for f in files):
            self.frameworks.append("jest/vitest")
        if any(f.endswith("_test.go") for f in files):
            self.frameworks.append("go test")
        ctx.analyzed(f"Frameworks: {', '.join(self.frameworks) or 'none detected'}; {len(self.py_tests)} Python test modules")
        ctx.message(
            "orchestrator",
            f"Discovered {len(self.py_tests)} Python test module(s); frameworks: {', '.join(self.frameworks) or 'none'}",
            payload={"test_files": self.py_tests[:30]},
        )
        if "jest/vitest" in self.frameworks or "go test" in self.frameworks:
            ctx.limitation("Non-Python test suites are analysed statically only (execution supports pytest)")

    def _static_quality(self, ctx: AgentContext) -> None:
        weak: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
        no_assert: dict[str, list[tuple[str, int]]] = defaultdict(list)
        flaky: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
        test_count = 0
        for rel in self.py_tests:
            tree = parse_python(ctx.tools.try_get_file(rel) or "", rel)
            if tree is None:
                continue
            for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")]:
                test_count += 1
                asserts = [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]
                raises = [
                    n
                    for n in ast.walk(fn)
                    if isinstance(n, ast.With)
                    and any("raises" in (dotted_name(i.context_expr.func) or "") for i in n.items if isinstance(i.context_expr, ast.Call))
                ]
                method_asserts = [
                    n for n in ast.walk(fn) if isinstance(n, ast.Call) and (dotted_name(n.func) or "").split(".")[-1].startswith("assert")
                ]
                if not asserts and not raises and not method_asserts:
                    no_assert[rel].append((fn.name, fn.lineno))
                weak_reasons = [(_is_weak_assert(a), a.lineno) for a in asserts]
                weak_reasons = [(r, ln) for r, ln in weak_reasons if r]
                if asserts and len(weak_reasons) == len(asserts):
                    weak[rel].append((fn.name, weak_reasons[0][1], weak_reasons[0][0]))
                for call in [n for n in ast.walk(fn) if isinstance(n, ast.Call)]:
                    name = dotted_name(call.func) or ""
                    if name in _FLAKY_CALLS:
                        flaky[rel].append((fn.name, call.lineno, _FLAKY_CALLS[name]))
        self.test_count = test_count
        ctx.analyzed(f"{test_count} test functions analysed statically")
        for rel, items in weak.items():
            lines = (ctx.tools.try_get_file(rel) or "").splitlines()
            ctx.publish(
                FindingDraft(
                    category=Category.TESTING,
                    rule_id="testing.weak_assertion",
                    title=f"{len(items)} test(s) in {rel} only make weak assertions",
                    description="; ".join(f"{name} ({reason}, line {ln})" for name, ln, reason in items[:6])
                    + ". Such tests pass even when behaviour is wrong.",
                    severity=Severity.LOW,
                    subject=f"tests:{rel}",
                    affected_files=[rel],
                    affected_components=["tests"],
                    attributes={"tests": [n for n, _, _ in items], "test_only": True},
                    reasoning_summary="AST: every assertion in the test is a truthiness / not-None check.",
                    recommended_action="Assert on concrete expected values (content, length, specific fields).",
                ),
                [
                    EvidenceDraft(
                        source_type=SourceType.STATIC_ANALYSIS,
                        source=f"{rel}:{ln}",
                        tool="skopeo-test-ast",
                        file=rel,
                        line_start=ln,
                        line_end=ln,
                        excerpt=excerpt(lines, ln, ln),
                        confidence=0.9,
                    )
                    for _, ln, _ in items[:6]
                ],
            )
        for rel, items in no_assert.items():
            ctx.publish(
                FindingDraft(
                    category=Category.TESTING,
                    rule_id="testing.no_assertions",
                    title=f"{len(items)} test(s) in {rel} contain no assertions",
                    description=", ".join(n for n, _ in items[:8]),
                    severity=Severity.LOW,
                    subject=f"tests-noassert:{rel}",
                    affected_files=[rel],
                    affected_components=["tests"],
                    attributes={"tests": [n for n, _ in items], "test_only": True},
                    reasoning_summary="AST: no assert statements, pytest.raises or assert* calls.",
                    recommended_action="Add assertions that check observable behaviour.",
                ),
                [
                    EvidenceDraft(
                        source_type=SourceType.STATIC_ANALYSIS,
                        source=f"{rel}:{ln}",
                        tool="skopeo-test-ast",
                        file=rel,
                        line_start=ln,
                        line_end=ln,
                        excerpt=n,
                        confidence=0.9,
                    )
                    for n, ln in items[:6]
                ],
            )
        for rel, items in flaky.items():
            ctx.publish(
                FindingDraft(
                    category=Category.TESTING,
                    rule_id="testing.flaky_indicators",
                    title=f"Flakiness indicators in {rel} ({', '.join(sorted({r for _, _, r in items}))})",
                    description="; ".join(f"{n}:{ln} {r}" for n, ln, r in items[:6]),
                    severity=Severity.LOW,
                    subject=f"tests-flaky:{rel}",
                    affected_files=[rel],
                    affected_components=["tests"],
                    attributes={"indicators": sorted({r for _, _, r in items}), "test_only": True},
                    reasoning_summary="Static indicators only; flakiness is not established without repeated runs.",
                    recommended_action="Seed randomness, freeze time, mock network and replace sleeps with explicit waits.",
                    is_hypothesis=False,
                ),
                [
                    EvidenceDraft(
                        source_type=SourceType.STATIC_ANALYSIS,
                        source=f"{rel}:{ln}",
                        tool="skopeo-test-ast",
                        file=rel,
                        line_start=ln,
                        line_end=ln,
                        excerpt=f"{n}: {r}",
                        confidence=0.6,
                    )
                    for n, ln, r in items[:6]
                ],
            )

    def _mapping(self, ctx: AgentContext) -> None:
        graph = ctx.tool("build_import_graph", ImportGraph, ctx.tools)
        self.graph = graph
        tested: set[str] = set()
        for t in self.py_tests:
            tested |= graph.imports.get(t, set())
        self.tested_modules = tested
        source = [f for f in ctx.tools.list_files(suffixes=(".py",), include_tests=False) if not f.endswith("__init__.py")]
        untested = [f for f in source if f not in tested]
        ctx.analyzed(f"{len(tested)} of {len(source)} production modules imported directly by tests")
        by_component: dict[str, list[str]] = defaultdict(list)
        for f in untested:
            for c in components_for(f):
                if c in SECURITY_CRITICAL_COMPONENTS:
                    by_component[c].append(f)
        for component, files in by_component.items():
            ctx.publish(
                FindingDraft(
                    category=Category.TESTING,
                    rule_id="testing.untested_critical_path",
                    title=f"Security-critical {component} code has no tests ({', '.join(files[:3])})",
                    description=f"No test module imports {', '.join(files)}. Changes to {component} logic (including dependency upgrades) ship without regression protection.",
                    severity=Severity.HIGH,
                    subject=f"untested:{component}",
                    affected_files=files,
                    affected_components=[component],
                    attributes={"component": component, "untested_files": files, "evidence_basis": "static_import_mapping"},
                    reasoning_summary="Static test-to-code import mapping; coverage evidence is added if the suite can be executed.",
                    recommended_action=f"Add unit tests for {component} paths (valid/invalid/expired tokens, tampered signatures, wrong algorithms).",
                ),
                [
                    EvidenceDraft(
                        source_type=SourceType.STATIC_ANALYSIS,
                        source="test import graph",
                        tool="skopeo-import-graph",
                        file=f,
                        excerpt=f"no test module imports {f}; tests import: {', '.join(sorted(tested))[:300] or 'nothing'}",
                        confidence=0.8,
                    )
                    for f in files[:5]
                ],
            )

    def _execute(self, ctx: AgentContext) -> None:
        if not self.py_tests:
            ctx.limitation("No Python tests to execute")
            return
        test_dirs = sorted({t.split("/")[0] if "/" in t else t for t in self.py_tests})
        packages = ctx.profile.get("python_packages") or []
        run = ctx.tool("run_tests", ctx.tools.run_tests, test_dirs, packages)
        res = run["result"]
        parsed = run["pytest"]
        summary = res.summary(1500)
        summary.update({"parsed": parsed["counts"], "failures": parsed["failures"][:20]})
        ctx.record_tool_result(summary)
        ctx.coverage["test_run"] = {
            "command": summary["command"],
            "exit_code": res.exit_code,
            "duration_ms": res.duration_ms,
            "counts": parsed["counts"],
            "summary": parsed["summary"],
        }
        ctx.message(
            "orchestrator",
            f"Executed test suite: {parsed['summary'] or 'no summary'} (exit code {res.exit_code}, {res.duration_ms} ms)",
            payload=ctx.coverage["test_run"],
        )
        if res.timed_out:
            ctx.limitation("Test run timed out — results incomplete")
        if res.exit_code not in (0, 1):
            ctx.limitation(f"Test run ended abnormally (exit {res.exit_code}); see output — failures are not inferred")
        for failure in [f for f in parsed["failures"] if f["kind"] == "failed"][:10]:
            node = failure["node_id"]
            rel = node.split("::")[0]
            ctx.publish(
                FindingDraft(
                    category=Category.TESTING,
                    rule_id="testing.test_failure",
                    title=f"Failing test: {node}",
                    description=f"{node} failed when the suite was executed: {failure['message'] or 'see output'}",
                    severity=Severity.MEDIUM,
                    subject=f"test:{node}",
                    affected_files=[rel],
                    affected_components=["tests"],
                    attributes={
                        "node_id": node,
                        "exit_code": res.exit_code,
                        "message": failure["message"],
                        "reproducible_command": f"python -m pytest {node}",
                    },
                    tool_results=[{k: summary[k] for k in ("command", "exit_code", "duration_ms")}],
                    reasoning_summary="Observed failure from a real pytest execution (not inferred).",
                    recommended_action=f"Fix the behaviour under test or the test itself; run `python -m pytest {node}`.",
                ),
                [
                    EvidenceDraft(
                        source_type=SourceType.TEST,
                        source=summary["command"],
                        tool="pytest",
                        file=rel,
                        excerpt=(failure["message"] or parsed["summary"])[:600],
                        raw_reference=summary["stdout_tail"][-1500:],
                        confidence=0.95,
                        data={"exit_code": res.exit_code, "duration_ms": res.duration_ms, "counts": parsed["counts"]},
                    )
                ],
            )
        cov = run["coverage"]
        if not cov:
            ctx.limitation("Coverage data unavailable for this run")
            return
        totals = cov.get("totals", {})
        pct = float(totals.get("percent_covered", 0.0))
        ctx.coverage["line_coverage_percent"] = round(pct, 1)
        files_cov = {k.replace("\\", "/"): v for k, v in (cov.get("files") or {}).items()}
        self.files_cov = files_cov
        critical = {
            f.attributes.get("component"): f for f in ctx.findings(agent=self.name) if f.rule_id == "testing.untested_critical_path"
        }
        for finding in critical.values():
            for rel in finding.affected_files:
                entry = files_cov.get(rel)
                if entry is None:
                    continue
                summary_f = entry.get("summary", {})
                ctx.attach_evidence(
                    finding.finding_id,
                    EvidenceDraft(
                        source_type=SourceType.TEST,
                        source="coverage.py json report",
                        tool="coverage",
                        file=rel,
                        excerpt=f"{rel}: {summary_f.get('percent_covered', 0):.0f}% line coverage ({summary_f.get('covered_lines', 0)}/{summary_f.get('num_statements', 0)} statements) during the executed test run",
                        confidence=0.95,
                        data={"percent_covered": summary_f.get("percent_covered"), "missing_lines": entry.get("missing_lines", [])[:50]},
                    ),
                    f"Coverage run confirms {rel} at {summary_f.get('percent_covered', 0):.0f}% coverage",
                    reproduced=True,
                )
        if pct < 60:
            ctx.publish(
                FindingDraft(
                    category=Category.TESTING,
                    rule_id="testing.low_coverage",
                    title=f"Overall line coverage is {pct:.0f}%",
                    description=f"The executed suite covers {totals.get('covered_lines')} of {totals.get('num_statements')} statements in {', '.join(ctx.profile.get('python_packages') or ['the package'])}.",
                    severity=Severity.MEDIUM if pct < 40 else Severity.LOW,
                    subject="coverage:total",
                    affected_files=[],
                    affected_components=["tests"],
                    attributes={"percent_covered": pct},
                    reasoning_summary="Measured by coverage.py during the real test run.",
                    recommended_action="Raise coverage on critical modules first.",
                ),
                [
                    EvidenceDraft(
                        source_type=SourceType.TEST,
                        source="coverage.py json report",
                        tool="coverage",
                        excerpt=f"total {pct:.1f}%",
                        confidence=0.95,
                        data={"totals": totals},
                    )
                ],
            )

    def _dependency_coverage(self, ctx: AgentContext) -> None:
        focus = ctx.task.focus
        package = focus.get("package", "")
        import_name = (focus.get("import_name") or package).split(".")[0]
        graph = ctx.tool("build_import_graph", ImportGraph, ctx.tools)
        users = [f for f in graph.files_importing_external(import_name) if not is_test_path(f)]
        tests = [f for f in ctx.tools.list_files(suffixes=(".py",)) if is_test_path(f)]
        tested: set[str] = set()
        for t in tests:
            tested |= graph.imports.get(t, set())
        untested_users = [u for u in users if u not in tested]
        existing = [
            f
            for f in ctx.findings(category="testing")
            if f.rule_id == "testing.untested_critical_path" and set(f.affected_files) & set(untested_users)
        ]
        if not users:
            ctx.message("orchestrator", f"No production code imports {import_name}; nothing to cover", payload={"package": package})
            return
        if not untested_users:
            ctx.message("orchestrator", f"All modules using {package} are imported by tests", payload={"package": package, "users": users})
            return
        note = f"Code using {package} ({', '.join(untested_users)}) is not exercised by any test — an upgrade of {package} would ship without regression tests"
        draft = EvidenceDraft(
            source_type=SourceType.STATIC_ANALYSIS,
            source="test import graph (dependency follow-up)",
            tool="skopeo-import-graph",
            file=untested_users[0],
            excerpt=note,
            confidence=0.85,
            data={"package": package, "untested_users": untested_users, "tests_considered": len(tests)},
        )
        if existing:
            target = existing[0]
            ctx.attach_evidence(
                target.finding_id, draft, f"Linked untested {target.attributes.get('component')} code to dependency {package}"
            )
            related = sorted(set(target.attributes.get("related_packages", [])) | {package})
            ctx.store.update_finding(target.finding_id, attributes={"related_packages": related})
            ctx.message(
                "orchestrator",
                note + " (evidence added to existing finding)",
                payload={"finding_id": target.finding_id, "package": package},
            )
            return
        ctx.publish(
            FindingDraft(
                category=Category.TESTING,
                rule_id="testing.untested_dependency_usage",
                title=f"Code that uses {package} has no tests ({', '.join(untested_users[:3])})",
                description=note,
                severity=Severity.MEDIUM,
                subject=f"untested-dep:{package}",
                affected_files=untested_users,
                affected_components=sorted({c for f in untested_users for c in components_for(f)}),
                attributes={"package": package, "untested_files": untested_users, "related_packages": [package]},
                reasoning_summary="Follow-up from orchestrator: static test-to-code mapping for modules importing the dependency.",
                recommended_action=f"Add tests around {package} usage before upgrading it.",
            ),
            [draft],
        )
