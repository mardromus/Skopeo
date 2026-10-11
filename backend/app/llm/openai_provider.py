"""OpenAI and OpenAI-compatible chat-completions providers (plain httpx, JSON mode).

Reasoning models (``o1``/``o3``/``o4``, ``gpt-5*``, ``gpt-6*``) take ``max_completion_tokens``
(which also covers their hidden reasoning tokens) and ``reasoning_effort`` and reject a custom
``temperature``; older chat models and most OpenAI-compatible servers (Ollama, vLLM, LM Studio)
take ``temperature`` and ``max_tokens``. The body is built for whichever kind the model is.
"""

from __future__ import annotations

import json
import time

import httpx

from app.llm.base import LLMProvider, LLMRequest, T
from app.security.prompt_guard import build_messages

REASONING_MODEL_PREFIXES = ("o1", "o3", "o4", "gpt-5", "gpt-6")


def is_reasoning_model(model: str) -> bool:
    return model.rsplit("/", 1)[-1].lower().startswith(REASONING_MODEL_PREFIXES)


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model_fast: str,
        model_reasoning: str,
        max_output_tokens: int = 4096,
        max_input_chars: int = 24_000,
        max_retries: int = 2,
        timeout: float = 60.0,
        max_calls: int = 120,
        transport: httpx.BaseTransport | None = None,
        reasoning_effort: str | None = "medium",
        reasoning_effort_fast: str | None = "low",
    ) -> None:
        super().__init__(max_calls=max_calls)
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model_fast = model_fast
        self.model_reasoning = model_reasoning
        self.max_output_tokens = max_output_tokens
        self.max_input_chars = max_input_chars
        self.max_retries = max_retries
        self.timeout = timeout
        self._transport = transport
        self.reasoning_effort = reasoning_effort or None
        self.reasoning_effort_fast = reasoning_effort_fast or None

    def build_body(self, model: str, messages: list[dict[str, str]], tier: str, max_output_tokens: int) -> dict:
        body: dict = {"model": model, "messages": messages, "response_format": {"type": "json_object"}}
        if is_reasoning_model(model):
            body["max_completion_tokens"] = max_output_tokens
            effort = self.reasoning_effort if tier == "reasoning" else self.reasoning_effort_fast
            if effort:
                body["reasoning_effort"] = effort
        else:
            body["temperature"] = 0
            body["max_tokens"] = max_output_tokens
        return body

    def _complete(self, request: LLMRequest, schema: type[T]) -> tuple[T, int, int, str]:
        model = self.model_reasoning if request.tier == "reasoning" else self.model_fast
        messages = build_messages(
            role_instructions=request.role_instructions,
            task=request.task,
            structured_input=request.structured_input,
            untrusted=request.untrusted,
            output_schema=schema.model_json_schema(),
            max_chars=self.max_input_chars,
        )
        body = self.build_body(model, messages, request.tier, request.max_output_tokens or self.max_output_tokens)
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                    resp = client.post(f"{self.base_url}/chat/completions", json=body, headers=headers)
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(min(8.0, 0.5 * 2**attempt))
                    continue
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                if not content:  # a reasoning model can spend the whole budget thinking (finish_reason "length")
                    raise ValueError(f"empty completion (finish_reason={data['choices'][0].get('finish_reason')})")
                parsed = schema.model_validate(json.loads(content))
                usage = data.get("usage") or {}
                return parsed, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)), model
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(min(8.0, 0.5 * 2**attempt))
        raise RuntimeError(f"LLM request failed after {self.max_retries + 1} attempts: {type(last_error).__name__}")


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("base_url", "https://api.openai.com/v1")
        super().__init__(**kwargs)
