from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel

from app.config import settings

from .base import LLMMessage, LLMProvider, LLMResponse


def _to_strict_schema(schema: dict) -> dict:
    """OpenAI/Groq strict `json_schema` response-format mode requires
    `additionalProperties: false` on every object node, which pydantic's
    `model_json_schema()` doesn't set by default — inject it recursively
    (including into $defs, for nested models)."""
    if schema.get("type") == "object":
        schema.setdefault("additionalProperties", False)
        for prop in schema.get("properties", {}).values():
            _to_strict_schema(prop)
    for definition in schema.get("$defs", {}).values():
        _to_strict_schema(definition)
    if "items" in schema:
        _to_strict_schema(schema["items"])
    return schema


class OpenAIProvider(LLMProvider):
    """Targets any OpenAI-compatible chat-completions endpoint. Setting
    `base_url` (e.g. to a local Ollama/vLLM/LM Studio server) plugs in a
    local model without a new provider class."""

    name = "openai"

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.base_url = base_url if base_url is not None else settings.openai_base_url
        self.model = model or settings.openai_model

    def is_available(self) -> bool:
        return bool(self.api_key) or bool(self.base_url)

    def _client(self):
        import openai  # optional dependency; only needed when this provider is used

        return openai.OpenAI(api_key=self.api_key or "not-needed", base_url=self.base_url)

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        response_schema: type[BaseModel] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse:
        client = self._client()
        start = time.monotonic()

        full_messages: list[dict[str, str]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend({"role": m["role"], "content": m["content"]} for m in messages)

        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=full_messages,
        )
        if response_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema.__name__,
                    "schema": _to_strict_schema(response_schema.model_json_schema()),
                    "strict": True,
                },
            }

        result = client.chat.completions.create(**kwargs)
        latency_ms = int((time.monotonic() - start) * 1000)

        choice = result.choices[0]
        text = choice.message.content or ""
        raw_json: dict | None = None
        if response_schema is not None:
            try:
                raw_json = json.loads(text)
            except json.JSONDecodeError:
                raw_json = None

        usage = result.usage
        return LLMResponse(
            text=text,
            raw_json=raw_json,
            model=result.model,
            provider=self.name,
            input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
            latency_ms=latency_ms,
            stop_reason=choice.finish_reason,
        )

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)
