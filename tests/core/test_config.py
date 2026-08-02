"""Behavior tests for typed process configuration."""

import pytest
from pydantic import ValidationError

from guojing.core.config import AppEnvironment, Settings

_SETTING_ENVIRONMENT_VARIABLES = (
    "GUOJING_APP_NAME",
    "GUOJING_ENVIRONMENT",
    "GUOJING_DEBUG",
    "GUOJING_DATABASE_URL",
    "GUOJING_ADMIN_API_TOKEN",
)


def test_settings_have_safe_local_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable_name in _SETTING_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable_name, raising=False)

    settings = Settings()

    assert settings.app_name == "老牌子 API"
    assert settings.environment is AppEnvironment.LOCAL
    assert settings.debug is False
    assert settings.database_url == "sqlite:///./data/guojing.db"
    assert settings.admin_api_token is None


def test_settings_read_prefixed_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUOJING_APP_NAME", "家庭测试 API")
    monkeypatch.setenv("GUOJING_ENVIRONMENT", "test")
    monkeypatch.setenv("GUOJING_DEBUG", "true")
    monkeypatch.setenv("GUOJING_DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.setenv(
        "GUOJING_ADMIN_API_TOKEN",
        "a-secret-test-token-that-is-long-enough",
    )

    settings = Settings()

    assert settings.app_name == "家庭测试 API"
    assert settings.environment is AppEnvironment.TEST
    assert settings.debug is True
    assert settings.database_url == "sqlite:///./data/test.db"
    assert settings.admin_api_token is not None
    assert "a-secret-test-token" not in repr(settings)


def test_settings_reject_unknown_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUOJING_ENVIRONMENT", "qa")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_reject_short_admin_token() -> None:
    with pytest.raises(ValidationError):
        Settings(admin_api_token="too-short")
