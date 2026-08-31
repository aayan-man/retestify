class ProviderNotConfiguredError(RuntimeError):
    """Raised when the selected LLMProvider is missing required config
    (e.g. no API key) — callers can catch this to fail fast with an
    actionable message instead of the underlying HTTP client erroring deep
    inside a `complete()` call."""
