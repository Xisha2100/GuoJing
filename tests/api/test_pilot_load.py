import asyncio
import base64
import io
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from PIL import Image
from tests.api.test_agent import FakeSandboxRegistry

from guojing.application.agent.usage import current_usage
from guojing.core.config import AppEnvironment, Settings
from guojing.domain.agent_guidance import GuidanceDecision, GuidanceStatus
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import Base
from guojing.main import create_app


class MeteredAgent:
    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.calls = 0

    async def analyze(self, **kwargs: Any) -> GuidanceDecision:
        usage = current_usage.get()
        assert usage
        usage.begin_call()
        self.calls += 1
        await self.release.wait()
        return GuidanceDecision(GuidanceStatus.CANNOT_DETERMINE, "请重试", None, 0.5)


@pytest.mark.asyncio
async def test_ten_concurrent_devices_receive_bounded_results_and_service_recovers(
    tmp_path: Path,
) -> None:
    settings = Settings(
        environment=AppEnvironment.TEST,
        database_url=f"sqlite:///{tmp_path / 'load.db'}",
        agent_max_concurrency=2,
        agent_queue_capacity=8,
    )
    database = Database(settings.database_url)
    Base.metadata.create_all(database.engine)
    agent = MeteredAgent()
    app = create_app(settings, visual_agent=agent, sandbox_registry=FakeSandboxRegistry())
    image = io.BytesIO()
    Image.new("RGB", (8, 12)).save(image, format="PNG")
    payload = {
        "schema_version": "1.0",
        "image_media_type": "image/png",
        "screen_width": 8,
        "screen_height": 12,
        "screenshot_base64": base64.b64encode(image.getvalue()).decode(),
    }
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        sessions = []
        for index in range(10):
            access = app.state.device_access
            secret = "a" * 43
            device = access.activate(access.invite(str(index)), uuid4(), secret)
            headers = {"Authorization": f"Bearer {device.device_id}.{secret}"}
            response = await client.post(
                "/api/v1/agent/sessions",
                headers=headers,
                json={
                    "schema_version": "1.0",
                    "client_session_id": str(uuid4()),
                    "goal": "测试",
                    "target_package": "synthetic.app",
                },
            )
            assert response.status_code == 201
            session = response.json()
            headers["X-Agent-Session-Token"] = session["access_token"]
            sessions.append((f"/api/v1/agent/sessions/{session['session_id']}/runs", headers))
        try:
            responses = await asyncio.gather(
                *[
                    client.post(
                        url, headers=headers, json={**payload, "client_turn_id": str(uuid4())}
                    )
                    for url, headers in sessions
                ]
            )
            assert all(result.status_code in {202, 429, 503} for result in responses)
            for response in responses:
                if response.status_code != 202:
                    assert response.json()["detail"]["code"] == "service_busy"
            assert app.state.agent_coordinator.active_count <= 2
            assert app.state.agent_coordinator.queue_depth <= 8
            assert agent.calls <= 2
            agent.release.set()
            await asyncio.wait_for(app.state.agent_coordinator._queue.join(), 3)
            assert app.state.agent_coordinator.ready
            url, headers = sessions[-1]
            result = await client.post(
                url, headers=headers, json={**payload, "client_turn_id": str(uuid4())}
            )
            assert result.status_code == 202
            await asyncio.wait_for(app.state.agent_coordinator._queue.join(), 3)
        finally:
            agent.release.set()
    database.dispose()
