from __future__ import annotations

from app.ai_engine.providers.base import LLMMessage, LLMProvider, LLMResponse


class CostTrackingProvider(LLMProvider):
    """Wraps another provider and accumulates token/latency usage across
    calls, so the evaluation harness can report LLM cost per run without
    threading tracking through the product's ai_engine core — this stays
    in research/ deliberately, per the "keep the research harness separate
    from the product core" split."""

    def __init__(self, inner: LLMProvider):
        self._inner = inner
        self.name = inner.name
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_latency_ms = 0
        self.call_count = 0

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        response_schema=None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse:
        response = self._inner.complete(
            messages, system=system, response_schema=response_schema, max_tokens=max_tokens, temperature=temperature
        )
        self.total_input_tokens += response.input_tokens
        self.total_output_tokens += response.output_tokens
        self.total_latency_ms += response.latency_ms
        self.call_count += 1
        return response

    def count_tokens(self, text: str) -> int:
        return self._inner.count_tokens(text)

    def is_available(self) -> bool:
        return self._inner.is_available()
