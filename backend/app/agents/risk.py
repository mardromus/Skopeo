"""Risk Assessment Agent — scores ONLY verified findings and verified correlations.

    Risk = Severity x Confidence x Impact x Exploitability x CorrelationMultiplier  -> 0..100 -> P0..P4

Rejected and unverified ("INSUFFICIENT EVIDENCE") findings are listed as excluded, with reasons.
"""

from __future__ import annotations

from app.agents.base import Agent, AgentContext
from app.schemas import AgentOutcome, EventType, FindingOut
from app.services.risk_scoring import compute_risk, exploitability_for, impact_for, overall_risk

# Compound risks are scored once, as their own risk entry; members are not multiplied again.
_MULTIPLYING = ("causal", "dependency")
_SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


class RiskAgent(Agent):
    name = "risk_agent"
    display_name = "Risk Assessment Agent"
    description = "Prioritises verified risks (P0-P4) with a transparent, explainable score."

    def run(self, ctx: AgentContext) -> AgentOutcome:
        ctx.store.clear_risks(ctx.investigation_id)
        findings = ctx.findings()
        correlations = [c for c in ctx.store.list_correlations(ctx.investigation_id) if c.status.value == "verified"]
        by_id = {f.finding_id: f for f in findings}
        verified = [f for f in findings if f.status.value == "verified" and f.severity.value != "info"]
        excluded = [
            {
                "finding_id": f.finding_id,
                "title": f.title,
                "status": f.status.value,
                "reason": "rejected by red-team" if f.status.value == "rejected" else "INSUFFICIENT EVIDENCE (not verified)",
            }
            for f in findings
            if f.status.value != "verified" and f.severity.value != "info"
        ]
        duplicates = {fid for c in correlations if c.relationship_type.value == "duplicate" for fid in c.finding_ids[1:]}
        ctx.tick("score findings")
        scores = []
        for f in verified:
            if f.finding_id in duplicates:
                excluded.append(
                    {"finding_id": f.finding_id, "title": f.title, "status": "verified", "reason": "duplicate of another verified finding"}
                )
                continue
            mult, via = 1.0, None
            for c in correlations:
                if c.relationship_type.value in _MULTIPLYING and f.finding_id in c.finding_ids and c.risk_multiplier > mult:
                    mult, via = c.risk_multiplier, c
            risk = self._score(ctx, f, mult, via.title if via else None)
            scores.append(risk.score)
        ctx.tick("score compound risks")
        for c in correlations:
            if c.relationship_type.value not in ("compound_risk", "causal"):
                continue
            members = [by_id[i] for i in c.finding_ids if i in by_id and by_id[i].status.value == "verified"]
            if len(members) < 2:
                continue
            top = max(members, key=lambda m: _SEV_RANK.get(m.severity.value, 0))
            impact = max(impact_for(m.model_dump(mode="json"))[0] for m in members)
            expl = max(exploitability_for(m.model_dump(mode="json"))[0] for m in members)
            calc = compute_risk(top.severity.value, c.confidence, impact, expl, c.risk_multiplier)
            rationale = (
                f"{calc['priority']} compound risk: most severe verified member is {top.severity.value} ({top.title}); "
                f"correlation confidence {c.confidence:.2f}; max member impact {impact:.2f}; max exploitability {expl:.2f}; "
                f"multiplier {c.risk_multiplier:.2f} because {len({m.category.value for m in members})} independently verified dimensions "
                f"({', '.join(sorted({m.category.value for m in members}))}) reinforce each other. "
                f"raw {calc['raw']:.3f} -> score {calc['score']}."
            )
            risk = ctx.store.add_risk(
                ctx.investigation_id,
                correlation_id=c.correlation_id,
                kind="compound",
                title=c.title,
                category="compound",
                severity=top.severity.value,
                score=calc["score"],
                priority=calc["priority"],
                confidence=c.confidence,
                impact=impact,
                exploitability=expl,
                correlation_multiplier=c.risk_multiplier,
                factors=calc,
                member_finding_ids=[m.finding_id for m in members],
                rationale=rationale,
            )
            scores.append(risk.score)
            ctx.emit(
                EventType.RISK_ASSESSED,
                f"{risk.priority} (score {risk.score}) compound: {c.title}",
                receiver="recommendation_agent",
                payload={"risk_id": risk.risk_id, "priority": risk.priority, "score": risk.score, "correlation_id": c.correlation_id},
            )
        overall = overall_risk(scores)
        ctx.store.update_investigation(ctx.investigation_id, overall_risk_score=overall["score"], overall_risk_level=overall["level"])
        ctx.message(
            "orchestrator",
            f"Risk assessment: {len(scores)} verified risk(s); overall {overall['score']} ({overall['level']}); {len(excluded)} finding(s) excluded",
            payload={"overall": overall, "excluded": excluded},
        )
        ctx.coverage["excluded"] = excluded
        ctx.coverage["overall"] = overall
        return AgentOutcome(summary=f"{len(scores)} risks scored; overall {overall['score']} ({overall['level']})", coverage=ctx.coverage)

    def _score(self, ctx: AgentContext, f: FindingOut, mult: float, via: str | None):
        data = f.model_dump(mode="json")
        impact, impact_reason = impact_for(data)
        expl, expl_reason = exploitability_for(data)
        calc = compute_risk(f.severity.value, f.confidence, impact, expl, mult)
        rationale = (
            f"{calc['priority']} because: severity {f.severity.value} ({calc['severity_weight']}) x confidence {f.confidence:.2f} "
            f"x impact {impact:.2f} ({impact_reason}) x exploitability {expl:.2f} ({expl_reason}) x correlation {mult:.2f}"
            + (f" (part of '{via}')" if via else "")
            + f" = raw {calc['raw']:.3f} -> score {calc['score']}."
        )
        risk = ctx.store.add_risk(
            ctx.investigation_id,
            finding_id=f.finding_id,
            kind="finding",
            title=f.title,
            category=f.category.value,
            severity=f.severity.value,
            score=calc["score"],
            priority=calc["priority"],
            confidence=f.confidence,
            impact=impact,
            exploitability=expl,
            correlation_multiplier=mult,
            factors={**calc, "impact_reason": impact_reason, "exploitability_reason": expl_reason},
            member_finding_ids=[f.finding_id],
            rationale=rationale,
        )
        ctx.emit(
            EventType.RISK_ASSESSED,
            f"{risk.priority} (score {risk.score}): {f.title}",
            receiver="recommendation_agent",
            payload={"risk_id": risk.risk_id, "finding_id": f.finding_id, "priority": risk.priority, "score": risk.score},
        )
        return risk
