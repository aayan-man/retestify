from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel

from app.config import settings

from .base import LLMMessage, LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key if api_key is not None else settings.anthropic_api_key
        self.model = model or settings.anthropic_model

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _client(self):
        import anthropic  # optional dependency; only needed when this provider is used

        return anthropic.Anthropic(api_key=self.api_key)

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        response_schema: type[BaseModel] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")

        client = self._client()
        start = time.monotonic()

        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
        )
        if system:
            kwargs["system"] = system

        # Anthropic has no native JSON-mode; force structured output via a
        # single required tool call whose input_schema is the pydantic schema.
        if response_schema is not None:
            tool_name = "emit_result"
            kwargs["tools"] = [
                {
                    "name": tool_name,
                    "description": "Emit the structured result.",
                    "input_schema": response_schema.model_json_schema(),
                }
            ]
            kwargs["tool_choice"] = {"type": "tool", "name": tool_name}

        result = client.messages.create(**kwargs)
        latency_ms = int((time.monotonic() - start) * 1000)

        text_parts: list[str] = []
        raw_json: dict | None = None
        for block in result.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                raw_json = block.input

        usage = result.usage
        return LLMResponse(
            text="\n".join(text_parts),
            raw_json=raw_json,
            model=result.model,
            provider=self.name,
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            latency_ms=latency_ms,
            stop_reason=result.stop_reason,
        )

    def count_tokens(self, text: str) -> int:
        # Rough estimate; avoids a network call for a non-critical metric.
        return max(1, len(text) // 4)
