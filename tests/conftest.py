"""Shared test fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from guojing.core.config import AppEnvironment, Settings
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import Base
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
def client(test_settings: Settings, tmp_path: Path) -> Iterator[TestClient]:
    """Exercise the API through the same ASGI boundary used in production."""
    settings = test_settings.model_copy(
        update={"database_url": f"sqlite:///{tmp_path / 'api.db'}"},
    )
    schema_database = Database(settings.database_url)
    Base.metadata.create_all(schema_database.engine)
    try:
        with TestClient(create_app(settings)) as test_client:
            yield test_client
    finally:
        schema_database.dispose()
