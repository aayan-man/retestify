from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    workspace_root: Path = Path(__file__).resolve().parent.parent / "workspace"

    ai_provider: str = "anthropic"
    # Applying a project makes one call per recommendation back to back,
    # which saturates tokens-per-minute limits on smaller tiers. Both SDKs
    # honor Retry-After and back off exponentially, so a higher ceiling than
    # their default of 2 absorbs rate limiting instead of failing the
    # recommendation.
    llm_max_retries: int = 5
    # Background workers for the API's long-running pipeline calls. Jobs are
    # already serialized per project, so this caps how many *different*
    # projects can be classified or applied at once.
    job_max_workers: int = 4
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"

    test_runner_docker_image_python: str = "python:3.11-slim"
    test_runner_docker_image_node: str = "node:20-slim"

    github_webhook_secret: str | None = None


settings = Settings()
settings.workspace_root.mkdir(parents=True, exist_ok=True)
