"""Behavior tests for typed agent configuration."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from guojing.core.config import AppEnvironment, Settings


def test_settings_have_safe_local_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GUOJING_DEEPSEEK_API_KEY", raising=False)
    settings = Settings(_env_file=None)

    assert settings.app_name == "老牌子视觉指引 Agent API"
    assert settings.environment is AppEnvironment.LOCAL
    assert settings.deepseek_vision_model == "deepseek-v4-flash-vision-exp"
    assert settings.agent_max_concurrency == 4
    assert settings.agent_confidence_threshold == 0.70
    assert settings.sandbox_image == "python:3.12-slim"


def test_settings_read_agent_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUOJING_ENVIRONMENT", "test")
    monkeypatch.setenv("GUOJING_AGENT_MAX_CONCURRENCY", "2")
    monkeypatch.setenv("GUOJING_AGENT_CONFIDENCE_THRESHOLD", "0.8")
    monkeypatch.setenv("GUOJING_SANDBOX_IDLE_TTL_SECONDS", "300")
    settings = Settings(_env_file=None)

    assert settings.environment is AppEnvironment.TEST
    assert settings.agent_max_concurrency == 2
    assert settings.agent_confidence_threshold == 0.8
    assert settings.sandbox_idle_ttl_seconds == 300


def test_settings_reject_unknown_environment() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="qa", _env_file=None)


def test_settings_require_deepseek_key_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(environment=AppEnvironment.PRODUCTION, _env_file=None)


def test_settings_load_local_file_but_environment_wins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GUOJING_DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("GUOJING_AGENT_MAX_CONCURRENCY", "3")
    (tmp_path / ".env.local").write_text(
        "GUOJING_DEEPSEEK_API_KEY=sk-from-local-file\nGUOJING_AGENT_MAX_CONCURRENCY=2\n",
        encoding="utf-8",
    )

    settings = Settings()

    assert settings.deepseek_api_key is not None
    assert settings.deepseek_api_key.get_secret_value() == "sk-from-local-file"
    assert settings.agent_max_concurrency == 3
