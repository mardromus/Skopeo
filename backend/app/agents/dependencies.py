"""Dependency Health Agent — ecosystem detection, vulnerabilities (OSV), freshness, pinning, conflicts."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from app.agents.base import AgentContext, SpecialistAgent, Step
from app.agents.common import SECURITY_SENSITIVE_PACKAGES, import_name_for
from app.schemas import Category, EvidenceDraft, FindingDraft, Severity, SourceType
from app.tools.advisories import age_in_days, parse_version, version_gap
from app.tools.manifests import Dependency

_SEV_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "unknown": 2}


def _max_version(versions: list[str], ecosystem: str) -> str | None:
    parsed = [(parse_version(v, ecosystem), v) for v in versions]
    parsed = [p for p in parsed if p[0] is not None]
    if not parsed:
        return None
    return max(parsed, key=lambda p: p[0])[1]  # type: ignore[arg-type,return-value]


def _min_version(versions: list[str], ecosystem: str) -> str | None:
    parsed = [(parse_version(v, ecosystem), v) for v in versions]
    parsed = [p for p in parsed if p[0] is not None]
    if not parsed:
        return None
    return min(parsed, key=lambda p: p[0])[1]  # type: ignore[arg-type,return-value]


class DependencyAgent(SpecialistAgent):
    name = "dependency_agent"
    display_name = "Dependency Health Agent"
    category = "dependency"
    description = (
        "Detects ecosystems, parses manifests, queries OSV advisories and registry metadata for freshness, pinning and abandonment."
    )

    def plan(self, ctx: AgentContext) -> list[Step]:
        self.deps: list[Dependency] = []
        return [
            ("detect ecosystems & parse manifests", self._parse),
            ("query vulnerability database", self._vulnerabilities),
            ("check freshness & maintenance via registry", self._freshness),
            ("check version pinning & conflicts", self._pinning),
        ]

    # ------------------------------------------------------------------ steps
    def _parse(self, ctx: AgentContext) -> None:
        self.deps = ctx.tool("inspect_dependencies", ctx.tools.inspect_dependencies)
        ecosystems = sorted({d.ecosystem for d in self.deps})
        manifests = sorted({d.manifest for d in self.deps})
        ctx.analyzed(f"{len(self.deps)} declared dependencies across {len(manifests)} manifest(s): {', '.join(manifests) or 'none'}")
        ctx.message(
            "orchestrator",
            f"Detected ecosystem(s) {', '.join(ecosystems) or 'none'}; {len(self.deps)} dependencies in {', '.join(manifests) or 'no manifests'}",
            payload={"ecosystems": ecosystems, "manifests": manifests, "dependencies": [d.to_dict() for d in self.deps[:50]]},
        )
        if not self.deps:
            ctx.limitation("No dependency manifests found — dependency health not assessable (INSUFFICIENT EVIDENCE)")
        if any(d.ecosystem == "PyPI" for d in self.deps) and not any(m.endswith((".lock", "lock.json")) for m in manifests):
            ctx.limitation("No Python lockfile: transitive dependencies were not resolved")

    def _manifest_evidence(self, ctx: AgentContext, dep: Dependency) -> EvidenceDraft:
        line_text = ""
        if dep.line:
            lines = ctx.tools.get_lines(dep.manifest, dep.line, dep.line)
            line_text = lines[0] if lines else ""
        return EvidenceDraft(
            source_type=SourceType.DEPENDENCY,
            source=f"manifest {dep.manifest}",
            tool="manifest-parser",
            file=dep.manifest,
            line_start=dep.line,
            line_end=dep.line,
            excerpt=line_text or f"{dep.display_name}{dep.spec}",
            confidence=0.95,
            data={"package": dep.name, "spec": dep.spec, "version": dep.version},
        )

    def _vulnerabilities(self, ctx: AgentContext) -> None:
        unavailable = []
        for dep in self.deps:
            lookup = ctx.tool("osv_lookup", ctx.services.advisories.lookup, dep)
            if lookup.status == "unavailable":
                unavailable.append(f"{dep.display_name}=={dep.version} ({lookup.detail})")
                continue
            if lookup.status != "ok" or not lookup.advisories:
                continue
            advisories = lookup.advisories
            max_sev = max(advisories, key=lambda a: _SEV_ORDER.get(a.severity, 0)).severity
            severity = Severity(max_sev if max_sev in ("critical", "high", "medium", "low") else "medium")
            # The release that fixes *every* advisory: the max over advisories of each one's minimal fix.
            per_advisory_fix = [_min_version(a.fixed_versions, dep.ecosystem) for a in advisories]
            fixed = _max_version([v for v in per_advisory_fix if v], dep.ecosystem)
            unfixed = sum(1 for v in per_advisory_fix if v is None)
            evidence = [self._manifest_evidence(ctx, dep)]
            for adv in advisories[:12]:
                evidence.append(
                    EvidenceDraft(
                        source_type=SourceType.DEPENDENCY,
                        source=lookup.source,
                        tool="osv-advisory-lookup",
                        excerpt=f"{adv.id} [{adv.severity}] {adv.summary}"[:600],
                        raw_reference=adv.url or f"https://osv.dev/vulnerability/{adv.id}",
                        confidence=0.9,
                        data={
                            "advisory_id": adv.id,
                            "aliases": adv.aliases[:6],
                            "severity": adv.severity,
                            "fixed_versions": adv.fixed_versions,
                        },
                    )
                )
            sensitive = dep.name in SECURITY_SENSITIVE_PACKAGES
            finding = ctx.publish(
                FindingDraft(
                    category=Category.DEPENDENCY,
                    rule_id="dependency.vulnerable",
                    title=f"{dep.display_name} {dep.version} is affected by {len(advisories)} known vulnerabilit{'y' if len(advisories) == 1 else 'ies'}",
                    description=(
                        f"{dep.display_name}=={dep.version} (declared in {dep.manifest}) matches {len(advisories)} distinct advisories in "
                        f"{lookup.source}. Highest severity: {max_sev.upper()}. "
                        + (f"Version {fixed} fixes {'all' if not unfixed else len(advisories) - unfixed} of them." if fixed else "")
                        + (f" {unfixed} advisory(ies) have no published fix." if unfixed else "")
                    ),
                    severity=severity,
                    subject=f"pkg:{dep.ecosystem}/{dep.name}",
                    affected_files=[dep.manifest],
                    affected_components=["dependencies"] + (["authentication"] if sensitive else []),
                    attributes={
                        "package": dep.name,
                        "display_name": dep.display_name,
                        "ecosystem": dep.ecosystem,
                        "version": dep.version,
                        "import_name": import_name_for(dep.name, dep.ecosystem),
                        "vulnerable": True,
                        "advisory_ids": [a.id for a in advisories],
                        "advisory_max_severity": max_sev,
                        "fixed_version": fixed,
                        "security_sensitive_package": sensitive,
                        "advisory_source": lookup.source,
                    },
                    tool_results=[{"tool": "osv", "source": lookup.source, "advisories": len(advisories)}],
                    reasoning_summary=(
                        f"Exact pinned version {dep.version} matched {len(advisories)} advisory groups (aliases merged). "
                        f"Severity taken from the advisory database, not estimated. Whether the vulnerable code is reachable "
                        f"in this repository is not established by this agent."
                    ),
                    recommended_action=f"Upgrade {dep.display_name} to {fixed or 'a fixed release'} or later.",
                ),
                evidence,
            )
            if severity in (Severity.CRITICAL, Severity.HIGH):
                ctx.request_investigation(
                    f"Assess real-world impact of vulnerable {dep.display_name} {dep.version} (usage, upgrade compatibility, test coverage)",
                    reason=f"{len(advisories)} advisories, highest {max_sev}; impact depends on how the package is used",
                    required_evidence="impact_analysis",
                    focus={
                        "package": dep.name,
                        "import_name": import_name_for(dep.name, dep.ecosystem),
                        "current_version": dep.version,
                        "target_version": fixed,
                        "finding_id": finding.finding_id,
                        "security_sensitive": sensitive,
                    },
                    related_finding_ids=[finding.finding_id],
                )
        if unavailable:
            ctx.limitation("Advisory data unavailable (INSUFFICIENT EVIDENCE) for: " + "; ".join(unavailable[:10]))
        pinned = [d for d in self.deps if d.version]
        ctx.analyzed(f"Vulnerability lookup for {len(pinned)} exactly-versioned dependencies")

    def _freshness(self, ctx: AgentContext) -> None:
        now = datetime.now(UTC)
        unavailable = []
        for dep in self.deps:
            info = ctx.tool("registry_lookup", ctx.services.registry.package_info, dep)
            if info.status != "ok":
                if info.status == "unavailable":
                    unavailable.append(dep.display_name)
                continue
            dep_info = {"latest": info.latest_version, "license": info.license}
            ctx.coverage.setdefault("registry", {})[dep.name] = dep_info
            latest_age = age_in_days(info.latest_release_date, now)
            if latest_age is not None and latest_age > 730:
                ctx.publish(
                    FindingDraft(
                        category=Category.DEPENDENCY,
                        rule_id="dependency.abandoned",
                        title=f"{dep.display_name} appears unmaintained (latest release {latest_age // 365}+ years ago)",
                        description=f"The newest release of {dep.display_name} ({info.latest_version}) was published {latest_age} days ago.",
                        severity=Severity.MEDIUM,
                        subject=f"pkg:{dep.ecosystem}/{dep.name}",
                        affected_files=[dep.manifest],
                        affected_components=["dependencies"],
                        attributes={"package": dep.name, "latest_version": info.latest_version, "latest_release_age_days": latest_age},
                        reasoning_summary="Registry metadata shows no release for over two years.",
                        recommended_action=f"Evaluate maintained alternatives to {dep.display_name}.",
                    ),
                    [
                        self._manifest_evidence(ctx, dep),
                        EvidenceDraft(
                            source_type=SourceType.DEPENDENCY,
                            source=info.source,
                            tool="registry-metadata",
                            excerpt=f"latest={info.latest_version} released {info.latest_release_date}",
                            confidence=0.9,
                        ),
                    ],
                )
            current = dep.version
            gap = version_gap(current, info.latest_version, dep.ecosystem) if current else None
            if gap in ("major", "minor"):
                pinned_age = age_in_days(info.pinned_release_date, now)
                severity = Severity.MEDIUM if gap == "major" else Severity.LOW
                age_text = f", released {pinned_age // 365} year(s) ago" if pinned_age and pinned_age > 365 else ""
                ctx.publish(
                    FindingDraft(
                        category=Category.DEPENDENCY,
                        rule_id="dependency.outdated",
                        title=f"{dep.display_name} {current} is a {gap} version behind latest {info.latest_version}{age_text}",
                        description=(
                            f"{dep.display_name} is pinned at {current}; the registry's latest release is {info.latest_version} "
                            f"({info.latest_release_date or 'date unknown'}). A {gap}-version gap usually means accumulated fixes and API changes."
                        ),
                        severity=severity,
                        subject=f"pkg:{dep.ecosystem}/{dep.name}",
                        affected_files=[dep.manifest],
                        affected_components=["dependencies"],
                        attributes={
                            "package": dep.name,
                            "version": current,
                            "latest_version": info.latest_version,
                            "gap": gap,
                            "pinned_release_age_days": pinned_age,
                        },
                        reasoning_summary="Deterministic comparison of the pinned version with registry metadata.",
                        recommended_action=f"Plan an upgrade of {dep.display_name} to {info.latest_version}.",
                    ),
                    [
                        self._manifest_evidence(ctx, dep),
                        EvidenceDraft(
                            source_type=SourceType.DEPENDENCY,
                            source=info.source,
                            tool="registry-metadata",
                            excerpt=f"latest={info.latest_version} ({info.latest_release_date}); pinned {current} released {info.pinned_release_date}",
                            confidence=0.9,
                        ),
                    ],
                )
        if unavailable:
            ctx.limitation("Registry metadata unavailable (INSUFFICIENT EVIDENCE) for: " + ", ".join(unavailable[:10]))

    def _pinning(self, ctx: AgentContext) -> None:
        runtime_unpinned = [d for d in self.deps if not d.pinned and not d.dev and not d.resolved_from]
        if runtime_unpinned:
            by_manifest: dict[str, list[Dependency]] = defaultdict(list)
            for d in runtime_unpinned:
                by_manifest[d.manifest].append(d)
            for manifest, deps in by_manifest.items():
                names = ", ".join(f"{d.display_name}{d.spec if d.spec != '*' else ''}" for d in deps[:8])
                ctx.publish(
                    FindingDraft(
                        category=Category.DEPENDENCY,
                        rule_id="dependency.unpinned",
                        title=f"{len(deps)} runtime dependenc{'y is' if len(deps) == 1 else 'ies are'} not pinned to exact versions ({names})",
                        description=(
                            f"{manifest} declares {len(deps)} runtime dependencies with open version ranges and no lockfile. "
                            "Builds are not reproducible and a compromised or broken release can be picked up automatically."
                        ),
                        severity=Severity.LOW,
                        subject=f"manifest:{manifest}",
                        affected_files=[manifest],
                        affected_components=["dependencies"],
                        attributes={"packages": [d.name for d in deps], "specs": {d.name: d.spec for d in deps}},
                        reasoning_summary="Manifest specs are ranges (not ==) and no lockfile resolves them.",
                        recommended_action="Pin exact versions or add a lockfile (pip-tools / uv / poetry lock).",
                    ),
                    [self._manifest_evidence(ctx, d) for d in deps[:8]],
                )
        specs: dict[str, set[str]] = defaultdict(set)
        where: dict[str, list[Dependency]] = defaultdict(list)
        for d in self.deps:
            specs[d.key].add(d.spec)
            where[d.key].append(d)
        for key, values in specs.items():
            if len(values) > 1:
                deps = where[key]
                ctx.publish(
                    FindingDraft(
                        category=Category.DEPENDENCY,
                        rule_id="dependency.conflicting_specs",
                        title=f"{deps[0].display_name} is declared with conflicting version specs ({', '.join(sorted(values))})",
                        description="The same package is constrained differently in multiple manifests, which can resolve inconsistently.",
                        severity=Severity.LOW,
                        subject=f"pkg:{deps[0].ecosystem}/{deps[0].name}",
                        affected_files=sorted({d.manifest for d in deps}),
                        affected_components=["dependencies"],
                        attributes={"package": deps[0].name, "specs": sorted(values)},
                        reasoning_summary="Deterministic comparison of declared specs across manifests.",
                        recommended_action="Use a single source of truth for dependency versions.",
                    ),
                    [self._manifest_evidence(ctx, d) for d in deps],
                )
