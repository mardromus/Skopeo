"""Performance Agent — static suspects (N+1 queries, network calls in loops, ...) and measured
benchmarks.

It strictly distinguishes:
* STATIC SUSPECT  — a pattern seen in code (``attributes.measurement = "static_suspect"``);
* MEASURED ISSUE  — confirmed by a benchmark that actually ran (``"measured"``).
A performance problem is never reported as measured unless a benchmark executed and its output
was parsed.
"""

from __future__ import annotations

import json
from typing import Any

from app.agents.base import AgentContext, SpecialistAgent, Step
from app.agents.common import components_for, excerpt
from app.schemas import Category, EvidenceDraft, FindingDraft, Severity, SourceType
from app.tools.python_ast import call_sites, import_aliases, iter_functions, parse_python, resolve_call

_DB_METHODS = {"execute", "executemany", "query", "filter", "get", "all", "first", "fetchall", "scalar", "scalars"}
_DB_RECEIVER_HINTS = ("conn", "connection", "cursor", "cur", "session", "db", "engine", "objects")


def _is_db_receiver(receiver: str) -> bool:
    return any(receiver == h or receiver.endswith("_" + h) or receiver.startswith(h + "_") for h in _DB_RECEIVER_HINTS)


_HTTP_PREFIXES = ("requests.", "httpx.", "urllib.request.urlopen", "aiohttp.", "session.get", "session.post", "client.get", "client.post")


class PerformanceAgent(SpecialistAgent):
    name = "performance_agent"
    display_name = "Performance Agent"
    category = "performance"
    description = "Static performance suspects (N+1, network in loops, regex compile in loops) and benchmark-based measurement."
    modes = {
        "full": "static analysis plus benchmarks for discovered suspects",
        "benchmark": "measure specific suspects by running benchmark harnesses",
    }

    def fallback_strategy(self, error_type: str, current_strategy: str) -> str | None:
        if error_type == "ToolUnavailableError":
            return "static_only"
        return None

    def plan(self, ctx: AgentContext) -> list[Step]:
        if ctx.task.mode == "benchmark":
            return [("run benchmarks for requested suspects", self._benchmark_requested)]
        steps: list[Step] = []
        if ctx.task.strategy != "static_only":
            steps.append(("initialise benchmark/profiling harness", self._init_harness))
        steps.append(("detect static performance suspects (AST)", self._static))
        if ctx.task.strategy == "static_only":
            ctx.limitation("Degraded strategy 'static_only': no benchmarks or profiling in this run")
        return steps

    # ------------------------------------------------------------- harness
    def _init_harness(self, ctx: AgentContext) -> None:
        # Fault-injection point: a missing harness makes this agent FAIL (fault isolation demo).
        ctx.require_tool("benchmark harness")
        self.harness_ready = bool(ctx.profile.get("trusted_execution"))
        if not self.harness_ready:
            ctx.limitation("Benchmarks not executed: untrusted repository code (static analysis only)")

    # -------------------------------------------------------------- static
    def _static(self, ctx: AgentContext) -> list[Step] | None:
        suspects: list[dict[str, Any]] = []
        for rel in ctx.tools.list_files(suffixes=(".py",), include_tests=False):
            if rel.startswith(("benchmarks/", "bench/")):
                continue
            text = ctx.tools.try_get_file(rel) or ""
            tree = parse_python(text, rel)
            if tree is None:
                continue
            lines = text.splitlines()
            aliases = import_aliases(tree)
            fns = {f.name: f for f in iter_functions(tree, rel)}
            for site in call_sites(tree):
                if not site.in_loop:
                    continue
                full = resolve_call(site.dotted, aliases)
                method = site.dotted.split(".")[-1]
                receiver = site.dotted.split(".")[0].lower()
                kind = None
                if method in _DB_METHODS and (_is_db_receiver(receiver) or ".objects." in site.dotted):
                    kind = ("performance.n_plus_one", Severity.MEDIUM, "Database query executed inside a loop (N+1 pattern)", None)
                elif full.startswith(_HTTP_PREFIXES):
                    kind = ("performance.network_in_loop", Severity.MEDIUM, "Blocking network call inside a loop", full.split(".")[0])
                elif full == "re.compile":
                    kind = ("performance.regex_compile_in_loop", Severity.LOW, "Regular expression compiled inside a loop", None)
                if kind:
                    fn = fns.get(site.function or "")
                    suspects.append(
                        {
                            "rule": kind[0],
                            "severity": kind[1],
                            "title": kind[2],
                            "package": kind[3],
                            "file": rel,
                            "line": site.lineno,
                            "end": site.end_lineno,
                            "loop_line": site.loop_lineno,
                            "call": full,
                            "function": site.function,
                            "fn": fn,
                            "lines": lines,
                        }
                    )
        seen: set[tuple[str, str, str | None]] = set()
        published = []
        for s in suspects:
            key = (s["rule"], s["file"], s["function"])
            if key in seen:
                continue
            seen.add(key)
            fn = s["fn"]
            subject = f"py:{s['file']}::{s['function']}" if s["function"] else f"perf:{s['file']}:{s['line']}"
            finding = ctx.publish(
                FindingDraft(
                    category=Category.PERFORMANCE,
                    rule_id=s["rule"],
                    title=f"{s['title']} in {s['function'] or 'module'}() ({s['file']}) — STATIC SUSPECT",
                    description=(
                        f"`{s['call']}` at line {s['line']} runs once per iteration of the loop at line {s['loop_line']}. "
                        "Cost grows linearly with the number of iterations. Not measured yet."
                    ),
                    severity=s["severity"],
                    subject=subject,
                    affected_files=[s["file"]],
                    affected_components=components_for(s["file"]),
                    attributes={
                        "measurement": "static_suspect",
                        "function": s["function"],
                        "call": s["call"],
                        "loop_line": s["loop_line"],
                        **({"package": s["package"]} if s["package"] else {}),
                    },
                    reasoning_summary="AST shows the call inside a loop body; impact depends on iteration counts, which static analysis cannot know.",
                    recommended_action=_FIXES.get(s["rule"], "Hoist the call out of the loop or batch it."),
                ),
                [
                    EvidenceDraft(
                        source_type=SourceType.STATIC_ANALYSIS,
                        source=f"{s['file']}:{s['loop_line']}-{s['end']}",
                        tool="skopeo-python-ast",
                        file=s["file"],
                        line_start=s["loop_line"],
                        line_end=s["end"],
                        excerpt=excerpt(s["lines"], s["loop_line"], s["end"]),
                        confidence=0.75,
                        data={"call": s["call"], "function": s["function"], "function_lines": [fn.lineno, fn.end_lineno] if fn else None},
                    )
                ],
            )
            published.append(finding)
        ctx.analyzed(f"Static performance analysis: {len(published)} suspect(s)")
        if published and getattr(self, "harness_ready", False):
            return [("benchmark discovered suspects", lambda c: self._benchmark(c, published))]
        return None

    # ----------------------------------------------------------- benchmarks
    def _benchmark_requested(self, ctx: AgentContext) -> None:
        ids = ctx.task.focus.get("finding_ids") or []
        findings = [f for f in (ctx.store.get_finding(i) for i in ids) if f is not None]
        if not findings:
            ctx.limitation("Benchmark requested but no target findings were supplied")
            return
        if not ctx.profile.get("trusted_execution"):
            ctx.limitation("Benchmark requested but repository code is untrusted — INSUFFICIENT EVIDENCE")
            ctx.message(
                "verification_agent", "Cannot benchmark untrusted code; findings remain static suspects", payload={"finding_ids": ids}
            )
            return
        self._benchmark(ctx, findings)

    def _find_harness(self, ctx: AgentContext, function: str | None, file: str) -> str | None:
        module = file[:-3].replace("/", ".") if file.endswith(".py") else file
        for script in ctx.profile.get("benchmark_scripts") or []:
            text = ctx.tools.try_get_file(script) or ""
            if function and function in text and (module.split(".")[-1] in text or module in text):
                return script
        return None

    def _benchmark(self, ctx: AgentContext, findings: list) -> None:
        for finding in findings:
            fn = finding.attributes.get("function")
            file = finding.affected_files[0] if finding.affected_files else ""
            script = self._find_harness(ctx, fn, file)
            if script is None:
                ctx.message(
                    "verification_agent",
                    f"INSUFFICIENT EVIDENCE: no benchmark harness exercises {fn}() in {file}; finding stays a static suspect",
                    payload={"finding_id": finding.finding_id},
                    severity="warning",
                )
                ctx.limitation(f"No benchmark harness for {fn}() ({file})")
                continue
            ctx.require_tool("benchmark harness")
            result = ctx.tool("run_benchmark", ctx.tools.run_benchmark, script)
            summary = result.summary(800)
            ctx.record_tool_result(summary)
            payload = None
            for line in reversed(result.stdout.strip().splitlines()):
                try:
                    payload = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
            if not result.ok or not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                ctx.message(
                    "verification_agent",
                    f"Benchmark {script} did not produce parseable results (exit {result.exit_code}); no measurement recorded",
                    payload=summary,
                    severity="warning",
                )
                ctx.limitation(f"Benchmark {script} output unusable")
                continue
            results = [r for r in payload["results"] if isinstance(r, dict) and r.get("n")]
            verdict = _analyse(results)
            draft = EvidenceDraft(
                source_type=SourceType.BENCHMARK,
                source=f"{summary['command']} (exit {result.exit_code}, {result.duration_ms} ms)",
                tool="skopeo-benchmark-runner",
                file=script,
                excerpt="; ".join(f"n={r['n']}: {r.get('queries', '?')} queries, {r.get('seconds', '?')}s" for r in results)[:600],
                raw_reference=result.stdout[-1500:],
                confidence=0.95,
                data={"results": results, "verdict": verdict},
            )
            measurement = "measured" if verdict["confirmed"] else "measured_no_issue"
            ctx.attach_evidence(
                finding.finding_id,
                draft,
                f"Benchmark {script}: {verdict['summary']}",
                reproduced=verdict["confirmed"],
                static_suspect=False,
            )
            title = finding.title.replace("— STATIC SUSPECT", "— MEASURED" if verdict["confirmed"] else "— MEASURED (no issue)")
            ctx.store.update_finding(
                finding.finding_id,
                title=title,
                attributes={"measurement": measurement, "benchmark": {"script": script, "results": results, "verdict": verdict}},
            )
            ctx.message(
                "verification_agent",
                f"Benchmark for {fn}(): {verdict['summary']}",
                payload={"finding_id": finding.finding_id, "measurement": measurement, "results": results},
            )


def _analyse(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Decide from measured numbers whether cost scales with input size (N+1 / linear calls)."""
    if len(results) < 2:
        return {"confirmed": False, "summary": "fewer than two data points — cannot judge scaling"}
    results = sorted(results, key=lambda r: r["n"])
    first, last = results[0], results[-1]
    growth_n = last["n"] / max(1, first["n"])
    if "queries" in first and "queries" in last:
        per_row = [r["queries"] / max(1, r["n"]) for r in results]
        q_growth = last["queries"] / max(1, first["queries"])
        confirmed = min(per_row) >= 0.9 and q_growth >= 0.8 * growth_n
        return {
            "confirmed": confirmed,
            "query_growth": round(q_growth, 2),
            "input_growth": round(growth_n, 2),
            "queries_per_row": [round(x, 3) for x in per_row],
            "summary": (
                f"query count grows linearly with rows ({first['queries']} queries at n={first['n']} -> {last['queries']} at n={last['n']}); N+1 confirmed"
                if confirmed
                else f"query count does not scale with rows ({first['queries']} -> {last['queries']})"
            ),
        }
    t_growth = last.get("seconds", 0) / max(1e-9, first.get("seconds", 0) or 1e-9)
    confirmed = t_growth >= 0.8 * growth_n
    return {
        "confirmed": confirmed,
        "time_growth": round(t_growth, 2),
        "input_growth": round(growth_n, 2),
        "summary": f"time grew {t_growth:.1f}x for {growth_n:.0f}x input",
    }


_FIXES = {
    "performance.n_plus_one": "Fetch related rows in one query (JOIN or WHERE id IN (...)) and group in memory.",
    "performance.network_in_loop": "Batch the requests (bulk endpoint) or run them concurrently with a bounded pool; reuse a Session.",
    "performance.regex_compile_in_loop": "Compile the regular expression once at module level.",
}
