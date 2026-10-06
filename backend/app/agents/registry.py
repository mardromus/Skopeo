"""Agent registry — the only place agent names map to implementations."""

from __future__ import annotations

from app.agents.api_compatibility import ApiCompatibilityAgent
from app.agents.base import Agent, SpecialistAgent
from app.agents.code_quality import CodeQualityAgent
from app.agents.dependencies import DependencyAgent
from app.agents.license import LicenseAgent
from app.agents.maintenance import MaintenanceAgent
from app.agents.performance import PerformanceAgent
from app.agents.security import SecurityAgent
from app.agents.test_reliability import TestReliabilityAgent

SPECIALIST_CLASSES: dict[str, type[SpecialistAgent]] = {
    cls.name: cls
    for cls in (
        SecurityAgent,
        DependencyAgent,
        CodeQualityAgent,
        ApiCompatibilityAgent,
        TestReliabilityAgent,
        LicenseAgent,
        MaintenanceAgent,
        PerformanceAgent,
    )
}


def create_specialist(name: str) -> SpecialistAgent:
    try:
        return SPECIALIST_CLASSES[name]()
    except KeyError as exc:
        raise ValueError(f"unknown specialist agent: {name}") from exc


def all_agent_descriptions() -> list[dict[str, str]]:
    from app.agents.correlation import CorrelationAgent
    from app.agents.orchestrator import OrchestratorAgent
    from app.agents.recommendation import RecommendationAgent
    from app.agents.risk import RiskAgent
    from app.agents.verification import VerificationAgent

    classes: list[type[Agent]] = [
        OrchestratorAgent,
        *SPECIALIST_CLASSES.values(),
        CorrelationAgent,
        VerificationAgent,
        RiskAgent,
        RecommendationAgent,
    ]
    return [{"name": c.name, "display_name": c.display_name, "description": c.description, "modes": ", ".join(c.modes)} for c in classes]
