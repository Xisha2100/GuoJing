"""Typed application configuration loaded from the process environment."""

from enum import StrEnum

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    """Deployment environments with intentionally explicit semantics."""

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

    app_name: str = Field(default="老牌子 API", min_length=1)
    environment: AppEnvironment = AppEnvironment.LOCAL
    debug: bool = False
    database_url: str = Field(default="sqlite:///./data/guojing.db", min_length=1)
    admin_api_token: SecretStr | None = Field(default=None, min_length=32)
