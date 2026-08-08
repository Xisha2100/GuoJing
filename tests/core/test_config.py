"""Behavior tests for typed process configuration."""

import pytest
from pydantic import ValidationError

from guojing.core.config import AppEnvironment, Settings

_SETTING_ENVIRONMENT_VARIABLES = (
    "GUOJING_APP_NAME",
    "GUOJING_ENVIRONMENT",
    "GUOJING_DEBUG",
    "GUOJING_DATABASE_URL",
    "GUOJING_ADMIN_COOKIE_SECURE",
    "GUOJING_ADMIN_SESSION_TTL_MINUTES",
    "GUOJING_ADMIN_LOGIN_WINDOW_MINUTES",
    "GUOJING_ADMIN_MAXIMUM_LOGIN_FAILURES",
)


def test_settings_have_safe_local_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable_name in _SETTING_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable_name, raising=False)

    settings = Settings()

    assert settings.app_name == "老牌子 API"
    assert settings.environment is AppEnvironment.LOCAL
    assert settings.debug is False
    assert settings.database_url == "sqlite:///./data/guojing.db"
    assert settings.admin_cookie_secure is False
    assert settings.admin_session_ttl_minutes == 480
    assert settings.admin_login_window_minutes == 15
    assert settings.admin_maximum_login_failures == 5


def test_settings_read_prefixed_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUOJING_APP_NAME", "家庭测试 API")
    monkeypatch.setenv("GUOJING_ENVIRONMENT", "test")
    monkeypatch.setenv("GUOJING_DEBUG", "true")
    monkeypatch.setenv("GUOJING_DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.setenv("GUOJING_ADMIN_COOKIE_SECURE", "true")
    monkeypatch.setenv("GUOJING_ADMIN_SESSION_TTL_MINUTES", "60")
    monkeypatch.setenv("GUOJING_ADMIN_LOGIN_WINDOW_MINUTES", "10")
    monkeypatch.setenv("GUOJING_ADMIN_MAXIMUM_LOGIN_FAILURES", "3")

    settings = Settings()

    assert settings.app_name == "家庭测试 API"
    assert settings.environment is AppEnvironment.TEST
    assert settings.debug is True
    assert settings.database_url == "sqlite:///./data/test.db"
    assert settings.admin_cookie_secure is True
    assert settings.admin_session_ttl_minutes == 60
    assert settings.admin_login_window_minutes == 10
    assert settings.admin_maximum_login_failures == 3


def test_settings_reject_unknown_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUOJING_ENVIRONMENT", "qa")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_require_secure_admin_cookie_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(environment=AppEnvironment.PRODUCTION, admin_cookie_secure=False)
