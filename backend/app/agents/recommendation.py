"""Recommendation Agent — actionable, reviewable remediation for verified risks, plus GitHub
action *proposals* (issues / draft PRs) that always require human approval."""

from __future__ import annotations

import difflib

from pydantic import BaseModel, Field

from app.agents.base import Agent, AgentContext
from app.schemas import AgentOutcome, EventType, FindingOut
from app.schemas.investigation import RiskOut


class RecommendationText(BaseModel):
    title: str = Field(max_length=300)
    problem: str = Field(max_length=1500)
    why_it_matters: str = Field(max_length=1500)
    proposed_fix: str = Field(max_length=3000)
    expected_benefit: str = Field(max_length=800)
    implementation_difficulty: str = Field(pattern="^(low|medium|high)$")


_TEMPLATES: dict[str, dict[str, str]] = {
    "security.jwt_no_algorithms": {
        "why": "An attacker controls the token header; without an allow-list the library may accept an algorithm the server never intended (e.g. key confusion).",
        "fix": "Pass algorithms=['HS256'] (or the single algorithm you issue) to every jwt.decode call; add tests that tokens with other algorithms are rejected.",
        "benefit": "Closes the algorithm-confusion class of token forgery.",
        "difficulty": "low",
    },
    "security.hardcoded_default_secret": {
        "why": "If the environment variable is missing in any deployment, tokens are signed with a public literal and can be forged by anyone who reads the code.",
        "fix": "Remove the literal fallback and fail fast at start-up when the secret is not configured. Rotating the existing secret is a human action outside Skopeo's authority.",
        "benefit": "Prevents silent insecure deployments.",
        "difficulty": "low",
    },
    "security.weak_password_hash": {
        "why": "MD5/SHA1 are fast and unsalted; leaked hashes can be cracked at billions of guesses per second.",
        "fix": "Hash passwords with argon2id (argon2-cffi) or bcrypt; re-hash on next successful login and expire legacy hashes.",
        "benefit": "Makes offline cracking of leaked credentials impractical.",
        "difficulty": "medium",
    },
    "security.prompt_injection_content": {
        "why": "AI-based tooling (review bots, assistants) that reads this repository may follow the embedded instructions.",
        "fix": "Remove the AI-directed instructions from repository content; make CI bots treat repository text as untrusted data.",
        "benefit": "Reduces AI supply-chain manipulation risk.",
        "difficulty": "low",
    },
    "testing.test_failure": {
        "why": "A red test means either shipped behaviour is wrong or the suite is not trusted — both erode the safety net.",
        "fix": "Fix the code under test (or the test, if its expectation is wrong) and keep the test in CI.",
        "benefit": "Restores a green, trustworthy suite and fixes user-visible output.",
        "difficulty": "low",
    },
    "testing.untested_critical_path": {
        "why": "Security-critical code changes (including dependency upgrades) ship without any regression signal.",
        "fix": "Add unit tests for the component: valid token, expired token, tampered signature, wrong algorithm, missing header; password verify success/failure.",
        "benefit": "Makes security fixes and upgrades safe to ship.",
        "difficulty": "medium",
    },
    "performance.n_plus_one": {
        "why": "Query count grows linearly with rows, so latency and database load grow with every new order.",
        "fix": "Load items for all orders in one query (WHERE order_id IN (...) or a JOIN) and group them in memory.",
        "benefit": "Constant query count per request; measured 1+N queries become 2.",
        "difficulty": "low",
    },
    "performance.network_in_loop": {
        "why": "One blocking HTTP call per customer makes latency proportional to the audience size.",
        "fix": "Use a bulk notification endpoint or a bounded concurrent pool with a shared Session.",
        "benefit": "Notification latency independent of recipient count.",
        "difficulty": "medium",
    },
    "license.metadata_mismatch": {
        "why": "Contradictory license metadata creates legal ambiguity for every downstream user and fails compliance scanners.",
        "fix": "Decide the intended license and make the LICENSE file and package metadata identical.",
        "benefit": "Clear, consistent licensing.",
        "difficulty": "low",
    },
    "license.copyleft_file": {
        "why": "Strong-copyleft code inside a permissive project changes the distribution terms of the combined work.",
        "fix": "Replace the vendored copyleft code with a permissively licensed or stdlib implementation (e.g. Python's csv module).",
        "benefit": "Removes copyleft obligations from distribution.",
        "difficulty": "low",
    },
    "code_quality.high_complexity": {
        "why": "High cyclomatic complexity correlates with defects and makes changes risky to review and test.",
        "fix": "Extract filtering and per-item formatting into small functions; cover each branch with a test.",
        "benefit": "Easier review and safer change.",
        "difficulty": "medium",
    },
}


class RecommendationAgent(Agent):
    name = "recommendation_agent"
    display_name = "Recommendation Agent"
    description = "Turns verified, prioritised risks into reviewable remediation and approval-gated GitHub action proposals."

    def run(self, ctx: AgentContext) -> AgentOutcome:
        risks = [r for r in ctx.store.list_risks(ctx.investigation_id) if r.priority in ("P0", "P1", "P2", "P3")]
        findings = {f.finding_id: f for f in ctx.findings()}
        covered: set[str] = set()
        inv = ctx.store.get_investigation(ctx.investigation_id)
        recs = 0
        for risk in sorted(risks, key=lambda r: (r.kind != "compound", -r.score)):
            ctx.tick(risk.title[:60])
            if risk.kind == "finding" and risk.finding_id in covered:
                continue
            members = [findings[i] for i in risk.member_finding_ids if i in findings]
            if not members:
                continue
            rec = self._recommend(ctx, risk, members, findings)
            recs += 1
            if risk.kind == "compound":
                covered.update(risk.member_finding_ids)
            if risk.priority in ("P0", "P1"):
                self._propose_actions(ctx, risk, rec, members, inv)
        return AgentOutcome(summary=f"{recs} recommendation(s) generated", coverage={"recommendations": recs})

    def _recommend(self, ctx: AgentContext, risk: RiskOut, members: list[FindingOut], all_findings: dict[str, FindingOut]):
        lead = members[0]
        component = ", ".join(sorted({c for m in members for c in m.affected_components if c not in ("tests", "dependencies")})[:3]) or (
            lead.affected_files[0] if lead.affected_files else "repository"
        )

        def policy() -> RecommendationText:
            if risk.kind == "compound":
                dep = next((m for m in members if m.category.value == "dependency" and m.attributes.get("vulnerable")), None)
                api = next((m for m in members if m.rule_id == "api.upgrade_breaking_changes"), None)
                tests = [m for m in members if m.category.value == "testing"]
                steps = []
                if dep:
                    steps.append(
                        f"1. Upgrade {dep.attributes.get('display_name', dep.attributes.get('package'))} from {dep.attributes.get('version')} to {dep.attributes.get('fixed_version') or 'a fixed release'} or later (resolves {len(dep.attributes.get('advisory_ids', []))} advisories)."
                    )
                if api:
                    steps.append(
                        f"{len(steps) + 1}. In the same change, update the breaking call sites ({', '.join(api.attributes.get('call_sites', [])[:4])}): "
                        + " ".join(api.attributes.get("fixes", []))
                    )
                if tests:
                    steps.append(
                        f"{len(steps) + 1}. Add regression tests for {', '.join(sorted({f for t in tests for f in t.affected_files})[:3])} before merging (valid/expired/tampered tokens, wrong algorithm)."
                    )
                others = [m for m in members if m not in ([dep] if dep else []) + ([api] if api else []) + tests]
                for o in others[:3]:
                    tmpl = _TEMPLATES.get(o.rule_id)
                    if tmpl:
                        steps.append(f"{len(steps) + 1}. {o.title}: {tmpl['fix']}")
                steps.append(f"{len(steps) + 1}. Re-run Skopeo to confirm the compound risk is closed.")
                return RecommendationText(
                    title=f"Fix compound risk: {risk.title}"[:300],
                    problem=risk.title + ". " + " | ".join(m.title for m in members[:5]),
                    why_it_matters=f"Independent agents verified {len(members)} linked problems across {len({m.category.value for m in members})} dimensions; together they are worse than each alone (multiplier {risk.correlation_multiplier}).",
                    proposed_fix="\n".join(steps),
                    expected_benefit=f"Closes a {risk.priority} risk (score {risk.score}) and makes the upgrade path safe.",
                    implementation_difficulty="medium" if api or tests else "low",
                )
            tmpl = dict(_TEMPLATES.get(lead.rule_id, {}))
            if lead.rule_id == "testing.test_failure":
                tmpl["fix"] = (
                    f"Reproduce with `{lead.attributes.get('reproducible_command')}` (observed: {lead.attributes.get('message') or 'see output'}). "
                    + tmpl["fix"]
                )
            if lead.rule_id == "performance.n_plus_one" and lead.attributes.get("benchmark"):
                tmpl["benefit"] = (
                    "Constant query count per request instead of the measured "
                    + (lead.attributes["benchmark"].get("verdict") or {}).get("summary", "linear growth")
                    + "."
                )
            if lead.rule_id == "dependency.vulnerable":
                api = next(
                    (
                        f
                        for f in all_findings.values()
                        if f.rule_id == "api.upgrade_breaking_changes" and f.attributes.get("package") == lead.attributes.get("package")
                    ),
                    None,
                )
                fix = f"Upgrade {lead.attributes.get('display_name')} to {lead.attributes.get('fixed_version') or 'a fixed release'}+." + (
                    f" Note: {api.title}; update call sites in the same change." if api else ""
                )
                tmpl = {
                    "why": f"{len(lead.attributes.get('advisory_ids', []))} published advisories affect the pinned version.",
                    "fix": fix,
                    "benefit": "Removes known vulnerabilities.",
                    "difficulty": "medium" if api else "low",
                }
            return RecommendationText(
                title=f"{lead.title}"[:300],
                problem=lead.description[:1500],
                why_it_matters=tmpl.get("why", f"Verified {lead.category.value} risk with priority {risk.priority}."),
                proposed_fix=tmpl.get("fix") or lead.recommended_action or "Review and remediate.",
                expected_benefit=tmpl.get("benefit", f"Reduces a {risk.priority} risk (score {risk.score})."),
                implementation_difficulty=tmpl.get("difficulty", "medium"),
            )

        decision = ctx.decide(
            "recommendation.write",
            RecommendationText,
            policy,
            role="You write precise, actionable engineering remediation for verified risks. Never invent findings.",
            task="Write a remediation recommendation for this verified risk using only the given facts.",
            structured={
                "risk": risk.model_dump(mode="json"),
                "findings": [
                    {
                        "title": m.title,
                        "rule": m.rule_id,
                        "attributes": {k: v for k, v in m.attributes.items() if k != "confidence_inputs"},
                        "recommended_action": m.recommended_action,
                    }
                    for m in members
                ],
            },
        )
        text = decision.value
        rec = ctx.store.add_recommendation(
            ctx.investigation_id,
            risk_id=risk.risk_id,
            finding_ids=[m.finding_id for m in members],
            title=text.title,
            problem=text.problem,
            affected_component=component,
            why_it_matters=text.why_it_matters,
            proposed_fix=text.proposed_fix,
            estimated_risk={"priority": risk.priority, "score": risk.score},
            verification_status="verified",
            expected_benefit=text.expected_benefit,
            implementation_difficulty=text.implementation_difficulty,
            priority=risk.priority,
        )
        ctx.emit(
            EventType.RECOMMENDATION_CREATED,
            f"{risk.priority} recommendation: {text.title}",
            receiver="human",
            payload={"recommendation_id": rec.recommendation_id, "risk_id": risk.risk_id, "decided_by": decision.decided_by},
        )
        return rec

    def _propose_actions(self, ctx: AgentContext, risk: RiskOut, rec, members: list[FindingOut], inv) -> None:
        target = ctx.repo.full_name
        evidence_lines = "\n".join(f"- [{m.severity.value}] {m.title} ({m.agent}, confidence {m.confidence:.2f})" for m in members[:8])
        body = (
            f"## {rec.title}\n\n**Priority:** {risk.priority} (score {risk.score}) — verified by Skopeo's red-team agent.\n\n"
            f"### Problem\n{rec.problem}\n\n### Why it matters\n{rec.why_it_matters}\n\n### Proposed fix\n{rec.proposed_fix}\n\n"
            f"### Evidence\n{evidence_lines}\n\n_Proposed by Skopeo. Requires human review; Skopeo never merges or deploys._"
        )
        action = ctx.store.add_action(
            ctx.investigation_id,
            recommendation_id=rec.recommendation_id,
            action_type="github_issue",
            title=f"[Skopeo {risk.priority}] {rec.title}"[:250],
            body=body,
            target_repository=target,
            status="proposed",
            requires_approval=True,
            risk_score=risk.score,
            result={"executable": bool(inv and inv.enable_github_actions and ctx.repo.source == "github")},
        )
        ctx.emit(
            EventType.GITHUB_ACTION_PROPOSED,
            f"ACTION PROPOSED: GitHub issue '{action.title}'",
            receiver="human",
            payload={"action_id": action.action_id, "type": "github_issue"},
        )
        dep = next((m for m in members if m.rule_id == "dependency.vulnerable"), None)
        if dep and dep.affected_files:
            manifest = dep.affected_files[0]
            original = ctx.tools.try_get_file(manifest) or ""
            outdated = next(
                (
                    f
                    for f in ctx.findings(category="dependency")
                    if f.rule_id == "dependency.outdated" and f.attributes.get("package") == dep.attributes.get("package")
                ),
                None,
            )
            target_version = (outdated.attributes.get("latest_version") if outdated else None) or dep.attributes.get("fixed_version")
            new_lines = []
            changed = False
            for line in original.splitlines(keepends=True):
                stripped = line.strip()
                if target_version and stripped.lower().startswith(f"{dep.attributes.get('display_name', '').lower()}=="):
                    new_lines.append(f"{dep.attributes.get('display_name')}=={target_version}\n")
                    changed = True
                else:
                    new_lines.append(line)
            if changed:
                patch = "".join(
                    difflib.unified_diff(original.splitlines(keepends=True), new_lines, fromfile=f"a/{manifest}", tofile=f"b/{manifest}")
                )
                api = next((m for m in members if m.rule_id == "api.upgrade_breaking_changes"), None)
                pr = ctx.store.add_action(
                    ctx.investigation_id,
                    recommendation_id=rec.recommendation_id,
                    action_type="pull_request",
                    title=f"[Skopeo] Upgrade {dep.attributes.get('display_name')} to {target_version} (draft)",
                    body=body + ("\n\n**Warning:** this bump alone breaks call sites — " + api.title if api else ""),
                    patch=patch,
                    target_repository=target,
                    status="proposed",
                    requires_approval=True,
                    risk_score=risk.score,
                    result={
                        "executable": bool(inv and inv.enable_github_actions and ctx.repo.source == "github"),
                        "files": {manifest: "".join(new_lines)},
                        "draft": True,
                    },
                )
                ctx.emit(
                    EventType.GITHUB_ACTION_PROPOSED,
                    f"ACTION PROPOSED: draft PR '{pr.title}'",
                    receiver="human",
                    payload={"action_id": pr.action_id, "type": "pull_request"},
                )
