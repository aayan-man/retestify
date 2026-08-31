from app.config import settings

from .anthropic_provider import AnthropicProvider
from .base import LLMProvider
from .errors import ProviderNotConfiguredError
from .openai_provider import OpenAIProvider

_MISSING_KEY_HINT = {
    "anthropic": "Set APP_ANTHROPIC_API_KEY.",
    "openai": "Set APP_OPENAI_API_KEY (or APP_OPENAI_BASE_URL to point at a local model).",
}


def get_provider(name: str | None = None) -> LLMProvider:
    name = name or settings.ai_provider
    if name == "anthropic":
        return AnthropicProvider()
    if name == "openai":
        return OpenAIProvider()
    raise ValueError(f"unknown AI provider {name!r}")


def require_provider(name: str | None = None) -> LLMProvider:
    """Like get_provider, but fails fast with a clear, catchable error if
    the provider isn't configured — so a missing API key surfaces as one
    readable message instead of an exception raised deep inside the first
    LLM call the pipeline happens to make."""
    provider = get_provider(name)
    if not provider.is_available():
        hint = _MISSING_KEY_HINT.get(provider.name, "Check its required configuration.")
        raise ProviderNotConfiguredError(f"AI provider {provider.name!r} is not configured. {hint}")
    return provider
