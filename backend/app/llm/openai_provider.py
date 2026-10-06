"""OpenAI and OpenAI-compatible chat-completions providers (plain httpx, JSON mode)."""

from __future__ import annotations

import json
import time

import httpx

from app.llm.base import LLMProvider, LLMRequest, T
from app.security.prompt_guard import build_messages


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model_fast: str,
        model_reasoning: str,
        max_output_tokens: int = 1200,
        max_input_chars: int = 24_000,
        max_retries: int = 2,
        timeout: float = 60.0,
        max_calls: int = 120,
        transport: httpx.BaseTransport | None = None,
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
        body = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": request.max_output_tokens or self.max_output_tokens,
            "response_format": {"type": "json_object"},
        }
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
