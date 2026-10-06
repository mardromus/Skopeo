"""Application settings.

All configuration comes from environment variables (optionally a ``.env`` file).
Secrets are typed as ``SecretStr`` so they never appear in reprs or logs.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", str(_PROJECT_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Modes -----------------------------------------------------------------
    skopeo_mode: Literal["mock", "live"] = "mock"
    """mock: deterministic policies stand in for the LLM; live: real LLM provider."""

    skopeo_demo_mode: bool = True
    """Enables the bundled demo repository endpoint and the UI demo button."""

    skopeo_offline: bool = False
    """Never touch the network (advisories / registries / GitHub come from the offline snapshot)."""

    dry_run: bool = True
    """When true, approved GitHub actions are recorded but never executed."""

    # --- Storage -----------------------------------------------------------------
    database_url: str = f"sqlite:///{(_BACKEND_DIR / 'data' / 'skopeo.db').as_posix()}"
    skopeo_workspace_dir: Path = _BACKEND_DIR / "data" / "workspaces"
    skopeo_examples_dir: Path = _PROJECT_ROOT / "examples"
    skopeo_run_migrations: bool = True

    # --- LLM -------------------------------------------------------------------------
    llm_provider: Literal["mock", "openai", "openai_compatible"] = "mock"
    openai_api_key: SecretStr | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model_reasoning: str = "gpt-4o"
    llm_model_fast: str = "gpt-4o-mini"
    llm_max_output_tokens: int = 1200
    llm_max_input_chars: int = 24_000
    llm_max_retries: int = 2
    llm_timeout_seconds: float = 60.0
    llm_max_calls_per_investigation: int = 120

    # --- GitHub --------------------------------------------------------------------
    github_token: SecretStr | None = None
    github_api_url: str = "https://api.github.com"

    # --- Execution policy ---------------------------------------------------------
    skopeo_sandbox_execution: bool = False
    """Allow running tests/benchmarks of *untrusted* cloned repositories.
    Only enable inside an isolated container. The bundled demo fixture is always trusted."""

    skopeo_fault_injection: str = ""
    """Comma separated ``agent@attempt`` pairs that raise a controlled ToolUnavailableError."""

    skopeo_demo_fault_injection: str = "performance_agent@1"
    """Fault injection applied to demo investigations (controlled failure demonstration)."""

    skopeo_demo_step_delay_ms: int = 0
    """Presentation pacing for demo runs so humans can watch agents work (0 = full speed)."""

    # --- Budgets / loop limits ----------------------------------------------------
    agent_max_iterations: int = 40
    agent_max_tool_calls: int = 400
    agent_timeout_seconds: float = 180.0
    agent_max_retries: int = 1
    investigation_timeout_seconds: float = 1200.0
    max_orchestrator_rounds: int = 6
    max_correlation_rounds: int = 3
    max_verification_rounds: int = 2
    max_followups_per_round: int = 6
    max_findings_to_verify: int = 60

    # --- Repository / tool limits --------------------------------------------------
    clone_depth: int = 300
    clone_timeout_seconds: float = 180.0
    command_timeout_seconds: float = 120.0
    max_output_bytes: int = 200_000
    max_repo_files: int = 6000
    max_file_bytes: int = 400_000
    max_search_results: int = 400

    # --- HTTP API ---------------------------------------------------------------------
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8080"])
    max_concurrent_investigations: int = 2

    # --- Observability -----------------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip().startswith("["):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @property
    def is_mock(self) -> bool:
        return self.skopeo_mode == "mock" or self.llm_provider == "mock"

    def secret_values(self) -> list[str]:
        """Concrete secret values that must be redacted from every log line and output."""
        values = []
        for secret in (self.openai_api_key, self.github_token):
            if secret is not None and secret.get_secret_value():
                values.append(secret.get_secret_value())
        return values


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
