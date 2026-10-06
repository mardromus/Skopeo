"""Correlation Agent — reasons *across* independent findings (it is not a summariser).

Candidate relationships are generated deterministically from typed links between findings
(shared package, file, component, subject, opposing stances). Each candidate is then assessed
(LLM in live mode, transparent policy in mock mode) and written to the blackboard as a
Correlation with a risk multiplier and a confidence derived from member confidence and link
strength. Contradictions are flagged for adjudication by the red-team.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.agents.base import Agent, AgentContext
from app.schemas import AgentOutcome, CorrelationDraft, EventType, FindingOut, RelationshipType
from app.services.risk_scoring import SECURITY_CRITICAL_COMPONENTS
from app.tools.repository import is_test_path


@dataclass
class Candidate:
    relationship_type: RelationshipType
    members: list[FindingOut]
    title: str
    description: str
    multiplier: float
    link_strength: float
    signature: str
    links: list[dict] = field(default_factory=list)
    reasoning: str = ""


class CorrelationAssessment(BaseModel):
    accept: bool
    title: str = Field(max_length=300)
    description: str = Field(max_length=1500)
    confidence_adjustment: float = Field(default=0.0, ge=-0.3, le=0.1)
    rationale: str = Field(max_length=600)


def packages_of(f: FindingOut) -> set[str]:
    a = f.attributes or {}
    out = set(a.get("packages") or []) | set(a.get("related_packages") or [])
    if a.get("package"):
        out.add(a["package"])
    return {p.lower() for p in out}


def _geo_mean(values: list[float]) -> float:
    values = [max(0.01, v) for v in values]
    return math.exp(sum(math.log(v) for v in values) / len(values))


class CorrelationAgent(Agent):
    name = "correlation_agent"
    display_name = "Correlation Agent"
    description = "Detects compound risks, shared root causes, causal chains, duplicates and contradictions across agents."

    def run(self, ctx: AgentContext) -> AgentOutcome:
        findings = [f for f in ctx.findings() if f.status.value != "rejected"]
        ctx.tick("generate candidates")
        candidates = self._candidates(findings)
        ctx.message(
            "orchestrator",
            f"Correlation pass over {len(findings)} findings from {len({f.agent for f in findings})} agents: {len(candidates)} candidate relationship(s)",
            payload={"candidates": [c.signature for c in candidates]},
        )
        created = updated = 0
        self.existing = {c.signature: c for c in ctx.store.list_correlations(ctx.investigation_id)}
        for cand in candidates:
            ctx.tick(cand.signature)
            created_flag, changed = self._assess_and_store(ctx, cand)
            created += int(created_flag)
            updated += int(changed and not created_flag)
        return AgentOutcome(
            summary=f"{created} new and {updated} updated correlation(s) from {len(candidates)} candidates",
            coverage={"candidates": len(candidates)},
        )

    # ------------------------------------------------------------ candidates
    def _candidates(self, findings: list[FindingOut]) -> list[Candidate]:
        out: list[Candidate] = []
        out += self._contradictions(findings)
        out += self._shared_root_causes(findings)
        out += self._dependency_compounds(findings)
        out += self._component_clusters(findings)
        out += self._perf_architecture(findings)
        out += self._maintenance_dependency(findings)
        out += self._dependency_links(findings)
        out += self._duplicates(findings)
        return out

    def _contradictions(self, findings: list[FindingOut]) -> list[Candidate]:
        by_subject: dict[str, list[FindingOut]] = defaultdict(list)
        for f in findings:
            if f.subject:
                by_subject[f.subject].append(f)
        out = []
        for subject, group in by_subject.items():
            acceptable = [f for f in group if (f.attributes or {}).get("stance") == "acceptable"]
            issues = [f for f in group if f.severity.value != "info" and (f.attributes or {}).get("stance") != "acceptable"]
            if not acceptable or not issues:
                continue
            issue, ok = issues[0], acceptable[0]
            measured = (issue.attributes or {}).get("measurement") == "measured"
            if measured:
                desc = (
                    f"{issue.agent} reports '{issue.title}' while {ok.agent} assessed the same function as acceptable. "
                    f"Benchmark evidence now supports {issue.agent}; the 'acceptable' assessment relied on the small seed dataset."
                )
            else:
                desc = (
                    f"Disagreement on {subject}: {issue.agent} flags a potential issue ('{issue.title}'), {ok.agent} considers it "
                    f"acceptable ({ok.reasoning_summary}). Potential issue but insufficient evidence — needs measurement to adjudicate."
                )
            out.append(
                Candidate(
                    RelationshipType.CONTRADICTION,
                    [issue, ok],
                    f"Agents disagree about {subject.split('::')[-1]}()",
                    desc,
                    1.0,
                    0.9,
                    f"contradiction:{subject}",
                    [{"type": "same_subject", "value": subject}, {"type": "opposing_stance", "issue": issue.agent, "acceptable": ok.agent}],
                    "Same code subject, opposite stances from different agents.",
                )
            )
        return out

    def _shared_root_causes(self, findings: list[FindingOut]) -> list[Candidate]:
        by_pkg: dict[str, list[FindingOut]] = defaultdict(list)
        for f in findings:
            if f.category.value == "dependency" and (f.attributes or {}).get("package"):
                by_pkg[f.attributes["package"].lower()].append(f)
        out = []
        for pkg, group in by_pkg.items():
            if len(group) < 2:
                continue
            version = next((g.attributes.get("version") for g in group if g.attributes.get("version")), "?")
            out.append(
                Candidate(
                    RelationshipType.SHARED_ROOT_CAUSE,
                    group,
                    f"Shared root cause: stale pin of {pkg} {version}",
                    f"{len(group)} dependency findings ({', '.join(g.rule_id for g in group)}) stem from the same pinned version {pkg}=={version}; one upgrade resolves all of them.",
                    1.0,
                    0.95,
                    f"root:{pkg}",
                    [{"type": "same_package", "value": pkg}],
                    "Same package and version across dependency findings.",
                )
            )
        return out

    def _dependency_compounds(self, findings: list[FindingOut]) -> list[Candidate]:
        out = []
        for v in findings:
            attrs = v.attributes or {}
            if v.category.value != "dependency" or not attrs.get("vulnerable"):
                continue
            pkg = attrs["package"].lower()
            usage = [
                f
                for f in findings
                if f.finding_id != v.finding_id
                and f.category.value != "dependency"
                and pkg in packages_of(f)
                and f.category.value != "testing"
            ]
            if not usage:
                continue
            usage_files = set()
            for u in usage:
                usage_files |= set(u.affected_files) | set((u.attributes or {}).get("usage_files") or [])
            tests = [
                f for f in findings if f.category.value == "testing" and (set(f.affected_files) & usage_files or pkg in packages_of(f))
            ]
            members = [v] + usage + tests
            categories = sorted({m.category.value for m in members})
            comps = Counter(c for u in usage for c in u.affected_components if c in SECURITY_CRITICAL_COMPONENTS)
            component = comps.most_common(1)[0][0] if comps else "application"
            display = attrs.get("display_name", pkg)
            title = (
                f"Compound {component} upgrade risk: vulnerable {display} {attrs.get('version')} in {component} code with insufficient tests"
                if tests
                else f"Vulnerable {display} {attrs.get('version')} is reachable from {component} code"
            )
            parts = [f"{v.agent}: {v.title}"] + [f"{u.agent}: {u.title}" for u in usage] + [f"{t.agent}: {t.title}" for t in tests]
            description = (
                "These findings form a compound risk: "
                + " | ".join(parts)
                + ". "
                + (
                    f"A vulnerable dependency is used in security-critical {component} code whose upgrade is insufficiently tested"
                    if tests
                    else "A vulnerable dependency is used by production code"
                )
                + (
                    " and the upgrade breaks existing call sites."
                    if any(u.rule_id == "api.upgrade_breaking_changes" for u in usage)
                    else "."
                )
            )
            out.append(
                Candidate(
                    RelationshipType.COMPOUND_RISK,
                    members,
                    title,
                    description,
                    min(2.0, 1.0 + 0.25 * (len(categories) - 1)),
                    0.95,
                    f"compound:dep:{pkg}",
                    [
                        {"type": "same_package", "value": pkg},
                        {"type": "usage_files", "value": sorted(usage_files)},
                        {"type": "categories", "value": categories},
                    ],
                    f"Linked through package '{pkg}' (dependency evidence) and usage files {sorted(usage_files)}; {len(categories)} engineering dimensions involved.",
                )
            )
        return out

    def _component_clusters(self, findings: list[FindingOut]) -> list[Candidate]:
        out = []
        for component in sorted(SECURITY_CRITICAL_COMPONENTS):
            sec = [
                f
                for f in findings
                if f.category.value == "security"
                and component in f.affected_components
                and not all(is_test_path(p) for p in f.affected_files or ["x"])
                and f.rule_id not in ("security.vulnerable_dependency_usage", "security.hardcoded_secret")
            ]
            tests = [f for f in findings if f.category.value == "testing" and component in f.affected_components]
            if len(sec) >= 2 and tests or len(sec) >= 3:
                members = sec + tests
                out.append(
                    Candidate(
                        RelationshipType.COMPOUND_RISK,
                        members,
                        f"Concentrated weaknesses in the {component} component ({len(sec)} security findings{', untested' if tests else ''})",
                        f"{len(sec)} independent security weaknesses affect {component} code ("
                        + "; ".join(s.title for s in sec[:4])
                        + ")"
                        + (f", and {tests[0].title.lower()}" if tests else "")
                        + ". Fixing them in isolation without tests risks regressions.",
                        min(1.5, 1.0 + 0.1 * len(sec)),
                        0.8,
                        f"cluster:{component}",
                        [{"type": "same_component", "value": component}],
                        "Shared security-critical component across findings from different agents.",
                    )
                )
        return out

    def _perf_architecture(self, findings: list[FindingOut]) -> list[Candidate]:
        out = []
        perf = [f for f in findings if f.category.value == "performance"]
        quality = [f for f in findings if f.category.value == "code_quality" and (f.attributes or {}).get("stance") != "acceptable"]
        for p in perf:
            related = [q for q in quality if set(q.affected_files) & set(p.affected_files)]
            if related:
                out.append(
                    Candidate(
                        RelationshipType.CAUSAL,
                        [p] + related,
                        f"Performance suspect sits in structurally complex code ({p.affected_files[0]})",
                        f"{p.title} occurs in a file that also has maintainability problems ({related[0].title}); the structure makes the hot path hard to optimise safely.",
                        1.1,
                        0.8,
                        f"perfarch:{p.affected_files[0]}:{p.rule_id}",
                        [{"type": "same_file", "value": p.affected_files[0]}],
                        "Same file across performance and code-quality findings.",
                    )
                )
        return out

    def _maintenance_dependency(self, findings: list[FindingOut]) -> list[Candidate]:
        maint = [
            f
            for f in findings
            if f.category.value == "maintenance" and f.rule_id in ("maintenance.inactive", "maintenance.archived", "maintenance.bus_factor")
        ]
        vulns = [f for f in findings if f.category.value == "dependency" and (f.attributes or {}).get("vulnerable")]
        if maint and vulns:
            return [
                Candidate(
                    RelationshipType.COMPOUND_RISK,
                    maint + vulns,
                    "Vulnerable dependencies in a weakly maintained project",
                    f"{len(vulns)} vulnerable dependenc{'y' if len(vulns) == 1 else 'ies'} combined with {maint[0].title.lower()}: fixes are unlikely to land quickly.",
                    1.3,
                    0.75,
                    "maint:dep",
                    [{"type": "maintenance_to_dependency"}],
                    "Maintenance risk raises the likelihood that dependency risk persists.",
                )
            ]
        return []

    def _dependency_links(self, findings: list[FindingOut]) -> list[Candidate]:
        out = []
        for d in [f for f in findings if f.rule_id == "dependency.unpinned"]:
            for pkg in (d.attributes or {}).get("packages", []):
                related = [f for f in findings if f.category.value not in ("dependency",) and pkg in packages_of(f)]
                if related:
                    out.append(
                        Candidate(
                            RelationshipType.DEPENDENCY,
                            [d] + related,
                            f"Unpinned {pkg} is used on a hot path",
                            f"{pkg} has no exact version pin and is used by: "
                            + "; ".join(r.title for r in related[:3])
                            + ". Behaviour of that path can change with any new release.",
                            1.05,
                            0.85,
                            f"deplink:{pkg}",
                            [{"type": "same_package", "value": pkg}],
                            "Package link between dependency hygiene and code-level findings.",
                        )
                    )
        return out

    def _duplicates(self, findings: list[FindingOut]) -> list[Candidate]:
        out = []
        seen = set()
        for i, a in enumerate(findings):
            for b in findings[i + 1 :]:
                if a.agent == b.agent or a.category != b.category or not (set(a.affected_files) & set(b.affected_files)):
                    continue
                la, lb = set((a.attributes or {}).get("lines") or []), set((b.attributes or {}).get("lines") or [])
                if la and lb and la & lb:
                    key = tuple(sorted((a.finding_id, b.finding_id)))
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(
                        Candidate(
                            RelationshipType.DUPLICATE,
                            [a, b],
                            f"Duplicate report: {a.title}",
                            f"{a.agent} and {b.agent} reported the same location ({sorted(la & lb)}) in {sorted(set(a.affected_files) & set(b.affected_files))[0]}.",
                            1.0,
                            0.9,
                            f"dup:{key[0]}:{key[1]}",
                            [{"type": "same_lines", "value": sorted(la & lb)}],
                            "Overlapping file and line evidence.",
                        )
                    )
        return out

    # ------------------------------------------------------------- assess
    def _assess_and_store(self, ctx: AgentContext, cand: Candidate) -> tuple[bool, bool]:
        base_conf = _geo_mean([m.confidence for m in cand.members]) * cand.link_strength
        member_ids = [m.finding_id for m in cand.members]

        def policy() -> CorrelationAssessment:
            return CorrelationAssessment(
                accept=True, title=cand.title, description=cand.description, confidence_adjustment=0.0, rationale=cand.reasoning
            )

        def validate(a: CorrelationAssessment) -> CorrelationAssessment:
            a.confidence_adjustment = max(-0.3, min(0.1, a.confidence_adjustment))
            return a

        decision = ctx.decide(
            "correlation.assess",
            CorrelationAssessment,
            policy,
            role="You are the Correlation Agent of a multi-agent code-risk system. You judge whether independent findings are genuinely related.",
            task=f"Assess the proposed {cand.relationship_type.value} relationship. Reject it if the findings are not actually connected.",
            structured={
                "relationship_type": cand.relationship_type.value,
                "links": cand.links,
                "members": [
                    {
                        "id": m.finding_id,
                        "agent": m.agent,
                        "category": m.category.value,
                        "title": m.title,
                        "severity": m.severity.value,
                        "files": m.affected_files,
                        "status": m.status.value,
                    }
                    for m in cand.members
                ],
            },
            tier="reasoning",
            validate=validate,
        )
        assessment = decision.value
        if not assessment.accept:
            ctx.message(
                "orchestrator", f"Discarded candidate {cand.signature}: {assessment.rationale}", payload={"decided_by": decision.decided_by}
            )
            return False, False
        confidence = round(max(0.05, min(0.99, base_conf + assessment.confidence_adjustment)), 3)
        corr, created = ctx.store.upsert_correlation(
            ctx.investigation_id,
            CorrelationDraft(
                finding_ids=member_ids,
                relationship_type=cand.relationship_type,
                title=assessment.title,
                description=assessment.description,
                risk_multiplier=round(cand.multiplier, 2),
                confidence=confidence,
                signature=cand.signature,
                links=cand.links,
                reasoning_summary=f"{assessment.rationale} (decided by {decision.decided_by}; confidence = geometric mean of member confidences x link strength {cand.link_strength})",
            ),
        )
        prev = self.existing.get(cand.signature)
        changed = prev is None or prev.description != corr.description or sorted(prev.finding_ids) != sorted(member_ids)
        if created:
            ctx.emit(
                EventType.CORRELATION_CREATED,
                f"{cand.relationship_type.value.replace('_', ' ').title()}: {assessment.title}",
                payload={
                    "correlation_id": corr.correlation_id,
                    "relationship_type": cand.relationship_type.value,
                    "finding_ids": member_ids,
                    "member_titles": [m.title for m in cand.members],
                    "member_agents": sorted({m.agent for m in cand.members}),
                    "risk_multiplier": corr.risk_multiplier,
                    "confidence": confidence,
                    "decided_by": decision.decided_by,
                },
                correlation_id=corr.correlation_id,
            )
        elif changed:
            ctx.emit(
                EventType.CORRELATION_UPDATED,
                f"Re-assessed {cand.relationship_type.value.replace('_', ' ')}: {assessment.title}",
                payload={"correlation_id": corr.correlation_id, "description": assessment.description[:400]},
                correlation_id=corr.correlation_id,
            )
        for m in cand.members:
            if m.status.value == "proposed":
                ctx.store.update_finding(m.finding_id, status="correlated")
        if cand.relationship_type == RelationshipType.CONTRADICTION:
            for m in cand.members:
                ctx.store.recompute_confidence(m.finding_id, contradictions=1)
            if created:
                ctx.message(
                    "verification_agent",
                    f"Contradiction requires adjudication: {assessment.title}. {assessment.description}",
                    payload={"correlation_id": corr.correlation_id, "finding_ids": member_ids},
                    severity="warning",
                )
        elif cand.relationship_type in (RelationshipType.COMPOUND_RISK, RelationshipType.CAUSAL, RelationshipType.SHARED_ROOT_CAUSE):
            for m in cand.members:
                others = len({x.agent for x in cand.members if x.agent != m.agent})
                if others:
                    ctx.store.recompute_confidence(m.finding_id, corroborating_agents=min(3, others))
        return created, changed
