from app.ai_engine.providers.anthropic_provider import AnthropicProvider
from app.ai_engine.providers.openai_provider import OpenAIProvider
from app.config import settings


def test_anthropic_provider_unavailable_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    provider = AnthropicProvider(api_key=None)
    assert provider.is_available() is False


def test_openai_provider_available_with_base_url_even_without_key():
    provider = OpenAIProvider(api_key=None, base_url="http://localhost:11434/v1")
    assert provider.is_available() is True


def test_openai_provider_unavailable_without_key_or_base_url(monkeypatch):
    # api_key=None/base_url=None on the constructor falls back to global
    # settings, so a locally-configured backend/.env (e.g. a real provider
    # key for manual testing) must not leak into this test's expectations.
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "openai_base_url", None)
    provider = OpenAIProvider(api_key=None, base_url=None)
    assert provider.is_available() is False
