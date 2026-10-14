from app.config import Settings
from app.llm.base import LLMBudgetExceeded, LLMDecision, LLMProvider, LLMRequest
from app.llm.mock_provider import MockLLMProvider
from app.llm.openai_provider import GroqProvider, OpenAICompatibleProvider, OpenAIProvider, is_reasoning_model


def create_provider(settings: Settings) -> LLMProvider:
    """Model selection by configuration. Mock mode never touches the network."""
    if settings.is_mock:
        return MockLLMProvider(max_calls=settings.llm_max_calls_per_investigation)
    common = {
        "api_key": settings.llm_api_key,
        "model_fast": settings.llm_model_fast,
        "model_reasoning": settings.llm_model_reasoning,
        "max_output_tokens": settings.llm_max_output_tokens,
        "max_input_chars": settings.llm_max_input_chars,
        "max_retries": settings.llm_max_retries,
        "timeout": settings.llm_timeout_seconds,
        "max_calls": settings.llm_max_calls_per_investigation,
        "reasoning_effort": settings.llm_reasoning_effort,
        "reasoning_effort_fast": settings.llm_reasoning_effort_fast,
    }
    if settings.llm_provider == "openai":
        return OpenAIProvider(**common)
    if settings.llm_provider == "groq":
        common |= {"model_fast": settings.groq_model_fast, "model_reasoning": settings.groq_model_reasoning}
        return GroqProvider(base_url=settings.groq_base_url, **common)
    return OpenAICompatibleProvider(base_url=settings.llm_base_url, **common)


__all__ = [
    "GroqProvider",
    "LLMBudgetExceeded",
    "LLMDecision",
    "LLMProvider",
    "LLMRequest",
    "MockLLMProvider",
    "OpenAICompatibleProvider",
    "OpenAIProvider",
    "is_reasoning_model",
    "create_provider",
]
