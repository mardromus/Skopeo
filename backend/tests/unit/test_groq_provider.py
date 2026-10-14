"""Groq provider: endpoint, auth, request body per model family, response parsing, key-aware live mode."""

from __future__ import annotations

import json

import httpx
from pydantic import BaseModel, SecretStr

from app.config import get_settings
from app.llm import GroqProvider, LLMRequest, MockLLMProvider, create_provider
from app.security.redaction import redact, register_secrets


class Verdict(BaseModel):
    decision: str
    reason: str


def _request(tier: str = "reasoning") -> LLMRequest:
    return LLMRequest(task_type="test", role_instructions="Judge.", task="Decide.", structured_input={"x": 1}, tier=tier)


def test_groq_request_and_response():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        content = json.dumps({"decision": "verified", "reason": "evidence holds"})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 120, "completion_tokens": 30}}
        )

    provider = GroqProvider(
        api_key="gsk_test_key",
        model_fast="openai/gpt-oss-20b",
        model_reasoning="openai/gpt-oss-120b",
        transport=httpx.MockTransport(handler),
    )
    decision = provider.decide(_request("reasoning"), Verdict, lambda: Verdict(decision="policy", reason="fallback"))
    assert decision.value.decision == "verified" and decision.decided_by == "llm:openai/gpt-oss-120b"
    assert decision.input_tokens == 120 and decision.output_tokens == 30

    req = seen[0]
    assert str(req.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert req.headers["Authorization"] == "Bearer gsk_test_key"
    body = json.loads(req.content)
    assert body["model"] == "openai/gpt-oss-120b" and body["response_format"] == {"type": "json_object"}
    assert body["reasoning_effort"] == "medium" and body["include_reasoning"] is False and "max_completion_tokens" in body
    assert "temperature" not in body and "max_tokens" not in body
    assert "JSON" in body["messages"][-1]["content"]  # Groq JSON mode needs explicit JSON instructions


def test_groq_body_per_model_family():
    provider = GroqProvider(api_key="k", model_fast="openai/gpt-oss-20b", model_reasoning="openai/gpt-oss-120b")
    fast = provider.build_body("openai/gpt-oss-20b", [], "fast", 2048)
    assert fast["reasoning_effort"] == "low" and fast["max_completion_tokens"] == 2048
    llama = provider.build_body("llama-3.3-70b-versatile", [], "fast", 2048)
    assert llama["temperature"] == 0 and "reasoning_effort" not in llama and "include_reasoning" not in llama


def test_groq_rate_limit_is_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": {"message": "rate limit"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"decision": "ok", "reason": "r"}'}}]})

    provider = GroqProvider(
        api_key="k", model_fast="openai/gpt-oss-20b", model_reasoning="openai/gpt-oss-120b", transport=httpx.MockTransport(handler)
    )
    assert provider.decide(_request(), Verdict, lambda: Verdict(decision="policy", reason="")).value.decision == "ok"
    assert calls["n"] == 2


def test_groq_failure_falls_back_to_policy():
    provider = GroqProvider(
        api_key="k",
        model_fast="openai/gpt-oss-20b",
        model_reasoning="openai/gpt-oss-120b",
        max_retries=0,
        transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"error": {"message": "invalid api key"}})),
    )
    decision = provider.decide(_request(), Verdict, lambda: Verdict(decision="policy", reason="fallback"))
    assert decision.decided_by == "policy-fallback" and decision.value.decision == "policy"


def test_live_mode_uses_groq_only_with_a_key():
    base = get_settings().model_copy(update={"skopeo_mode": "live", "llm_provider": "groq"})
    assert base.model_copy(update={"groq_api_key": None}).is_mock
    assert isinstance(create_provider(base.model_copy(update={"groq_api_key": SecretStr("  ")})), MockLLMProvider)
    live = base.model_copy(update={"groq_api_key": SecretStr("gsk_live")})
    provider = create_provider(live)
    assert isinstance(provider, GroqProvider) and not live.is_mock
    assert provider.model_reasoning == "openai/gpt-oss-120b" and provider.model_fast == "openai/gpt-oss-20b"
    assert provider.base_url == "https://api.groq.com/openai/v1"
    register_secrets(live.secret_values())
    assert "gsk_live" not in redact("key=gsk_live")
