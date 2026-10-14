"""Application settings.

All configuration comes from environment variables (optionally a ``.env`` file).
Secrets are typed as ``SecretStr`` so they never appear in reprs or logs.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", str(_PROJECT_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,
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
    llm_provider: Literal["mock", "openai", "groq", "openai_compatible"] = "mock"
    openai_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    """Groq API key (console.groq.com/keys). Used when LLM_PROVIDER=groq."""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model_reasoning: str = "openai/gpt-oss-120b"
    """Groq model for planning, correlation and red-team judgement."""
    groq_model_fast: str = "openai/gpt-oss-20b"
    """Groq model for summaries, reviews and recommendation text."""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model_reasoning: str = "gpt-6.1-sol"
    llm_model_fast: str = "gpt-6-luna"
    llm_max_output_tokens: int = 4096
    """For reasoning models this budget also covers their hidden reasoning tokens."""
    llm_reasoning_effort: str = "medium"
    """reasoning_effort for the reasoning tier (planning, correlation, red team); reasoning models only."""
    llm_reasoning_effort_fast: str = "low"
    """reasoning_effort for the fast tier (summaries, reviews, recommendation text); reasoning models only."""
    llm_max_input_chars: int = 24_000
    llm_max_retries: int = 2
    llm_timeout_seconds: float = 60.0
    llm_max_calls_per_investigation: int = 120

    # --- GitHub --------------------------------------------------------------------
    github_token: SecretStr | None = None
    github_api_url: str = "https://api.github.com"

    # --- Execution policy ---------------------------------------------------------
    skopeo_sandbox_execution: bool = False
    # Whether people may switch sandbox execution ON for a single case from the UI. Off by default:
    # running a repository's own tests executes its code on this server.
    skopeo_allow_case_execution: bool = False
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

    # --- HTTP API / deployment -------------------------------------------------------------
    # Comma-separated in the environment (CORS_ORIGINS=https://a.example,https://b.example).
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8080"]
    )
    max_concurrent_investigations: int = 2
    skopeo_api_key: SecretStr | None = None
    """When set, starting, cancelling or approving anything requires this key (X-Skopeo-Key header)."""
    skopeo_demo_public: bool = True
    """With an API key set, still let anyone run the bundled reference case (it is offline and cheap)."""
    rate_limit_per_minute: int = 6
    """Maximum investigations a single client may start per minute (0 disables the limit)."""
    skopeo_static_dir: Path | None = None
    """Built frontend to serve from the API (single-container deploys). Defaults to frontend/dist when present."""
    skopeo_keep_workspaces: bool = True
    """Keep cloned repositories after an investigation finishes. Turn off in deployments to save disk."""

    # --- Accounts (Google sign-in through Firebase Authentication) ---------------------------
    # Leave FIREBASE_PROJECT_ID empty to run without accounts: everyone shares one local user.
    firebase_project_id: str = ""
    firebase_web_api_key: str = ""
    """Public web API key from the Firebase console (Project settings > Your apps). Not a secret."""
    firebase_auth_domain: str = ""
    """Usually <project-id>.firebaseapp.com."""
    firebase_app_id: str = ""
    firebase_sdk_version: str = "13.0.0"
    """Firebase JS SDK loaded by the browser from www.gstatic.com."""
    auth_require_login: bool = False
    """With Firebase configured: starting investigations requires signing in (the reference case stays public)."""
    auth_signed_in_users_can_scan: bool = True
    auth_github_enabled: bool = True
    """Offer "Sign in with GitHub" (enable the GitHub provider in Firebase Authentication first)."""
    github_private_repos: bool = False
    """Let users import private repositories: GitHub sign-in then asks for the broad `repo` scope."""
    skopeo_secret_key: SecretStr | None = None
    """Encrypts stored GitHub tokens. Unset: a random key is created next to the database on first start."""
    """With an access key set, a signed-in Google user may also start investigations without the key."""

    # --- Notifications ---------------------------------------------------------------------
    public_base_url: str = ""
    """Base URL used for links in notifications, e.g. https://skopeo.example.com."""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr | None = None
    smtp_from: str = ""
    """Sender address, e.g. "Skopeo <alerts@example.com>". Defaults to SMTP_USERNAME."""
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    notifications_dry_run: bool = False
    """Record deliveries without sending anything (useful in development)."""
    notification_timeout_seconds: float = 10.0
    notifications_allow_private_webhooks: bool = False
    """Allow generic webhooks to private / internal addresses (self-hosted setups only)."""

    # --- Projects and upstream watches ---------------------------------------------------------
    watch_scheduler_enabled: bool = True
    watch_scheduler_interval_seconds: int = 60
    watch_max_concurrent_checks: int = 1
    watch_clone_depth: int = 200
    project_max_files: int = 400
    project_max_total_bytes: int = 3_000_000

    # --- Observability -----------------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("database_url", mode="after")
    @classmethod
    def _postgres_driver(cls, value: str) -> str:
        """Hosted Postgres (Neon, Supabase, Render, Railway) hands out ``postgres://`` or
        ``postgresql://`` URLs; use the bundled psycopg 3 driver for both."""
        value = value.strip()
        # Tolerate what people paste from a provider dashboard: ``psql 'postgresql://…'``,
        # ``DATABASE_URL=…``, surrounding quotes, or a trailing newline.
        found = re.search(r"postgres(?:ql)?(?:\+\w+)?://[^\s'\"]+", value)
        if found:
            value = found.group(0)
        value = value.strip("'\" \t\r\n")
        if not value:  # an empty DATABASE_URL (e.g. a blank host variable) means the built-in SQLite file
            return f"sqlite:///{(_BACKEND_DIR / 'data' / 'skopeo.db').as_posix()}"
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                value = "postgresql+psycopg://" + value[len(prefix) :]
                break
        from sqlalchemy.engine import make_url

        try:
            make_url(value)
        except Exception as exc:  # noqa: BLE001 - never echo the value: it holds the password
            raise ValueError(
                "DATABASE_URL is not a valid database URL. Paste only the connection string, e.g. "
                "postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require (percent-encode special "
                "characters in the password), or leave it empty to use the built-in SQLite file."
            ) from exc
        return value

    @property
    def database_password(self) -> str | None:
        from sqlalchemy.engine import make_url

        try:
            return make_url(self.database_url).password
        except Exception:  # noqa: BLE001 - a malformed URL fails later, with a clearer error
            return None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip().startswith("["):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @property
    def is_mock(self) -> bool:
        """Deterministic policies instead of an LLM: mock mode, the mock provider, or a hosted provider without its key."""
        if self.skopeo_mode == "mock" or self.llm_provider == "mock":
            return True
        return self.llm_api_key is None and self.llm_provider in ("openai", "groq")

    @property
    def llm_api_key(self) -> str | None:
        secret = self.groq_api_key if self.llm_provider == "groq" else self.openai_api_key
        value = secret.get_secret_value().strip() if secret is not None else ""
        return value or None

    def secret_values(self) -> list[str]:
        """Concrete secret values that must be redacted from every log line and output."""
        values = []
        for secret in (
            self.openai_api_key,
            self.groq_api_key,
            self.github_token,
            self.skopeo_api_key,
            self.smtp_password,
            self.skopeo_secret_key,
        ):
            if secret is not None and secret.get_secret_value():
                values.append(secret.get_secret_value())
        if self.database_password:
            values.append(str(self.database_password))
        return values

    @property
    def auth_mode(self) -> Literal["firebase", "local"]:
        """firebase: Google sign-in; local: no accounts, a single built-in user owns everything."""
        return "firebase" if self.firebase_project_id.strip() else "local"

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host.strip() and (self.smtp_from.strip() or self.smtp_username.strip()))

    @property
    def static_dir(self) -> Path | None:
        """Directory with the built frontend, if one should be served."""
        candidate = self.skopeo_static_dir or (_PROJECT_ROOT / "frontend" / "dist")
        return candidate if (candidate / "index.html").is_file() else None


def effective_settings(settings: "Settings", options: dict | None) -> "Settings":
    """Server settings with one case's own choices applied (dry run, sandbox execution)."""
    options = options or {}
    update: dict = {}
    if isinstance(options.get("dry_run"), bool):
        update["dry_run"] = options["dry_run"]
    if isinstance(options.get("sandbox_execution"), bool):
        update["skopeo_sandbox_execution"] = options["sandbox_execution"]
    return settings.model_copy(update=update) if update else settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
