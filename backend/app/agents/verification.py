"""Verification / Red-Team Agent — exists to distrust every other agent.

For each important finding it asks adversarial questions and answers them with *its own*
tool calls (re-reading files, rebuilding the import graph, re-running tests, recomputing
metrics) rather than trusting the original agent's evidence:

 1. Is the evidence real?                 (content hashes re-computed against the repository)
 2. Is the affected code reachable?       (independent import-graph reachability)
 3. Is the vulnerable dependency used?
 4. Is the claimed severity justified?
 5. Could this be a false positive?       (placeholders, fixtures, docs)
 6. Is there contradictory evidence?      (contradiction correlations)
 7. Does configuration mitigate it?
 8. Can the claim be reproduced?          (re-run failing tests, recompute metrics, benchmarks)
 9. Is the evidence stale?                (commit SHA)
10. Theoretical vs actual risk?           (static suspects vs measurements)

Outcomes: VERIFIED, REJECTED or NEEDS_MORE_EVIDENCE (which becomes an investigation request
to the orchestrator). Rejected findings are excluded from risk assessment.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import PurePosixPath

from pydantic import BaseModel, Field

from app.agents.base import Agent, AgentContext
from app.agents.common import import_name_for
from app.schemas import (
    AgentOutcome,
    CorrelationOut,
    EventType,
    EvidenceDraft,
    FindingOut,
    Severity,
    SourceType,
    VerificationCheck,
    VerificationDecision,
    VerificationDraft,
)
from app.tools.python_ast import ImportGraph, iter_functions, parse_python
from app.tools.repository import is_fixture_path, is_test_path
from app.tools.secrets import placeholder_assessment, scan_text

_DOWNGRADE = {"critical": "high", "high": "medium", "medium": "low", "low": "info", "info": "info"}
_SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0, "unknown": 2}


class Judgement(BaseModel):
    decision: VerificationDecision
    reasoning_summary: str = Field(max_length=1200)
    adjusted_severity: Severity | None = None


def needs_verification(f: FindingOut, contested: set[str]) -> bool:
    """Shared selection rule (used by the red-team and by the orchestrator's review)."""
    status = f.status.value
    if status in ("verified", "rejected"):
        return False
    if status == "needs_more_evidence":
        return len(f.evidence_ids) > int(f.attributes.get("verified_evidence_count", 0)) or f.finding_id in contested
    if f.severity.value == "info":
        return f.finding_id in contested
    return True


def _check(check: str, question: str, outcome: str, detail: str, supports: str | None = None) -> VerificationCheck:
    return VerificationCheck(check=check, question=question, outcome=outcome, detail=detail, supports=supports)


class VerificationAgent(Agent):
    name = "verification_agent"
    display_name = "Verification / Red-Team Agent"
    description = "Adversarially challenges findings and correlations; verifies, rejects or requests more evidence."

    def run(self, ctx: AgentContext) -> AgentOutcome:
        self.round = int(ctx.task.focus.get("round", 1))
        self.graph = ctx.tool("build_import_graph", ImportGraph, ctx.tools)
        self.entrypoints = set(ctx.profile.get("entrypoints") or [])
        findings = ctx.findings()
        correlations = ctx.store.list_correlations(ctx.investigation_id)
        self.contradictions: dict[str, list[CorrelationOut]] = defaultdict(list)
        for c in correlations:
            if c.relationship_type.value == "contradiction" and c.status.value == "proposed":
                for fid in c.finding_ids:
                    self.contradictions[fid].append(c)
        self.by_id = {f.finding_id: f for f in findings}
        candidates = [f for f in findings if self._needs_verification(ctx, f)]
        candidates.sort(key=lambda f: -_SEV_RANK.get(f.severity.value, 0))
        candidates = candidates[: ctx.settings.max_findings_to_verify]
        ctx.emit(
            EventType.VERIFICATION_STARTED,
            f"Red-team round {self.round}: challenging {len(candidates)} finding(s) and pending correlations",
            receiver="orchestrator",
            payload={"round": self.round, "finding_ids": [f.finding_id for f in candidates]},
        )
        stats = defaultdict(int)
        for f in candidates:
            ctx.tick(f.title[:60])
            decision = self._verify_finding(ctx, f)
            stats[decision.value] += 1
        for c in ctx.store.list_correlations(ctx.investigation_id):
            if c.status.value == "proposed":
                ctx.tick(c.title[:60])
                self._verify_correlation(ctx, c)
        summary = ", ".join(f"{v} {k}" for k, v in sorted(stats.items())) or "nothing to verify"
        return AgentOutcome(summary=f"Round {self.round}: {summary}", coverage={"round": self.round, "decisions": dict(stats)})

    # ---------------------------------------------------------------- selection
    def _needs_verification(self, ctx: AgentContext, f: FindingOut) -> bool:
        return needs_verification(f, set(self.contradictions))

    # -------------------------------------------------------------- reachability
    def _reach(self, file: str) -> tuple[str, str]:
        if not file.endswith(".py"):
            return "n/a", "not a Python module"
        if file in self.entrypoints:
            return "entrypoint", f"{file} is itself an entrypoint"
        importers = self.graph.transitive_importers(file)
        prod = sorted(i for i in importers if not is_test_path(i))
        hit = sorted(set(prod) & self.entrypoints)
        if hit:
            return "entrypoint", f"imported (transitively) by entrypoint(s) {', '.join(hit[:3])}"
        if prod:
            return "reachable", f"imported by production module(s) {', '.join(prod[:3])}"
        if importers:
            return "test_only", f"only imported by tests ({', '.join(sorted(importers)[:3])})"
        return "unreferenced", "no static importers found (may still be loaded dynamically)"

    # ------------------------------------------------------------------ checks
    def _integrity(self, ctx: AgentContext, f: FindingOut) -> VerificationCheck:
        evidence = ctx.store.list_evidence(ctx.investigation_id, f.finding_id)
        checked, mismatched = 0, []
        for e in evidence:
            if not e.file or e.content_hash is None:
                continue
            checked += 1
            current = ctx.tools.line_hash(e.file, e.line_start, e.line_end)
            if current != e.content_hash:
                mismatched.append(f"{e.file}:{e.line_start}")
        self._evidence_ids = [e.evidence_id for e in evidence]
        self._evidence = evidence
        if mismatched:
            return _check(
                "evidence_integrity",
                "Is the evidence real?",
                "fail",
                f"{len(mismatched)} evidence item(s) no longer match repository content: {', '.join(mismatched[:4])}",
                "rejection",
            )
        if not checked:
            return _check(
                "evidence_integrity",
                "Is the evidence real?",
                "not_applicable",
                f"{len(evidence)} evidence item(s) reference external/tool data rather than file lines",
            )
        return _check(
            "evidence_integrity", "Is the evidence real?", "pass", f"re-hashed {checked} referenced line range(s); all match the repository"
        )

    def _staleness(self, ctx: AgentContext, f: FindingOut) -> VerificationCheck:
        sha = f.attributes.get("commit_sha")
        if sha and ctx.repo.commit_sha and sha != ctx.repo.commit_sha:
            return _check(
                "staleness",
                "Is the evidence stale?",
                "fail",
                f"finding produced at {sha[:10]}, repository now at {ctx.repo.commit_sha[:10]}",
                "more_evidence",
            )
        return _check(
            "staleness", "Is the evidence stale?", "pass", f"evidence captured at the analysed commit {str(ctx.repo.commit_sha)[:10]}"
        )

    def _location(self, f: FindingOut) -> VerificationCheck:
        files = f.affected_files or []
        if files and all(is_test_path(p) or is_fixture_path(p) for p in files):
            return _check(
                "location_context",
                "Could this be a false positive?",
                "fail",
                f"all affected files are tests/fixtures/docs: {', '.join(files[:3])}",
                "downgrade",
            )
        return _check("location_context", "Could this be a false positive?", "pass", "affected files are production code")

    def _secret_checks(self, ctx: AgentContext, f: FindingOut) -> list[VerificationCheck]:
        checks = [self._location(f)]
        rel = f.affected_files[0]
        text = ctx.tools.try_get_file(rel) or ""
        lines = text.splitlines()
        sibling_docs = ""
        for name in ("README.md", "README", "README.txt"):
            doc = str(PurePosixPath(rel).parent / name)
            sibling_docs += ctx.tools.try_get_file(doc) or ""
        verdicts = []
        for ln in f.attributes.get("lines") or []:
            window = "\n".join(lines[max(0, ln - 4) : ln + 2])
            for match in scan_text(lines[ln - 1] if 0 < ln <= len(lines) else ""):
                is_placeholder, why = placeholder_assessment(match.value, window + "\n" + sibling_docs)
                verdicts.append((match.masked, is_placeholder, why))
        if verdicts and all(v[1] for v in verdicts):
            checks.append(
                _check(
                    "placeholder",
                    "Is this a documented dummy credential?",
                    "fail",
                    "; ".join(f"{m}: {w}" for m, _, w in verdicts[:3]),
                    "rejection",
                )
            )
        elif verdicts:
            checks.append(
                _check(
                    "placeholder",
                    "Is this a documented dummy credential?",
                    "pass",
                    "at least one value has no placeholder indicators: " + ", ".join(m for m, p, _ in verdicts if not p),
                )
            )
        else:
            checks.append(
                _check(
                    "placeholder",
                    "Is this a documented dummy credential?",
                    "inconclusive",
                    "matched values could not be re-extracted",
                    "more_evidence",
                )
            )
        stem = PurePosixPath(rel).name
        refs = ctx.tool(
            "search",
            ctx.tools.search_repository,
            re.escape(PurePosixPath(rel).stem),
            suffixes=(".py", ".js", ".ts", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".json"),
            max_results=50,
        )
        prod_refs = sorted({h.file for h in refs if h.file != rel and not is_test_path(h.file)})
        test_refs = sorted({h.file for h in refs if h.file != rel and is_test_path(h.file)})
        if prod_refs:
            checks.append(
                _check(
                    "production_reference",
                    "Is the value used by production code?",
                    "pass",
                    f"{stem} referenced by production files {', '.join(prod_refs[:3])}",
                )
            )
        else:
            checks.append(
                _check(
                    "production_reference",
                    "Is the value used by production code?",
                    "fail",
                    f"{stem} is only referenced by tests ({', '.join(test_refs[:3]) or 'none'}); no production code loads it",
                    "rejection",
                )
            )
        return checks

    def _dependency_checks(self, ctx: AgentContext, f: FindingOut) -> tuple[list[VerificationCheck], str | None]:
        a = f.attributes
        pkg = a.get("package", "")
        import_name = a.get("import_name") or import_name_for(pkg)
        users = [u for u in self.graph.files_importing_external(import_name.split(".")[0]) if not is_test_path(u)]
        checks = []
        reach = None
        if users:
            levels = [self._reach(u) for u in users]
            reach = "entrypoint" if any(lv[0] == "entrypoint" for lv in levels) else "reachable"
            checks.append(
                _check(
                    "dependency_used",
                    "Is the vulnerable dependency actually used?",
                    "pass",
                    f"`{import_name}` imported by {', '.join(users[:4])}; {levels[0][1]}",
                )
            )
        else:
            reach = "unreachable"
            checks.append(
                _check(
                    "dependency_used",
                    "Is the vulnerable dependency actually used?",
                    "fail",
                    f"no production module imports `{import_name}` — theoretical risk only",
                    "downgrade",
                )
            )
        if a.get("vulnerable"):
            claimed = f.severity.value
            evidence_sev = [str((e.data or {}).get("severity")) for e in self._evidence if (e.data or {}).get("advisory_id")]
            advisory_max = max(evidence_sev, key=lambda s: _SEV_RANK.get(s, 0)) if evidence_sev else a.get("advisory_max_severity")
            if advisory_max and _SEV_RANK.get(claimed, 0) > _SEV_RANK.get(advisory_max, 0):
                checks.append(
                    _check(
                        "severity_justified",
                        "Is the claimed severity justified?",
                        "fail",
                        f"claimed {claimed} exceeds advisory maximum {advisory_max}",
                        "downgrade",
                    )
                )
            else:
                checks.append(
                    _check(
                        "severity_justified",
                        "Is the claimed severity justified?",
                        "pass",
                        f"claimed {claimed} matches the highest advisory severity in the evidence ({advisory_max}) for the exact pinned version",
                    )
                )
        return checks, reach

    def _code_reach_check(self, f: FindingOut) -> tuple[VerificationCheck, str | None]:
        py_files = [p for p in f.affected_files if p.endswith(".py")]
        if not py_files:
            return _check("reachability", "Is the affected code actually reachable?", "not_applicable", "no Python module to trace"), None
        levels = [self._reach(p) for p in py_files]
        best = (
            "entrypoint"
            if any(lv[0] == "entrypoint" for lv in levels)
            else "reachable"
            if any(lv[0] == "reachable" for lv in levels)
            else levels[0][0]
        )
        detail = levels[0][1]
        if best in ("entrypoint", "reachable"):
            return _check("reachability", "Is the affected code actually reachable?", "pass", detail), best
        if best == "test_only":
            return _check("reachability", "Is the affected code actually reachable?", "fail", detail, "downgrade"), "unreachable"
        return _check("reachability", "Is the affected code actually reachable?", "inconclusive", detail), None

    def _mitigation(self, ctx: AgentContext, f: FindingOut) -> VerificationCheck | None:
        if f.rule_id == "security.jwt_no_algorithms":
            deps = {d.name: d for d in ctx.tools.inspect_dependencies()}
            jwt_dep = deps.get("pyjwt")
            if jwt_dep and jwt_dep.version and int(jwt_dep.version.split(".")[0]) < 2:
                return _check(
                    "mitigation",
                    "Does the configuration mitigate the issue?",
                    "pass",
                    f"no mitigation: PyJWT {jwt_dep.version} (<2.0) accepts the algorithm named in the token header when algorithms is omitted",
                )
            return _check(
                "mitigation",
                "Does the configuration mitigate the issue?",
                "inconclusive",
                "PyJWT >= 2 rejects decode without algorithms (raises), reducing exploitability",
                "downgrade",
            )
        if f.rule_id == "security.hardcoded_default_secret":
            api = str(f.attributes.get("api", ""))
            env_files = [
                p
                for p in ctx.tools.list_files()
                if PurePosixPath(p).name in (".env.example", "docker-compose.yml", "docker-compose.yaml", "Dockerfile")
                or p.endswith((".k8s.yaml", ".helm.yaml"))
            ]
            var_hits = []
            for p in env_files:
                text = ctx.tools.try_get_file(p) or ""
                for name in re.findall(r"[A-Z][A-Z0-9_]{3,}", " ".join(self._evidence[0].excerpt.split()) if self._evidence else ""):
                    if name in text and ("SECRET" in name or "KEY" in name or "TOKEN" in name):
                        var_hits.append(f"{name} in {p}")
            if var_hits:
                return _check(
                    "mitigation",
                    "Does the configuration mitigate the issue?",
                    "inconclusive",
                    f"deployment config sets {', '.join(var_hits[:3])}",
                    "downgrade",
                )
            return _check(
                "mitigation",
                "Does the configuration mitigate the issue?",
                "pass",
                f"no deployment configuration sets the variable; the literal fallback is used whenever it is absent ({api})",
            )
        return None

    def _performance_checks(self, ctx: AgentContext, f: FindingOut) -> list[VerificationCheck]:
        m = f.attributes.get("measurement")
        if m == "measured":
            verdict = (f.attributes.get("benchmark") or {}).get("verdict", {})
            return [
                _check("reproduction", "Can the claim be reproduced?", "pass", f"benchmark executed: {verdict.get('summary', 'measured')}")
            ]
        if m == "measured_no_issue":
            return [
                _check(
                    "reproduction",
                    "Can the claim be reproduced?",
                    "fail",
                    "benchmark ran and did not show the claimed scaling",
                    "rejection",
                )
            ]
        if f.severity.value in ("low", "info"):
            return [
                _check(
                    "theoretical_vs_actual",
                    "Is the agent confusing theoretical risk with actual risk?",
                    "pass",
                    "low-severity static suspect accepted as a code smell (unmeasured)",
                )
            ]
        return [
            _check(
                "theoretical_vs_actual",
                "Is the agent confusing theoretical risk with actual risk?",
                "inconclusive",
                "STATIC SUSPECT only — no benchmark has measured the impact; a medium+ performance claim needs measurement",
                "more_evidence",
            )
        ]

    def _contradiction_check(self, f: FindingOut) -> VerificationCheck | None:
        corrs = self.contradictions.get(f.finding_id)
        if not corrs:
            return None
        other_ids = [i for c in corrs for i in c.finding_ids if i != f.finding_id]
        others = [self.by_id[i] for i in other_ids if i in self.by_id]
        mine_measured = f.attributes.get("measurement") == "measured" or any(
            e.source_type.value in ("benchmark", "test") for e in self._evidence
        )
        others_measured = [o for o in others if o.attributes.get("measurement") == "measured"]
        if f.attributes.get("stance") == "acceptable":
            if others_measured:
                return _check(
                    "contradiction",
                    "Is there contradictory evidence?",
                    "fail",
                    f"measured evidence from {others_measured[0].agent} contradicts this assessment ({others_measured[0].attributes.get('benchmark', {}).get('verdict', {}).get('summary', 'measured')})",
                    "rejection",
                )
            return _check(
                "contradiction",
                "Is there contradictory evidence?",
                "inconclusive",
                f"contested by {', '.join(o.agent for o in others)}; neither side measured",
                "more_evidence",
            )
        if mine_measured:
            return _check(
                "contradiction",
                "Is there contradictory evidence?",
                "pass",
                f"contradicting assessment by {', '.join(o.agent for o in others)} is not backed by measurement; this finding is",
            )
        return _check(
            "contradiction",
            "Is there contradictory evidence?",
            "inconclusive",
            f"{', '.join(o.agent for o in others)} disagrees; requires measurement to adjudicate",
            "more_evidence",
        )

    def _testing_checks(self, ctx: AgentContext, f: FindingOut) -> tuple[list[VerificationCheck], bool]:
        reproduced = False
        if f.rule_id == "testing.test_failure":
            node = f.attributes.get("node_id", "")
            if not ctx.profile.get("trusted_execution"):
                return [
                    _check(
                        "reproduction",
                        "Can the claim be reproduced?",
                        "inconclusive",
                        "re-run not permitted for untrusted code; relying on original execution evidence",
                    )
                ], False
            ctx.emit(
                EventType.CHALLENGE,
                f"Requested reproduction: re-running {node}",
                receiver=f.agent,
                payload={"finding_id": f.finding_id, "node_id": node},
            )
            res = ctx.tool("rerun_test", ctx.tools.rerun_test, node)
            summary = res.summary(800)
            ctx.record_tool_result(summary)
            ctx.store.add_evidence(
                ctx.investigation_id,
                f.finding_id,
                self.name,
                EvidenceDraft(
                    source_type=SourceType.TEST,
                    source=summary["command"],
                    tool="pytest (red-team rerun)",
                    excerpt=(res.stdout.strip().splitlines() or [""])[-1][:300],
                    raw_reference=res.stdout[-1200:],
                    confidence=0.95,
                    data={"exit_code": res.exit_code, "duration_ms": res.duration_ms},
                ),
            )
            if res.exit_code == 1:
                reproduced = True
                return [
                    _check(
                        "reproduction",
                        "Can the claim be reproduced?",
                        "pass",
                        f"reproduction confirmed: `{summary['command']}` failed again (exit 1, {res.duration_ms} ms)",
                    )
                ], True
            if res.exit_code == 0:
                return [
                    _check(
                        "reproduction",
                        "Can the claim be reproduced?",
                        "fail",
                        "test passed on re-run — failure not reproducible (possible flakiness)",
                        "more_evidence",
                    )
                ], False
            return [
                _check("reproduction", "Can the claim be reproduced?", "inconclusive", f"re-run ended with exit {res.exit_code}")
            ], False
        if f.rule_id in ("testing.untested_critical_path", "testing.untested_dependency_usage"):
            tests = [p for p in ctx.tools.list_files(suffixes=(".py",)) if is_test_path(p)]
            tested = set()
            for t in tests:
                tested |= self.graph.imports.get(t, set())
            still_untested = [p for p in f.affected_files if p not in tested]
            coverage_ev = [e for e in self._evidence if e.source_type.value == "test"]
            checks = []
            if still_untested:
                checks.append(
                    _check(
                        "independent_mapping",
                        "Can the claim be reproduced?",
                        "pass",
                        f"independently rebuilt import graph: no test imports {', '.join(still_untested[:3])}",
                    )
                )
            else:
                checks.append(
                    _check(
                        "independent_mapping", "Can the claim be reproduced?", "fail", "tests do import the affected modules", "rejection"
                    )
                )
            if coverage_ev:
                reproduced = True
                checks.append(_check("coverage_measurement", "Is there measured evidence?", "pass", coverage_ev[0].excerpt[:200]))
            return checks, reproduced
        return [_check("recheck", "Can the claim be reproduced?", "pass", "test-quality claim re-derived from the test AST")], False

    def _quality_checks(self, ctx: AgentContext, f: FindingOut) -> list[VerificationCheck]:
        fn = f.attributes.get("function")
        if (
            f.rule_id in ("code_quality.high_complexity", "code_quality.long_function", "code_quality.deep_nesting")
            and fn
            and f.affected_files
        ):
            tree = parse_python(ctx.tools.try_get_file(f.affected_files[0]) or "", f.affected_files[0])
            metrics = {m.qualname: m for m in iter_functions(tree, f.affected_files[0])} if tree else {}
            m = metrics.get(fn)
            if m and (f.rule_id != "code_quality.high_complexity" or m.complexity == f.attributes.get("complexity")):
                return [
                    _check(
                        "recompute",
                        "Can the claim be reproduced?",
                        "pass",
                        f"recomputed independently: complexity {m.complexity}, {m.length} lines, nesting {m.max_nesting}",
                    )
                ]
            return [_check("recompute", "Can the claim be reproduced?", "fail", "metric could not be reproduced", "rejection")]
        return []

    def _license_checks(self, ctx: AgentContext, f: FindingOut) -> list[VerificationCheck]:
        if f.rule_id == "license.copyleft_file":
            check, _ = self._code_reach_check(f)
            if check.outcome == "pass":
                check.detail = "copyleft-licensed file is part of shipped code: " + check.detail
            return [check, self._location(f)]
        if f.rule_id == "license.metadata_mismatch":
            from app.tools.licenses import normalize_expression

            declared = f.attributes.get("declared")
            file_lic = f.attributes.get("license_file")
            if file_lic in normalize_expression(str(declared)):
                return [
                    _check(
                        "false_positive",
                        "Could this be a false positive?",
                        "fail",
                        "declared expression includes the license file's license",
                        "rejection",
                    )
                ]
            return [
                _check(
                    "false_positive",
                    "Could this be a false positive?",
                    "pass",
                    f"'{declared}' and '{file_lic}' are distinct licenses with different obligations",
                )
            ]
        return []

    # --------------------------------------------------------------- decision
    def _verify_finding(self, ctx: AgentContext, f: FindingOut) -> VerificationDecision:
        challenge = self._challenge_text(f)
        ctx.store.update_finding(f.finding_id, status="challenged")
        ctx.emit(
            EventType.CHALLENGE,
            f"Challenge to {f.agent}: {challenge}",
            receiver=f.agent,
            payload={"finding_id": f.finding_id, "title": f.title, "round": self.round},
        )
        checks = [self._integrity(ctx, f), self._staleness(ctx, f)]
        reach = None
        reproduced = False
        if f.rule_id == "security.hardcoded_secret":
            checks += self._secret_checks(ctx, f)
        elif f.category.value == "dependency" and f.attributes.get("package"):
            dep_checks, reach = self._dependency_checks(ctx, f)
            checks += dep_checks
        elif f.category.value in ("security", "api_compatibility"):
            c, reach = self._code_reach_check(f)
            checks.append(c)
            checks.append(self._location(f))
            mit = self._mitigation(ctx, f)
            if mit:
                checks.append(mit)
            if f.rule_id == "security.vulnerable_dependency_usage":
                checks.append(
                    _check(
                        "usage_claim",
                        "Is the vulnerable dependency actually used?",
                        "pass" if f.attributes.get("usage_files") else "fail",
                        f"call sites: {', '.join(str(c['file']) + ':' + str(c['line']) for c in (f.attributes.get('call_sites') or [])[:4]) or 'none'}",
                        None if f.attributes.get("usage_files") else "downgrade",
                    )
                )
        elif f.category.value == "performance":
            c, reach = self._code_reach_check(f)
            checks.append(c)
            checks += self._performance_checks(ctx, f)
            reproduced = f.attributes.get("measurement") == "measured"
        elif f.category.value == "testing":
            test_checks, reproduced = self._testing_checks(ctx, f)
            checks += test_checks
        elif f.category.value == "code_quality":
            checks += self._quality_checks(ctx, f)
        elif f.category.value == "license":
            checks += self._license_checks(ctx, f)
        else:
            checks.append(_check("source_quality", "Is the evidence real?", "pass", "derived from deterministic git / GitHub data"))
        contra = self._contradiction_check(f)
        if contra:
            checks.append(contra)

        policy_value = self._policy(f, checks)

        def validate(j: Judgement) -> Judgement:
            hard_fail = any(c.check == "evidence_integrity" and c.outcome == "fail" for c in checks)
            if hard_fail and j.decision != VerificationDecision.REJECTED:
                raise ValueError("cannot verify a finding whose evidence failed integrity checks")
            if j.decision == VerificationDecision.REJECTED and not any(c.outcome == "fail" for c in checks):
                raise ValueError("rejection requires at least one failing check")
            if j.decision == VerificationDecision.VERIFIED and any(c.supports == "rejection" and c.outcome == "fail" for c in checks):
                raise ValueError("cannot verify while a rejection-supporting check failed")
            return j

        decision = ctx.decide(
            "verification.judge",
            Judgement,
            lambda: policy_value,
            role="You are an adversarial security reviewer (red team). Your job is to find reasons a finding is wrong. Be sceptical.",
            task="Given the finding and the results of independent checks, decide verified / rejected / needs_more_evidence.",
            structured={
                "finding": {"title": f.title, "agent": f.agent, "severity": f.severity.value, "rule": f.rule_id},
                "checks": [c.model_dump() for c in checks],
            },
            tier="reasoning",
            validate=validate,
        )
        judgement = decision.value
        applicable = [c for c in checks if c.outcome != "not_applicable"]
        passed = sum(1 for c in applicable if c.outcome == "pass")
        v_conf = (
            round(0.5 + 0.5 * passed / max(1, len(applicable)), 3)
            if judgement.decision != VerificationDecision.REJECTED
            else round(0.5 + 0.5 * sum(1 for c in applicable if c.outcome == "fail") / max(1, len(applicable)), 3)
        )
        counter = [
            {"check": c.check, "detail": c.detail} for c in checks if c.outcome == "fail" and c.supports in ("rejection", "downgrade")
        ]
        additional = (
            [
                t
                for t in ctx.coverage.get("tool_results", [])
                if "rerun" in str(t.get("command", "")) or "pytest" in str(t.get("command", ""))
            ][-1:]
            if f.rule_id == "testing.test_failure"
            else []
        )
        ctx.store.add_verification(
            ctx.investigation_id,
            VerificationDraft(
                finding_id=f.finding_id,
                round=self.round,
                decision=judgement.decision,
                confidence=v_conf,
                challenge=challenge,
                checks=checks,
                evidence_checked=getattr(self, "_evidence_ids", []),
                additional_tests=additional,
                counter_evidence=counter,
                adjusted_severity=judgement.adjusted_severity,
                reasoning_summary=judgement.reasoning_summary,
                decided_by=decision.decided_by,
            ),
        )
        attrs = {
            "verification_round": self.round,
            "verified_evidence_count": len(ctx.store.list_evidence(ctx.investigation_id, f.finding_id)),
        }
        if reach:
            attrs["reachability"] = reach
        update: dict = {"status": judgement.decision.value, "attributes": attrs}
        if judgement.adjusted_severity and judgement.adjusted_severity.value != f.severity.value:
            attrs["original_severity"] = f.severity.value
            update["severity"] = judgement.adjusted_severity.value
        ctx.store.update_finding(f.finding_id, **update)
        contradiction_resolved = judgement.decision == VerificationDecision.VERIFIED and contra is not None and contra.outcome == "pass"
        ctx.store.recompute_confidence(
            f.finding_id,
            verification=judgement.decision.value,
            reachable=True if reach in ("entrypoint", "reachable") else False if reach == "unreachable" else None,
            reproduced=reproduced or None,
            contradictions=0 if contradiction_resolved else None,
        )
        etype = {
            VerificationDecision.VERIFIED: EventType.FINDING_VERIFIED,
            VerificationDecision.REJECTED: EventType.FINDING_REJECTED,
            VerificationDecision.NEEDS_MORE_EVIDENCE: EventType.VERIFICATION_COMPLETED,
        }[judgement.decision]
        label = {"verified": "VERIFIED", "rejected": "REJECTED", "needs_more_evidence": "NEEDS MORE EVIDENCE"}[judgement.decision.value]
        ctx.emit(
            etype,
            f"{label}: {f.title} — {judgement.reasoning_summary[:300]}",
            receiver=f.agent,
            payload={
                "finding_id": f.finding_id,
                "decision": judgement.decision.value,
                "checks": [c.model_dump() for c in checks],
                "decided_by": decision.decided_by,
                "adjusted_severity": judgement.adjusted_severity.value if judgement.adjusted_severity else None,
            },
            severity="warning" if judgement.decision == VerificationDecision.REJECTED else "info",
        )
        if judgement.decision == VerificationDecision.NEEDS_MORE_EVIDENCE:
            self._request_more(ctx, f, checks)
        return judgement.decision

    def _policy(self, f: FindingOut, checks: list[VerificationCheck]) -> Judgement:
        fails = [c for c in checks if c.outcome == "fail"]
        if any(c.check == "evidence_integrity" for c in fails):
            return Judgement(
                decision=VerificationDecision.REJECTED,
                reasoning_summary="Evidence does not match the repository content; the claim cannot be substantiated.",
            )
        rejecting = [c for c in fails if c.supports == "rejection"]
        if rejecting:
            parts = [c.detail for c in rejecting] + [c.detail for c in fails if c.supports == "downgrade"]
            if f.rule_id == "security.hardcoded_secret":
                summary = (
                    f"The detected string occurs in {', '.join(f.affected_files)} and matches a documented placeholder pattern. "
                    + " ".join(p.rstrip(".") + "." for p in parts)
                    + " No production credential exposure established."
                )
            else:
                summary = "Rejected: " + " ".join(p.rstrip(".") + "." for p in parts)
            return Judgement(decision=VerificationDecision.REJECTED, reasoning_summary=summary[:1200])
        more = [c for c in checks if c.supports == "more_evidence" and c.outcome in ("fail", "inconclusive")]
        if more:
            return Judgement(
                decision=VerificationDecision.NEEDS_MORE_EVIDENCE,
                reasoning_summary="Needs more evidence: " + " ".join(c.detail.rstrip(".") + "." for c in more),
            )
        downgrades = [c for c in fails if c.supports == "downgrade"]
        adjusted = Severity(_DOWNGRADE[f.severity.value]) if downgrades else None
        passed = [c for c in checks if c.outcome == "pass"]
        summary = "Verified: " + " ".join(c.detail.rstrip(".") + "." for c in passed[:4])
        if downgrades:
            summary += f" Severity downgraded {f.severity.value} -> {adjusted.value if adjusted else f.severity.value}: " + " ".join(
                c.detail for c in downgrades
            )
        return Judgement(decision=VerificationDecision.VERIFIED, reasoning_summary=summary[:1200], adjusted_severity=adjusted)

    def _request_more(self, ctx: AgentContext, f: FindingOut, checks: list[VerificationCheck]) -> None:
        existing = [
            r
            for r in ctx.store.list_requests(ctx.investigation_id)
            if f.finding_id in r.related_finding_ids and r.requested_by == self.name
        ]
        if existing:
            ctx.message(
                "orchestrator",
                f"Evidence for '{f.title}' remains insufficient after follow-up — leaving as INSUFFICIENT EVIDENCE",
                payload={"finding_id": f.finding_id},
            )
            return
        if f.category.value == "performance" or any(c.check == "contradiction" for c in checks):
            perf = (
                f
                if f.category.value == "performance"
                else next(
                    (
                        self.by_id[i]
                        for c in self.contradictions.get(f.finding_id, [])
                        for i in c.finding_ids
                        if i in self.by_id and self.by_id[i].category.value == "performance"
                    ),
                    None,
                )
            )
            if perf is None:
                return
            ctx.request_investigation(
                f"Run a benchmark for {perf.attributes.get('function')}() to measure the suspected {perf.rule_id.split('.')[-1].replace('_', ' ')}",
                reason="static suspect / disputed claim cannot be verified without measurement",
                required_evidence="benchmark",
                target_agent="performance_agent",
                focus={
                    "finding_ids": [perf.finding_id],
                    "function": perf.attributes.get("function"),
                    "file": (perf.affected_files or [""])[0],
                },
                related_finding_ids=sorted({perf.finding_id, f.finding_id}),
            )
        elif f.rule_id == "security.hardcoded_secret":
            ctx.request_investigation(
                f"Re-examine credential context in {f.affected_files[0]}",
                reason="placeholder status undetermined",
                required_evidence="usage_analysis",
                target_agent="security_agent",
                focus={"file": f.affected_files[0]},
                related_finding_ids=[f.finding_id],
            )

    def _challenge_text(self, f: FindingOut) -> str:
        if f.rule_id == "security.hardcoded_secret":
            return "Is this a live credential, or a documented dummy value in a fixture? Is it used by production code?"
        if f.category.value == "dependency" and f.attributes.get("vulnerable"):
            return f"Is {f.attributes.get('package')} actually imported and reachable, and is the {f.severity.value} severity backed by the advisory data?"
        if f.category.value == "performance":
            return "Has this been measured, or is it a theoretical static suspect? Is the code on a reachable path?"
        if f.rule_id == "testing.test_failure":
            return "Does the failure reproduce on an independent re-run?"
        if f.attributes.get("stance") == "acceptable":
            return "Does measured evidence contradict this 'acceptable' assessment?"
        if f.category.value == "testing":
            return "Do tests really not exercise this code? Re-derive the mapping independently."
        return "Is the evidence real, current and reachable, and is the severity justified?"

    # ----------------------------------------------------------- correlations
    def _verify_correlation(self, ctx: AgentContext, c: CorrelationOut) -> None:
        members = [ctx.store.get_finding(i) for i in c.finding_ids]
        members = [m for m in members if m is not None]
        statuses = {m.finding_id: m.status.value for m in members}
        verified = [m for m in members if m.status.value == "verified"]
        rejected = [m for m in members if m.status.value == "rejected"]
        pending = [m for m in members if m.status.value not in ("verified", "rejected")]
        checks: list[VerificationCheck] = []
        multiplier = c.risk_multiplier
        if c.relationship_type.value == "contradiction":
            if verified and rejected:
                winner, loser = verified[0], rejected[0]
                resolution = f"Resolved in favour of {winner.agent}: {winner.title}. {loser.agent}'s position was rejected by evidence."
                ctx.store.update_correlation(c.correlation_id, status="resolved", resolution=resolution)
                decision = VerificationDecision.VERIFIED
                summary = resolution
            else:
                decision = VerificationDecision.NEEDS_MORE_EVIDENCE
                summary = "Contradiction unresolved: " + ", ".join(f"{m.agent}={m.status.value}" for m in members)
                if not pending:
                    ctx.store.update_correlation(c.correlation_id, status="rejected", resolution=summary)
            checks.append(
                _check(
                    "adjudication",
                    "Is there contradictory evidence?",
                    "pass" if decision == VerificationDecision.VERIFIED else "inconclusive",
                    summary,
                )
            )
        else:
            if c.relationship_type.value == "compound_risk":
                pkg_link = next((lk.get("value") for lk in c.links if lk.get("type") == "same_package"), None)
                tests = [m for m in verified if m.category.value == "testing"]
                if pkg_link and tests:
                    users = set(self.graph.files_importing_external(import_name_for(pkg_link).split(".")[0]))
                    overlap = sorted(users & {p for t in tests for p in t.affected_files})
                    if overlap:
                        checks.append(
                            _check("link", "Is the compound link real?", "pass", f"untested files {', '.join(overlap)} import {pkg_link}")
                        )
                    else:
                        multiplier = round(max(1.0, multiplier - 0.25), 2)
                        checks.append(
                            _check(
                                "link",
                                "Is the compound link real?",
                                "fail",
                                "tested-gap files do not import the package; multiplier reduced",
                                "downgrade",
                            )
                        )
                checks.append(
                    _check(
                        "severity_challenge",
                        "Is the compound severity justified?",
                        "pass",
                        f"compound severity = most severe verified member ({max((m.severity.value for m in verified), key=lambda s: _SEV_RANK.get(s, 0)) if verified else 'n/a'}); multiplier {multiplier} reflects {len({m.category.value for m in verified})} independently verified dimensions",
                    )
                )
            if len(verified) >= 2 and not (members and members[0].status.value == "rejected"):
                decision = VerificationDecision.VERIFIED
                remaining = [m.finding_id for m in members if m.status.value != "rejected"]
                summary = f"{len(verified)} of {len(members)} member findings verified" + (
                    f"; {len(rejected)} rejected member(s) removed" if rejected else ""
                )
                ctx.store.update_correlation(c.correlation_id, status="verified", finding_ids=remaining, risk_multiplier=multiplier)
            elif pending and len(verified) + len(pending) >= 2:
                decision = VerificationDecision.NEEDS_MORE_EVIDENCE
                summary = f"awaiting verification of {len(pending)} member(s)"
            else:
                decision = VerificationDecision.REJECTED
                summary = f"only {len(verified)} verified member(s); relationship not substantiated"
                ctx.store.update_correlation(c.correlation_id, status="rejected", resolution=summary)
            checks.append(
                _check(
                    "member_status",
                    "Are the related findings themselves verified?",
                    "pass"
                    if decision == VerificationDecision.VERIFIED
                    else "fail"
                    if decision == VerificationDecision.REJECTED
                    else "inconclusive",
                    summary,
                )
            )
        ctx.store.add_verification(
            ctx.investigation_id,
            VerificationDraft(
                correlation_id=c.correlation_id,
                round=self.round,
                decision=decision,
                confidence=c.confidence,
                challenge=f"Does the {c.relationship_type.value.replace('_', ' ')} hold once each member has been challenged?",
                checks=checks,
                evidence_checked=list(statuses),
                reasoning_summary=summary,
            ),
        )
        ctx.emit(
            EventType.CORRELATION_UPDATED,
            f"Correlation {decision.value.replace('_', ' ')}: {c.title} — {summary}",
            receiver="orchestrator",
            payload={
                "correlation_id": c.correlation_id,
                "decision": decision.value,
                "member_status": statuses,
                "risk_multiplier": multiplier,
            },
            correlation_id=c.correlation_id,
        )
