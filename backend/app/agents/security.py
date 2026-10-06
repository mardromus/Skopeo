"""Security Agent — secrets, insecure code patterns, prompt-injection content, dependency usage.

The detector side is deliberately recall-oriented: it reports anything that *looks* dangerous
with the evidence it saw. Precision is the Verification (red-team) agent's job.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

from app.agents.base import AgentContext, SpecialistAgent, Step
from app.agents.common import components_for, excerpt
from app.schemas import Category, EvidenceDraft, FindingDraft, Severity, SourceType
from app.security.prompt_guard import scan_for_injection
from app.tools.python_ast import ImportGraph, call_sites, dotted_name, import_aliases, iter_functions, parse_python, resolve_call
from app.tools.repository import is_test_path
from app.tools.secrets import scan_text

_SECRETISH_ENV = re.compile(r"(SECRET|TOKEN|PASSWORD|PASSWD|API_?KEY|PRIVATE_?KEY|SIGNING_?KEY)", re.I)
_PASSWORD_CONTEXT = re.compile(r"pass(word|wd)?|pwd|credential|hash_password|verify_password", re.I)
_TEXT_SUFFIXES = (".md", ".rst", ".txt", ".html", ".py", ".js", ".ts", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".json", ".env", ".sh")
_DOC_SUFFIXES = (".md", ".rst", ".txt", ".html")
_SEMGREP_RULES = Path(__file__).resolve().parents[1] / "data" / "semgrep_rules.yml"


def _is_false(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _is_dynamic_string(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(v, ast.FormattedValue) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
        return isinstance(node.left, (ast.Constant, ast.JoinedStr, ast.BinOp)) and not (
            isinstance(node.left, ast.Constant) and isinstance(node.right, ast.Constant)
        )
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format"


class SecurityAgent(SpecialistAgent):
    name = "security_agent"
    display_name = "Security Agent"
    category = "security"
    description = "Secret scanning, AST-based insecure-pattern detection, prompt-injection content, dependency usage and reachability."
    modes = {
        "full": "complete security review",
        "dependency_usage": "trace how a (vulnerable) dependency is used and whether it reaches security-critical code",
    }

    def plan(self, ctx: AgentContext) -> list[Step]:
        if ctx.task.mode == "dependency_usage":
            return [("trace dependency usage & reachability", self._dependency_usage)]
        steps: list[Step] = [
            ("scan for committed secrets", self._secrets),
            ("analyse insecure code patterns (AST)", self._python_patterns),
            ("scan for prompt-injection content", self._prompt_injection),
            ("run Semgrep ruleset if available", self._semgrep),
        ]
        if ctx.repo.source == "github" and ctx.services.github.authenticated:
            steps.append(("correlate GitHub Dependabot alerts", self._dependabot))
        else:
            ctx.limitation("Dependabot alerts not queried (no GITHUB_TOKEN or not a GitHub source)")
        return steps

    # ---------------------------------------------------------------- secrets
    def _secrets(self, ctx: AgentContext) -> None:
        files = [f for f in ctx.tools.list_files() if not f.endswith(("package-lock.json", ".min.js", "yarn.lock", "poetry.lock"))]
        scanned = 0
        by_file: dict[str, list] = defaultdict(list)
        for rel in files:
            text = ctx.tools.try_get_file(rel)
            if text is None:
                continue
            scanned += 1
            for match in scan_text(text):
                by_file[rel].append(match)
        ctx.analyzed(f"Secret scan over {scanned} text files")
        for rel, matches in by_file.items():
            severity = max((Severity(m.severity) for m in matches), key=lambda s: s.rank)
            kinds = sorted({m.title for m in matches})
            evidence = [
                EvidenceDraft(
                    source_type=SourceType.STATIC_ANALYSIS,
                    source=f"{rel}:{m.line}",
                    tool="skopeo-secret-scanner",
                    file=rel,
                    line_start=m.line,
                    line_end=m.line,
                    excerpt=m.line_text,
                    confidence=0.8,
                    data={"rule": m.rule_id, "masked_value": m.masked},
                )
                for m in matches[:10]
            ]
            ctx.publish(
                FindingDraft(
                    category=Category.SECURITY,
                    rule_id="security.hardcoded_secret",
                    title=f"Possible credential exposure: {' and '.join(kinds)} in {rel}",
                    description=(
                        f"{len(matches)} credential-shaped literal(s) matching {', '.join(sorted({m.rule_id for m in matches}))} "
                        f"were found in {rel}. If live, anyone with repository access could use them."
                    ),
                    severity=severity,
                    subject=f"file:{rel}",
                    affected_files=[rel],
                    affected_components=components_for(rel) + ["secrets"],
                    attributes={
                        "secret_types": sorted({m.rule_id for m in matches}),
                        "masked_values": [m.masked for m in matches[:10]],
                        "lines": [m.line for m in matches[:10]],
                        "in_test_path": is_test_path(rel),
                    },
                    reasoning_summary=(
                        "Pattern-based scanner matched literals with the exact format of the listed credential types. "
                        "The scanner does not judge context (fixture vs production); that is left to verification."
                    ),
                    recommended_action="If live: revoke and rotate the credential (human action), remove it from history, load secrets from a vault/env.",
                ),
                evidence,
            )

    # ------------------------------------------------------- python patterns
    def _python_patterns(self, ctx: AgentContext) -> None:
        files = ctx.tools.list_files(suffixes=(".py",), include_tests=False)
        hits: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for rel in files:
            text = ctx.tools.try_get_file(rel)
            tree = parse_python(text or "", rel) if text else None
            if tree is None:
                continue
            lines = text.splitlines()  # type: ignore[union-attr]
            aliases = import_aliases(tree)
            fn_ranges = [(f.lineno, f.end_lineno, f.name) for f in iter_functions(tree, rel)]

            def enclosing(line: int, ranges: list = fn_ranges) -> str:
                inner = [r for r in ranges if r[0] <= line <= r[1]]
                return min(inner, key=lambda r: r[1] - r[0])[2] if inner else ""

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = dotted_name(node.func)
                    if not name:
                        continue
                    full = resolve_call(name, aliases)
                    kw = {k.arg: k.value for k in node.keywords if k.arg}
                    line = node.lineno
                    hit = None
                    if full == "jwt.decode":
                        opts = kw.get("options")
                        disabled = ("verify" in kw and _is_false(kw["verify"])) or (
                            isinstance(opts, ast.Dict)
                            and any(
                                isinstance(k, ast.Constant) and k.value == "verify_signature" and _is_false(v)
                                for k, v in zip(opts.keys, opts.values, strict=False)
                            )
                        )
                        if disabled:
                            hit = ("security.jwt_verification_disabled", Severity.CRITICAL, "JWT signature verification disabled")
                        elif "algorithms" not in kw:
                            hit = ("security.jwt_no_algorithms", Severity.HIGH, "JWT decoded without an explicit algorithms allow-list")
                    elif full in ("hashlib.md5", "hashlib.sha1") and (
                        _PASSWORD_CONTEXT.search(enclosing(line)) or _PASSWORD_CONTEXT.search(rel)
                    ):
                        hit = (
                            "security.weak_password_hash",
                            Severity.HIGH,
                            f"Passwords hashed with {full.split('.')[-1].upper()} (fast, unsalted)",
                        )
                    elif full in ("eval", "exec") and node.args and not isinstance(node.args[0], ast.Constant):
                        hit = ("security.code_eval", Severity.HIGH, f"Dynamic code execution via {full}()")
                    elif full in ("pickle.loads", "pickle.load", "marshal.loads"):
                        hit = ("security.insecure_deserialization", Severity.MEDIUM, f"Insecure deserialization via {full}()")
                    elif full == "yaml.load" and "Loader" not in kw and len(node.args) < 2:
                        hit = ("security.yaml_unsafe_load", Severity.MEDIUM, "yaml.load without a safe Loader")
                    elif full in ("os.system", "os.popen") and node.args and not isinstance(node.args[0], ast.Constant):
                        hit = ("security.command_injection", Severity.HIGH, f"Shell command built from dynamic input ({full})")
                    elif (
                        full.startswith("subprocess.")
                        and "shell" in kw
                        and isinstance(kw["shell"], ast.Constant)
                        and kw["shell"].value is True
                    ):
                        hit = ("security.command_injection", Severity.HIGH, "subprocess invoked with shell=True")
                    elif full.split(".")[-1] in ("execute", "executemany", "raw") and node.args and _is_dynamic_string(node.args[0]):
                        hit = ("security.sql_injection", Severity.HIGH, "SQL statement built with string formatting")
                    elif full.split(".")[0] in ("requests", "httpx") and "verify" in kw and _is_false(kw["verify"]):
                        hit = ("security.tls_verification_disabled", Severity.MEDIUM, "TLS certificate verification disabled")
                    elif full in ("os.environ.get", "os.getenv") and len(node.args) >= 2:
                        key, default = node.args[0], node.args[1]
                        if (
                            isinstance(key, ast.Constant)
                            and isinstance(key.value, str)
                            and _SECRETISH_ENV.search(key.value)
                            and isinstance(default, ast.Constant)
                            and isinstance(default.value, str)
                            and default.value
                        ):
                            hit = ("security.hardcoded_default_secret", Severity.MEDIUM, f"Hardcoded fallback value for secret {key.value}")
                    if hit:
                        hits[(hit[0], rel)].append(
                            {
                                "line": line,
                                "end": getattr(node, "end_lineno", line) or line,
                                "severity": hit[1],
                                "title": hit[2],
                                "call": full,
                            }
                        )
                elif isinstance(node, ast.Assign) and Path(rel).stem in ("settings", "config", "configuration"):
                    for target in node.targets:
                        if (
                            isinstance(target, ast.Name)
                            and target.id == "DEBUG"
                            and isinstance(node.value, ast.Constant)
                            and node.value.value is True
                        ):
                            hits[("security.debug_enabled", rel)].append(
                                {
                                    "line": node.lineno,
                                    "end": node.lineno,
                                    "severity": Severity.LOW,
                                    "title": "DEBUG enabled in configuration",
                                    "call": "DEBUG = True",
                                }
                            )
            for (rule, file), items in list(hits.items()):
                if file != rel:
                    continue
                first = items[0]
                evidence = [
                    EvidenceDraft(
                        source_type=SourceType.STATIC_ANALYSIS,
                        source=f"{rel}:{it['line']}",
                        tool="skopeo-python-ast",
                        file=rel,
                        line_start=it["line"],
                        line_end=it["end"],
                        excerpt=excerpt(lines, it["line"], it["end"]),
                        confidence=0.85,
                        data={"call": it["call"], "function": enclosing(it["line"])},
                    )
                    for it in items[:8]
                ]
                ctx.publish(
                    FindingDraft(
                        category=Category.SECURITY,
                        rule_id=rule,
                        title=f"{first['title']} in {rel}",
                        description=f"{len(items)} occurrence(s) of `{first['call']}` matching rule {rule} in {rel} (lines {', '.join(str(i['line']) for i in items[:8])}).",
                        severity=first["severity"],
                        subject=f"rule:{rule}:{rel}",
                        affected_files=[rel],
                        affected_components=components_for(rel),
                        attributes={
                            "api": first["call"],
                            "lines": [i["line"] for i in items],
                            "functions": sorted({enclosing(i["line"]) for i in items} - {""}),
                        },
                        reasoning_summary=f"AST match of `{first['call']}` with the unsafe argument pattern for {rule}; alias-resolved imports.",
                        recommended_action=_RULE_FIXES.get(rule, "Review and remediate the insecure pattern."),
                    ),
                    evidence,
                )
        ctx.analyzed(f"AST security analysis of {len(files)} non-test Python files")
        non_python = [f for f in ctx.tools.list_files(suffixes=(".js", ".ts", ".jsx", ".tsx"), include_tests=False)]
        if non_python:
            for hit in ctx.tool(
                "search",
                ctx.tools.search_repository,
                r"\beval\(|\.innerHTML\s*=|child_process\.exec\(",
                suffixes=(".js", ".ts", ".jsx", ".tsx"),
                max_results=30,
            ):
                if is_test_path(hit.file):
                    continue
                ctx.publish(
                    FindingDraft(
                        category=Category.SECURITY,
                        rule_id="security.js_dangerous_sink",
                        title=f"Dangerous JavaScript sink in {hit.file}:{hit.line}",
                        description=f"`{hit.text[:120]}` writes to a code/HTML/command execution sink.",
                        severity=Severity.MEDIUM,
                        subject=f"rule:security.js_dangerous_sink:{hit.file}:{hit.line}",
                        affected_files=[hit.file],
                        affected_components=components_for(hit.file),
                        attributes={"line": hit.line},
                        reasoning_summary="Regex match on a known dangerous sink (no data-flow analysis for JS in this MVP).",
                        recommended_action="Avoid eval/innerHTML/exec with dynamic input; use safe APIs.",
                    ),
                    [
                        EvidenceDraft(
                            source_type=SourceType.STATIC_ANALYSIS,
                            source=f"{hit.file}:{hit.line}",
                            tool="regex-search",
                            file=hit.file,
                            line_start=hit.line,
                            line_end=hit.line,
                            excerpt=hit.text,
                            confidence=0.6,
                        )
                    ],
                )
            ctx.limitation("JavaScript/TypeScript analysed with regex rules only (no AST/data-flow)")

    # -------------------------------------------------------- prompt injection
    def _prompt_injection(self, ctx: AgentContext) -> None:
        files = ctx.tools.list_files(suffixes=_TEXT_SUFFIXES)
        found = []
        for rel in files:
            text = ctx.tools.try_get_file(rel)
            if not text:
                continue
            signals = scan_for_injection(text)
            if signals and (rel.endswith(_DOC_SUFFIXES) or any(s.pattern in ("exfiltration", "override_instructions") for s in signals)):
                found.append((rel, signals))
        for rel, signals in found[:10]:
            ctx.publish(
                FindingDraft(
                    category=Category.SECURITY,
                    rule_id="security.prompt_injection_content",
                    title=f"AI-directed instructions (possible prompt injection) in {rel}",
                    description=(
                        f"{rel} contains text addressed to AI/automated agents ({', '.join(sorted({s.pattern for s in signals}))}). "
                        "Skopeo treated it strictly as data and did not follow it, but other AI tooling consuming this repository could be manipulated."
                    ),
                    severity=Severity.LOW,
                    subject=f"file:{rel}",
                    affected_files=[rel],
                    affected_components=["documentation" if rel.endswith(_DOC_SUFFIXES) else components_for(rel)[0], "ai-supply-chain"],
                    attributes={"patterns": sorted({s.pattern for s in signals}), "lines": [s.line for s in signals]},
                    reasoning_summary="Deterministic prompt-injection signatures matched; content never reached an instruction context.",
                    recommended_action="Remove AI-directed instructions from repository content; treat repository text as untrusted in all AI tooling.",
                ),
                [
                    EvidenceDraft(
                        source_type=SourceType.STATIC_ANALYSIS,
                        source=f"{rel}:{s.line}",
                        tool="skopeo-prompt-guard",
                        file=rel,
                        line_start=s.line,
                        line_end=s.line,
                        excerpt=s.excerpt,
                        confidence=0.75,
                        data={"pattern": s.pattern},
                    )
                    for s in signals[:6]
                ],
            )
            ctx.message(
                "orchestrator",
                f"Prompt-injection content detected in {rel}; handled as untrusted data (no instructions followed)",
                payload={"file": rel, "patterns": sorted({s.pattern for s in signals})},
                severity="warning",
            )
        ctx.analyzed(f"Prompt-injection scan over {len(files)} text files")

    # ------------------------------------------------------------- semgrep
    def _semgrep(self, ctx: AgentContext) -> None:
        result = ctx.tool("run_static_analysis", ctx.tools.run_static_analysis, _SEMGREP_RULES)
        if result is None:
            ctx.limitation("Semgrep not installed — built-in AST/regex rules used instead")
            return
        res = result["result"]
        ctx.record_tool_result(res.summary(400))
        for item in (result["data"].get("results") or [])[:30]:
            path = str(item.get("path", "")).replace("\\", "/").lstrip("./")
            if not path or is_test_path(path):
                continue
            line = int((item.get("start") or {}).get("line") or 0) or None
            check = str(item.get("check_id", "semgrep"))
            existing = [
                f for f in ctx.findings(category="security") if path in f.affected_files and line in (f.attributes.get("lines") or [])
            ]
            draft = EvidenceDraft(
                source_type=SourceType.STATIC_ANALYSIS,
                source=f"semgrep {check}",
                tool="semgrep",
                file=path,
                line_start=line,
                line_end=line,
                excerpt=str((item.get("extra") or {}).get("lines", ""))[:400],
                confidence=0.85,
            )
            if existing:
                ctx.attach_evidence(existing[0].finding_id, draft, f"Semgrep corroborates finding at {path}:{line}")
            else:
                ctx.publish(
                    FindingDraft(
                        category=Category.SECURITY,
                        rule_id=f"security.semgrep.{check.split('.')[-1]}",
                        title=f"Semgrep: {(item.get('extra') or {}).get('message', check)} ({path}:{line})",
                        description=str((item.get("extra") or {}).get("message", check)),
                        severity=Severity.MEDIUM,
                        subject=f"rule:{check}:{path}:{line}",
                        affected_files=[path],
                        affected_components=components_for(path),
                        attributes={"semgrep_check": check},
                        reasoning_summary="Reported by Semgrep using Skopeo's local ruleset.",
                        recommended_action="Review the Semgrep finding.",
                    ),
                    [draft],
                )

    # ------------------------------------------------------------ dependabot
    def _dependabot(self, ctx: AgentContext) -> None:
        try:
            alerts = ctx.tool("github_dependabot", ctx.services.github.dependabot_alerts, ctx.repo.full_name)
        except Exception as exc:  # noqa: BLE001 - optional source, degrade gracefully
            ctx.limitation(f"Dependabot alerts unavailable: {exc}")
            return
        dep_findings = {f.attributes.get("package"): f for f in ctx.findings(category="dependency") if f.attributes.get("vulnerable")}
        for alert in alerts[:30]:
            pkg = ((alert.get("dependency") or {}).get("package") or {}).get("name", "").lower()
            adv = alert.get("security_advisory") or {}
            draft = EvidenceDraft(
                source_type=SourceType.GITHUB,
                source="GitHub Dependabot",
                tool="github-dependabot-api",
                excerpt=f"{adv.get('ghsa_id')} {adv.get('summary', '')}"[:400],
                raw_reference=str(alert.get("html_url", "")),
                confidence=0.85,
            )
            if pkg in dep_findings:
                ctx.attach_evidence(
                    dep_findings[pkg].finding_id, draft, f"Dependabot alert corroborates vulnerable {pkg}", corroborating_agents=1
                )

    # ------------------------------------------------------ dependency usage
    def _dependency_usage(self, ctx: AgentContext) -> None:
        focus = ctx.task.focus
        package = focus.get("package", "")
        import_name = focus.get("import_name") or package
        graph = ctx.tool("build_import_graph", ImportGraph, ctx.tools)
        users = [f for f in graph.files_importing_external(import_name.split(".")[0]) if not is_test_path(f)]
        test_users = [f for f in graph.files_importing_external(import_name.split(".")[0]) if is_test_path(f)]
        entrypoints = set(ctx.profile.get("entrypoints", []))
        if not users:
            ctx.message(
                "orchestrator",
                f"{package} is declared but never imported by production code — the advisories are likely not reachable",
                payload={"package": package, "test_only_users": test_users},
            )
            ctx.publish(
                FindingDraft(
                    category=Category.SECURITY,
                    rule_id="security.vulnerable_dependency_unused",
                    title=f"Vulnerable {package} is declared but not imported by production code",
                    description=f"No non-test module imports `{import_name}`. Vulnerable code paths are probably unreachable, but the package is still installed.",
                    severity=Severity.LOW,
                    subject=f"pkg-usage:{package}",
                    affected_files=test_users[:5] or [],
                    affected_components=["dependencies"],
                    attributes={
                        "package": package,
                        "usage_files": [],
                        "reachability_hint": "unreachable",
                        "related_finding_id": focus.get("finding_id"),
                    },
                    reasoning_summary="Import graph shows no production importers.",
                    recommended_action=f"Remove {package} if unused, or upgrade it.",
                    is_hypothesis=True,
                ),
                [],
            )
            return
        evidence: list[EvidenceDraft] = []
        call_lines: list[dict] = []
        components: set[str] = set()
        for rel in users:
            text = ctx.tools.get_file(rel)
            tree = parse_python(text, rel)
            lines = text.splitlines()
            components.update(c for c in components_for(rel) if c not in ("tests",))
            for i, line in enumerate(lines, start=1):
                if re.match(rf"\s*(import\s+{re.escape(import_name)}\b|from\s+{re.escape(import_name)}[\s.])", line):
                    evidence.append(
                        EvidenceDraft(
                            source_type=SourceType.STATIC_ANALYSIS,
                            source=f"{rel}:{i}",
                            tool="skopeo-import-graph",
                            file=rel,
                            line_start=i,
                            line_end=i,
                            excerpt=line.strip(),
                            confidence=0.95,
                            data={"kind": "import"},
                        )
                    )
            if tree is not None:
                aliases = import_aliases(tree)
                for site in call_sites(tree):
                    full = resolve_call(site.dotted, aliases)
                    if full.split(".")[0] == import_name.split(".")[0]:
                        call_lines.append({"file": rel, "line": site.lineno, "call": full, "function": site.function})
                        evidence.append(
                            EvidenceDraft(
                                source_type=SourceType.STATIC_ANALYSIS,
                                source=f"{rel}:{site.lineno}",
                                tool="skopeo-python-ast",
                                file=rel,
                                line_start=site.lineno,
                                line_end=site.end_lineno,
                                excerpt=excerpt(lines, site.lineno, site.end_lineno),
                                confidence=0.9,
                                data={"kind": "call", "call": full, "function": site.function},
                            )
                        )
        reach_chain: list[str] = []
        for rel in users:
            importers = graph.transitive_importers(rel)
            hits = sorted(importers & entrypoints) or ([rel] if rel in entrypoints else [])
            if hits:
                reach_chain.append(f"{rel} <- {', '.join(sorted(graph.importers_of(rel)))[:200]}")
        critical = sorted(components & {"authentication", "authorization", "cryptography", "payments", "secrets"})
        target = critical[0] if critical else (sorted(components)[0] if components else "application")
        severity = Severity.HIGH if critical else Severity.MEDIUM
        ctx.publish(
            FindingDraft(
                category=Category.SECURITY,
                rule_id="security.vulnerable_dependency_usage",
                title=f"Vulnerable {package} is used by the {target} component ({', '.join(users[:3])})",
                description=(
                    f"`{import_name}` is imported by {len(users)} production module(s) and called at {len(call_lines)} site(s): "
                    + "; ".join(f"{c['call']} in {c['file']}:{c['line']}" for c in call_lines[:6])
                    + (f". Reachable from entrypoints via: {'; '.join(reach_chain[:3])}." if reach_chain else ".")
                ),
                severity=severity,
                subject=f"pkg-usage:{package}",
                affected_files=users,
                affected_components=sorted(components) or ["application"],
                attributes={
                    "package": package,
                    "import_name": import_name,
                    "usage_files": users,
                    "call_sites": call_lines[:20],
                    "reachability_hint": "entrypoint" if reach_chain else "reachable",
                    "security_critical": bool(critical),
                    "related_finding_id": focus.get("finding_id"),
                },
                reasoning_summary=(
                    f"Follow-up requested by the orchestrator. Import graph + AST call-site analysis link {package} to "
                    f"{', '.join(users)}" + (f"; component classified security-critical ({', '.join(critical)})." if critical else ".")
                ),
                recommended_action=f"Prioritise upgrading {package}; review the listed call sites.",
            ),
            evidence[:15],
        )
        ctx.message(
            "orchestrator",
            f"Confirmed {package} is used by {target} code ({', '.join(users[:3])}); reachable from entrypoints: {'yes' if reach_chain else 'not established'}",
            payload={"package": package, "usage_files": users, "call_sites": len(call_lines)},
        )


_RULE_FIXES = {
    "security.jwt_no_algorithms": "Pass an explicit allow-list, e.g. jwt.decode(token, key, algorithms=['HS256']).",
    "security.jwt_verification_disabled": "Never disable signature verification outside tests.",
    "security.weak_password_hash": "Use a slow, salted password KDF (argon2id, bcrypt or scrypt) and migrate stored hashes.",
    "security.code_eval": "Remove eval/exec on dynamic input; use a safe parser.",
    "security.insecure_deserialization": "Do not unpickle untrusted data; use JSON or a schema-validated format.",
    "security.yaml_unsafe_load": "Use yaml.safe_load().",
    "security.command_injection": "Pass argv lists without shell=True and validate inputs.",
    "security.sql_injection": "Use parameterised queries.",
    "security.tls_verification_disabled": "Keep TLS verification enabled; configure a CA bundle if needed.",
    "security.hardcoded_default_secret": "Remove the literal fallback; fail fast when the secret is not configured, then rotate it.",
    "security.debug_enabled": "Disable DEBUG in production configuration.",
}
