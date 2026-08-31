from app.config import settings

from .anthropic_provider import AnthropicProvider
from .base import LLMProvider
from .openai_provider import OpenAIProvider


def get_provider(name: str | None = None) -> LLMProvider:
    name = name or settings.ai_provider
    if name == "anthropic":
        return AnthropicProvider()
    if name == "openai":
        return OpenAIProvider()
    raise ValueError(f"unknown AI provider {name!r}")
