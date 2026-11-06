from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


def test_health_fixture_never_starts_real_docker(request: pytest.FixtureRequest) -> None:
    with patch(
        "guojing.infrastructure.sandbox.docker_backend.DockerSandboxRegistry.start"
    ) as start:
        client = request.getfixturevalue("client")
        assert client.get("/health").status_code == 200
        start.assert_not_called()


def test_session_creation_is_rate_limited(agent_client: TestClient) -> None:
    responses = [
        agent_client.post(
            "/api/v1/agent/sessions",
            json={
                "schema_version": "1.0",
                "client_session_id": str(uuid4()),
                "goal": "设置",
                "target_package": "test.app",
            },
        )
        for _ in range(7)
    ]
    assert [r.status_code for r in responses] == [201] * 6 + [429]
    assert responses[-1].headers["Retry-After"]


@pytest.mark.asyncio
async def test_sqlite_writer_wait_leaves_api_event_loop_responsive(tmp_path: Path) -> None:
    import asyncio

    import httpx
    from tests.api.test_agent import FakeAgent, FakeSandboxRegistry

    from guojing.core.config import AppEnvironment, Settings
    from guojing.infrastructure.persistence.database import Database
    from guojing.infrastructure.persistence.models import Base
    from guojing.main import create_app

    settings = Settings(
        environment=AppEnvironment.TEST, database_url=f"sqlite:///{tmp_path / 'locked.db'}"
    )
    database = Database(settings.database_url)
    Base.metadata.create_all(database.engine)
    app = create_app(settings, visual_agent=FakeAgent(), sandbox_registry=FakeSandboxRegistry())
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            access = app.state.device_access
            secret = "a" * 43
            device = access.activate(access.invite("lock regression"), uuid4(), secret)
            with database.engine.connect() as writer:
                writer.exec_driver_sql("BEGIN IMMEDIATE")
                pending = asyncio.create_task(
                    client.post(
                        "/api/v1/agent/sessions",
                        headers={"Authorization": f"Bearer {device.device_id}.{secret}"},
                        json={
                            "schema_version": "1.0",
                            "client_session_id": str(uuid4()),
                            "goal": "设置",
                            "target_package": "test.app",
                        },
                    )
                )
                try:
                    await asyncio.sleep(0.05)
                    assert not pending.done()
                    assert (await asyncio.wait_for(client.get("/health"), 0.5)).status_code == 200
                finally:
                    writer.rollback()
                    result = await pending
                assert result.status_code == 201
    finally:
        database.dispose()
