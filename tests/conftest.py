"""Shared test fixtures."""

import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from guojing.core.config import AppEnvironment, Settings
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import Base
from guojing.main import create_app


@pytest.fixture(autouse=True)
def isolate_external_services(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    if request.node.get_closest_marker("integration"):
        yield
        return
    for key in list(os.environ):
        if key.startswith("GUOJING_"):
            monkeypatch.delenv(key)
    if "test_config" not in request.node.nodeid:
        monkeypatch.setitem(Settings.model_config, "env_file", None)
    with (
        patch(
            "guojing.infrastructure.sandbox.docker_backend.docker.from_env",
            side_effect=AssertionError("offline Docker"),
        ),
        patch("httpx.HTTPTransport.handle_request", side_effect=AssertionError("offline network")),
        patch(
            "httpx.AsyncHTTPTransport.handle_async_request",
            side_effect=AssertionError("offline network"),
        ),
        patch(
            "guojing.infrastructure.sandbox.docker_backend.docker.DockerClient",
            side_effect=AssertionError("offline test accessed Docker"),
        ),
    ):
        yield


@pytest.fixture
def test_settings() -> Settings:
    """Return deterministic settings that never depend on the developer shell."""
    return Settings(
        app_name="老牌子 Test API",
        environment=AppEnvironment.TEST,
        debug=True,
        _env_file=None,
        deepseek_api_key=None,
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
        from tests.api.test_agent import FakeAgent, FakeSandboxRegistry

        with TestClient(
            create_app(settings, visual_agent=FakeAgent(), sandbox_registry=FakeSandboxRegistry())
        ) as test_client:
            yield test_client
    finally:
        schema_database.dispose()
