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
