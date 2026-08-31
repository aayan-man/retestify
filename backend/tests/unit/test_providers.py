from app.ai_engine.providers.anthropic_provider import AnthropicProvider
from app.ai_engine.providers.openai_provider import OpenAIProvider


def test_anthropic_provider_unavailable_without_api_key():
    provider = AnthropicProvider(api_key=None)
    assert provider.is_available() is False


def test_openai_provider_available_with_base_url_even_without_key():
    provider = OpenAIProvider(api_key=None, base_url="http://localhost:11434/v1")
    assert provider.is_available() is True


def test_openai_provider_unavailable_without_key_or_base_url():
    provider = OpenAIProvider(api_key=None, base_url=None)
    assert provider.is_available() is False
