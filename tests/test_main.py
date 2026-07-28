"""Tests for application assembly."""

from guojing.core.config import Settings
from guojing.main import create_app


def test_create_app_uses_injected_settings(test_settings: Settings) -> None:
    application = create_app(test_settings)

    assert application.title == "老牌子 Test API"
    assert application.debug is True
    assert application.state.settings is test_settings
