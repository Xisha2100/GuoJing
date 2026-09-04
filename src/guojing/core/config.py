"""Typed configuration for the visual guidance agent backend."""

from enum import StrEnum

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Validated, immutable settings loaded once during application startup."""

    model_config = SettingsConfigDict(
        env_prefix="GUOJING_",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
        str_strip_whitespace=True,
    )

    app_name: str = Field(default="老牌子视觉指引 Agent API", min_length=1)
    environment: AppEnvironment = AppEnvironment.LOCAL
    debug: bool = False
    database_url: str = Field(default="sqlite:///./data/guojing.db", min_length=1)

    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_vision_model: str = "deepseek-v4-flash-vision-exp"
    deepseek_model_timeout_seconds: int = Field(default=30, ge=1, le=120)

    agent_run_timeout_seconds: int = Field(default=90, ge=10, le=300)
    agent_max_concurrency: int = Field(default=4, ge=1, le=16)
    agent_queue_capacity: int = Field(default=20, ge=1, le=100)
    agent_confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    agent_session_ttl_hours: int = Field(default=24, ge=1, le=168)

    sandbox_docker_host: str | None = None
    sandbox_image: str = "python:3.12-slim"
    sandbox_idle_ttl_seconds: int = Field(default=600, ge=60, le=3600)

    @model_validator(mode="after")
    def require_model_key_for_deployed_environments(self) -> "Settings":
        if self.environment in {AppEnvironment.STAGING, AppEnvironment.PRODUCTION}:
            if self.deepseek_api_key is None:
                raise ValueError("deepseek_api_key is required outside local and test")
        return self
