"""Shared test fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from guojing.core.config import AppEnvironment, Settings
from guojing.main import create_app


@pytest.fixture
def test_settings() -> Settings:
    """Return deterministic settings that never depend on the developer shell."""
    return Settings(
        app_name="老牌子 Test API",
        environment=AppEnvironment.TEST,
        debug=True,
    )


@pytest.fixture
def client(test_settings: Settings) -> Iterator[TestClient]:
    """Exercise the API through the same ASGI boundary used in production."""
    with TestClient(create_app(test_settings)) as test_client:
        yield test_client
