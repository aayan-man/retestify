from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal, TypedDict

from pydantic import BaseModel


class LLMMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMResponse(BaseModel):
    text: str
    raw_json: dict | None = None
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    stop_reason: str | None = None


class LLMProvider(ABC):
    """A pluggable LLM backend. The AI Review Engine, the test generator, and
    the research evaluation harness's standalone-LLM baseline all depend on
    this interface rather than a concrete vendor SDK, so providers can be
    swapped via config without touching call sites."""

    name: str

    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        response_schema: type[BaseModel] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse: ...

    @abstractmethod
    def count_tokens(self, text: str) -> int: ...

    def is_available(self) -> bool:
        """Cheap health check (e.g. API key present) — no network call."""
        return True
