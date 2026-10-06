from app.config import Settings
from app.llm.base import LLMBudgetExceeded, LLMDecision, LLMProvider, LLMRequest
from app.llm.mock_provider import MockLLMProvider
from app.llm.openai_provider import OpenAICompatibleProvider, OpenAIProvider


def create_provider(settings: Settings) -> LLMProvider:
    """Model selection by configuration. Mock mode never touches the network."""
    if settings.is_mock:
        return MockLLMProvider(max_calls=settings.llm_max_calls_per_investigation)
    common = {
        "api_key": settings.openai_api_key.get_secret_value() if settings.openai_api_key else None,
        "model_fast": settings.llm_model_fast,
        "model_reasoning": settings.llm_model_reasoning,
        "max_output_tokens": settings.llm_max_output_tokens,
        "max_input_chars": settings.llm_max_input_chars,
        "max_retries": settings.llm_max_retries,
        "timeout": settings.llm_timeout_seconds,
        "max_calls": settings.llm_max_calls_per_investigation,
    }
    if settings.llm_provider == "openai":
        return OpenAIProvider(**common)
    return OpenAICompatibleProvider(base_url=settings.llm_base_url, **common)


__all__ = [
    "LLMBudgetExceeded",
    "LLMDecision",
    "LLMProvider",
    "LLMRequest",
    "MockLLMProvider",
    "OpenAICompatibleProvider",
    "OpenAIProvider",
    "create_provider",
]
