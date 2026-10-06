"""License Compliance Agent — project license, metadata consistency, file-level SPDX headers and
dependency license compatibility."""

from __future__ import annotations

import json
import tomllib
from collections import defaultdict
from pathlib import Path

from app.agents.base import AgentContext, SpecialistAgent, Step
from app.agents.common import components_for
from app.schemas import Category, EvidenceDraft, FindingDraft, Severity, SourceType
from app.tools.licenses import SPDX_HEADER_RE, classify, compatibility_issue, identify_license_text, normalize_expression, normalize_license


class LicenseAgent(SpecialistAgent):
    name = "license_agent"
    display_name = "License Compliance Agent"
    category = "license"
    description = "Identifies the project license, checks metadata consistency, copyleft file headers and dependency license compatibility."

    def plan(self, ctx: AgentContext) -> list[Step]:
        self.project_license: str | None = None
        self.license_file: str | None = None
        return [
            ("identify repository license", self._identify),
            ("check package metadata consistency", self._metadata),
            ("scan SPDX headers in source files", self._headers),
            ("check dependency licenses", self._dependencies),
        ]

    def _identify(self, ctx: AgentContext) -> None:
        candidates = [
            f for f in ctx.tools.list_files() if "/" not in f and Path(f).name.upper().split(".")[0] in ("LICENSE", "LICENCE", "COPYING")
        ]
        for rel in candidates:
            text = ctx.tools.try_get_file(rel) or ""
            spdx = identify_license_text(text)
            if spdx:
                self.project_license, self.license_file = spdx, rel
                break
        if not candidates:
            ctx.publish(
                FindingDraft(
                    category=Category.LICENSE,
                    rule_id="license.missing",
                    title="Repository has no LICENSE file",
                    description="Without a license, default copyright applies and others cannot legally reuse the code.",
                    severity=Severity.MEDIUM,
                    subject="license:project",
                    affected_files=[],
                    affected_components=["legal"],
                    attributes={},
                    reasoning_summary="No LICENSE/COPYING file at the repository root.",
                    recommended_action="Add a LICENSE file with an OSI-approved license.",
                ),
                [
                    EvidenceDraft(
                        source_type=SourceType.STATIC_ANALYSIS,
                        source="repository root listing",
                        tool="list_files",
                        excerpt="no LICENSE/LICENCE/COPYING file found",
                        confidence=0.9,
                    )
                ],
            )
        elif not self.project_license:
            ctx.limitation(f"License text in {candidates[0]} not recognised (INSUFFICIENT EVIDENCE for classification)")
        ctx.analyzed(f"Project license: {self.project_license or 'unknown'} ({self.license_file or 'no file'})")

    def _metadata(self, ctx: AgentContext) -> None:
        declared: list[tuple[str, str, int | None]] = []
        if ctx.tools.exists("pyproject.toml"):
            text = ctx.tools.get_file("pyproject.toml")
            try:
                data = tomllib.loads(text)
                lic = (data.get("project") or {}).get("license")
                if isinstance(lic, dict):
                    lic = lic.get("text") or lic.get("file")
                if isinstance(lic, str):
                    line = next((i for i, ln in enumerate(text.splitlines(), 1) if ln.strip().startswith("license")), None)
                    declared.append(("pyproject.toml", lic, line))
            except tomllib.TOMLDecodeError:
                ctx.limitation("pyproject.toml could not be parsed")
        if ctx.tools.exists("package.json"):
            try:
                text = ctx.tools.get_file("package.json")
                lic = json.loads(text).get("license")
                if isinstance(lic, str):
                    line = next((i for i, ln in enumerate(text.splitlines(), 1) if '"license"' in ln), None)
                    declared.append(("package.json", lic, line))
            except json.JSONDecodeError:
                pass
        if ctx.tools.exists("Cargo.toml"):
            try:
                text = ctx.tools.get_file("Cargo.toml")
                lic = (tomllib.loads(text).get("package") or {}).get("license")
                if isinstance(lic, str):
                    declared.append(("Cargo.toml", lic, None))
            except tomllib.TOMLDecodeError:
                pass
        for manifest, value, line in declared:
            norm = normalize_license(value)
            if self.project_license and norm and norm != self.project_license:
                lines = ctx.tools.get_file(manifest).splitlines()
                ctx.publish(
                    FindingDraft(
                        category=Category.LICENSE,
                        rule_id="license.metadata_mismatch",
                        title=f"License metadata mismatch: {manifest} declares {norm} but {self.license_file} is {self.project_license}",
                        description=(
                            f"Package metadata ({manifest}) says '{value}' while the license text in {self.license_file} is {self.project_license}. "
                            "Downstream users and scanners receive contradictory terms."
                        ),
                        severity=Severity.MEDIUM,
                        subject="license:project",
                        affected_files=[manifest, self.license_file or "LICENSE"],
                        affected_components=["legal", "packaging"],
                        attributes={"declared": norm, "license_file": self.project_license},
                        reasoning_summary="License file fingerprint and manifest field normalised to SPDX and compared.",
                        recommended_action=f"Make {manifest} and {self.license_file} agree (decide which license is intended).",
                    ),
                    [
                        EvidenceDraft(
                            source_type=SourceType.STATIC_ANALYSIS,
                            source=manifest,
                            tool="manifest-license",
                            file=manifest,
                            line_start=line,
                            line_end=line,
                            excerpt=lines[line - 1] if line else value,
                            confidence=0.95,
                        ),
                        EvidenceDraft(
                            source_type=SourceType.STATIC_ANALYSIS,
                            source=self.license_file or "LICENSE",
                            tool="license-fingerprint",
                            file=self.license_file,
                            line_start=1,
                            line_end=1,
                            excerpt=(ctx.tools.get_file(self.license_file).splitlines() or [""])[0] if self.license_file else "",
                            confidence=0.95,
                        ),
                    ],
                )
            elif not self.project_license and norm:
                self.project_license = norm
        if not declared:
            ctx.analyzed("No license field in package metadata")

    def _headers(self, ctx: AgentContext) -> None:
        by_license: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
        for rel in ctx.tools.list_files(suffixes=(".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".h", ".cpp")):
            text = ctx.tools.try_get_file(rel)
            if not text:
                continue
            for i, line in enumerate(text.splitlines()[:30], start=1):
                m = SPDX_HEADER_RE.search(line)
                if m:
                    for lic in normalize_expression(m.group(1).strip()) or [m.group(1).strip()]:
                        by_license[lic].append((rel, i, line.strip()))
                    break
        if not by_license:
            ctx.analyzed("No SPDX headers found in source files")
        for lic, files in by_license.items():
            issue = compatibility_issue(self.project_license, lic)
            if not issue:
                continue
            severity, explanation = issue
            ctx.publish(
                FindingDraft(
                    category=Category.LICENSE,
                    rule_id="license.copyleft_file",
                    title=f"{lic} licensed source in a {self.project_license} project ({', '.join(f for f, _, _ in files[:3])})",
                    description=explanation + ". Files: " + ", ".join(f"{f}:{ln}" for f, ln, _ in files[:6]),
                    severity=Severity(severity),
                    subject=f"license-file:{lic}",
                    affected_files=[f for f, _, _ in files],
                    affected_components=sorted({c for f, _, _ in files for c in components_for(f)}) + ["legal"],
                    attributes={"file_license": lic, "project_license": self.project_license, "license_class": classify(lic)},
                    reasoning_summary="SPDX-License-Identifier header compared with the project license using a copyleft compatibility matrix.",
                    recommended_action=f"Replace the {lic} code, obtain it under a compatible license, or relicense consciously.",
                ),
                [
                    EvidenceDraft(
                        source_type=SourceType.STATIC_ANALYSIS,
                        source=f"{f}:{ln}",
                        tool="spdx-header-scan",
                        file=f,
                        line_start=ln,
                        line_end=ln,
                        excerpt=text,
                        confidence=0.95,
                    )
                    for f, ln, text in files[:6]
                ],
            )

    def _dependencies(self, ctx: AgentContext) -> None:
        deps = ctx.tool("inspect_dependencies", ctx.tools.inspect_dependencies)
        unknown, checked = [], 0
        for dep in deps:
            info = ctx.tool("registry_lookup", ctx.services.registry.package_info, dep)
            if info.status != "ok":
                unknown.append(f"{dep.display_name} ({info.status})")
                continue
            checked += 1
            licenses = normalize_expression(info.license)
            if not licenses:
                unknown.append(f"{dep.display_name} ('{info.license}')")
                continue
            # For "A OR B" the most permissive option can be chosen.
            issues = [compatibility_issue(self.project_license, lic) for lic in licenses]
            if all(issues) and issues:
                severity, explanation = issues[0]  # type: ignore[misc]
                ctx.publish(
                    FindingDraft(
                        category=Category.LICENSE,
                        rule_id="license.dependency_incompatible",
                        title=f"Dependency {dep.display_name} is licensed {info.license} (incompatible with {self.project_license})",
                        description=explanation,
                        severity=Severity(severity),
                        subject=f"pkg:{dep.ecosystem}/{dep.name}",
                        affected_files=[dep.manifest],
                        affected_components=["dependencies", "legal"],
                        attributes={"package": dep.name, "license": info.license},
                        reasoning_summary="Registry license metadata compared with project license.",
                        recommended_action=f"Replace {dep.display_name} or confirm the obligations are acceptable.",
                    ),
                    [
                        EvidenceDraft(
                            source_type=SourceType.DEPENDENCY,
                            source=info.source,
                            tool="registry-metadata",
                            file=dep.manifest,
                            line_start=dep.line,
                            line_end=dep.line,
                            excerpt=f"{dep.display_name}: license={info.license}",
                            confidence=0.85,
                        )
                    ],
                )
        ctx.analyzed(f"Dependency licenses checked for {checked} package(s)")
        if unknown:
            ctx.limitation("License unknown/unavailable (INSUFFICIENT EVIDENCE) for: " + ", ".join(unknown[:10]))
