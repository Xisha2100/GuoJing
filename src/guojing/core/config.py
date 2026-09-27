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
        env_file=".env.local",
        env_file_encoding="utf-8",
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
    deepseek_vision_model: str = "deepseek-flash"
    deepseek_model_timeout_seconds: int = Field(default=30, ge=1, le=120)

    agent_run_timeout_seconds: int = Field(default=90, ge=10, le=300)
    agent_max_concurrency: int = Field(default=2, ge=1, le=16)
    agent_queue_capacity: int = Field(default=8, ge=1, le=100)
    agent_confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    agent_session_ttl_hours: int = Field(default=24, ge=1, le=24)

    agent_queue_timeout_seconds: int = Field(default=30, ge=1, le=30)
    sandbox_cleanup_timeout_seconds: int = Field(default=5, ge=1, le=10)
    device_maximum: int = Field(default=10, ge=1, le=10)
    device_daily_limit: int = Field(default=50, ge=1)
    global_daily_limit: int = Field(default=300, ge=1)
    deployment_id: str = Field(default="local", pattern=r"^[a-z0-9-]{1,40}$")
    minimum_free_disk_bytes: int = Field(default=1024 * 1024 * 1024, ge=0)

    sandbox_docker_host: str | None = None
    sandbox_image: str = "python:3.12-slim"
    sandbox_idle_ttl_seconds: int = Field(default=600, ge=60, le=3600)

    @model_validator(mode="after")
    def require_model_key_for_deployed_environments(self) -> "Settings":
        if self.environment in {AppEnvironment.STAGING, AppEnvironment.PRODUCTION}:
            if self.agent_max_concurrency > 2 or self.agent_queue_capacity > 8:
                raise ValueError("pilot deployment supports at most 2 workers and 8 queued runs")
            if "@sha256:" not in self.sandbox_image:
                raise ValueError("deployed sandbox image must be pinned by digest")
            if self.debug:
                raise ValueError("debug must be disabled in deployed environments")
            if not self.database_url.startswith("sqlite:///") or ":memory:" in self.database_url:
                raise ValueError("the single-instance deployment requires file-backed SQLite")
            if not self.deepseek_base_url.startswith("https://"):
                raise ValueError("model endpoint must use HTTPS")
            if self.sandbox_docker_host and not self.sandbox_docker_host.startswith("unix://"):
                raise ValueError("deployed Docker must use a local Unix socket")
            if (
                self.deepseek_api_key is None
                or not self.deepseek_api_key.get_secret_value().strip()
            ):
                raise ValueError("deepseek_api_key is required outside local and test")
        return self
