"""Typed application configuration loaded from the process environment."""

from enum import StrEnum

from pydantic import Field, model_validator
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
    admin_cookie_secure: bool = False
    admin_session_ttl_minutes: int = Field(default=480, ge=15, le=1440)
    admin_login_window_minutes: int = Field(default=15, ge=1, le=60)
    admin_maximum_login_failures: int = Field(default=5, ge=1, le=20)
    help_request_evidence_max_age_minutes: int = Field(default=15, ge=1, le=60)
    help_request_evidence_ttl_minutes: int = Field(default=10, ge=1, le=30)
    help_request_evidence_future_skew_seconds: int = Field(default=30, ge=0, le=300)
    help_request_evidence_max_per_request: int = Field(default=8, ge=1, le=64)

    @model_validator(mode="after")
    def require_secure_admin_cookie_outside_local_environments(self) -> "Settings":
        if self.environment in {AppEnvironment.STAGING, AppEnvironment.PRODUCTION}:
            if not self.admin_cookie_secure:
                raise ValueError("admin_cookie_secure must be true in staging and production")
        return self
