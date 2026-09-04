import asyncio
import base64
import io
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from deepagents.backends.protocol import SandboxBackendProtocol
from fastapi.testclient import TestClient
from PIL import Image

from guojing.application.agent.coordinator import AgentRunCoordinator
from guojing.application.agent.service import AgentService
from guojing.core.config import AppEnvironment, Settings
from guojing.domain.agent_guidance import (
    AgentSession,
    GuidanceDecision,
    GuidanceStatus,
    GuidanceStep,
    NormalizedTarget,
)
from guojing.infrastructure.persistence.agent_repository import SqlAlchemyAgentRepository
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import Base
from guojing.main import create_app


class FakeAgent:
    async def analyze(
        self,
        *,
        session: AgentSession,
        history: Sequence[GuidanceStep],
        screenshot: bytes,
        image_media_type: str,
        sandbox: SandboxBackendProtocol,
    ) -> GuidanceDecision:
        del session, history, sandbox
        assert screenshot.startswith(b"\x89PNG")
        assert image_media_type == "image/png"
        return GuidanceDecision(
            status=GuidanceStatus.CONTINUE,
            instruction="点击中间的蓝色按钮",
            target=NormalizedTarget(left=0.2, top=0.3, right=0.8, bottom=0.6),
            confidence=0.95,
        )


class SequencedAgent:
    def __init__(self) -> None:
        self.history_lengths: list[int] = []

    async def analyze(
        self,
        *,
        session: AgentSession,
        history: Sequence[GuidanceStep],
        screenshot: bytes,
        image_media_type: str,
        sandbox: SandboxBackendProtocol,
    ) -> GuidanceDecision:
        del session, screenshot, image_media_type, sandbox
        self.history_lengths.append(len(history))
        if len(history) == 2:
            return GuidanceDecision(
                status=GuidanceStatus.COMPLETED,
                instruction="目标已经完成",
                target=None,
                confidence=0.98,
            )
        return GuidanceDecision(
            status=GuidanceStatus.CONTINUE,
            instruction=f"执行第 {len(history) + 1} 步",
            target=NormalizedTarget(left=0.2, top=0.3, right=0.8, bottom=0.6),
            confidence=0.95,
        )


class SlowAgent:
    async def analyze(
        self,
        *,
        session: AgentSession,
        history: Sequence[GuidanceStep],
        screenshot: bytes,
        image_media_type: str,
        sandbox: SandboxBackendProtocol,
    ) -> GuidanceDecision:
        del session, history, screenshot, image_media_type, sandbox
        await asyncio.sleep(60)
        raise AssertionError("cancelled agent must not return")


class FakeSandbox:
    id = "fake-sandbox"

    def delete(self, _path: str) -> None:
        return None


class FakeSandboxRegistry:
    def __init__(self) -> None:
        self.backend = cast(SandboxBackendProtocol, FakeSandbox())

    async def acquire(self, _session_id: object) -> SandboxBackendProtocol:
        return self.backend

    async def destroy(self, _session_id: object) -> None:
        return None

    async def cleanup_idle(self) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest.fixture
def agent_client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        environment=AppEnvironment.TEST,
        database_url=f"sqlite:///{tmp_path / 'agent.db'}",
    )
    database = Database(settings.database_url)
    Base.metadata.create_all(database.engine)
    service = AgentService(SqlAlchemyAgentRepository(database))
    registry = FakeSandboxRegistry()
    coordinator = AgentRunCoordinator(
        service,
        FakeAgent(),
        registry,
        maximum_concurrency=1,
        queue_capacity=2,
    )
    with TestClient(
        create_app(
            settings,
            agent_service=service,
            visual_agent=FakeAgent(),
            sandbox_registry=registry,
            agent_coordinator=coordinator,
        )
    ) as client:
        yield client
    database.dispose()


def test_session_run_and_sse_return_only_final_contract(agent_client: TestClient) -> None:
    session_response = agent_client.post(
        "/api/v1/agent/sessions",
        json={
            "schema_version": "1.0",
            "client_session_id": str(uuid4()),
            "goal": "找到蓝色按钮",
            "target_package": "com.example.target",
        },
    )
    assert session_response.status_code == 201
    session = session_response.json()
    headers = {"X-Agent-Session-Token": session["access_token"]}
    image = _png_base64(8, 12)

    accepted = agent_client.post(
        f"/api/v1/agent/sessions/{session['session_id']}/runs",
        headers=headers,
        json={
            "schema_version": "1.0",
            "client_turn_id": str(uuid4()),
            "image_media_type": "image/png",
            "screen_width": 8,
            "screen_height": 12,
            "screenshot_base64": image,
        },
    )
    assert accepted.status_code == 202
    run_id = accepted.json()["run_id"]

    result = _wait_for_terminal(agent_client, run_id, headers)
    assert result["status"] == "completed"
    decision = cast(dict[str, object], result["result"])
    assert decision["instruction"] == "点击中间的蓝色按钮"
    assert "screenshot_base64" not in result

    events = agent_client.get(f"/api/v1/agent/runs/{run_id}/events", headers=headers)
    assert events.status_code == 200
    assert "event: completed" in events.text
    assert image not in events.text


def test_run_rejects_mismatched_dimensions(agent_client: TestClient) -> None:
    session = agent_client.post(
        "/api/v1/agent/sessions",
        json={
            "schema_version": "1.0",
            "client_session_id": str(uuid4()),
            "goal": "打开设置",
            "target_package": "com.android.settings",
        },
    ).json()
    response = agent_client.post(
        f"/api/v1/agent/sessions/{session['session_id']}/runs",
        headers={"X-Agent-Session-Token": session["access_token"]},
        json={
            "schema_version": "1.0",
            "client_turn_id": str(uuid4()),
            "image_media_type": "image/png",
            "screen_width": 9,
            "screen_height": 12,
            "screenshot_base64": _png_base64(8, 12),
        },
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "screen dimensions do not match image"}


def test_same_turn_is_idempotent_and_changed_payload_is_rejected(
    agent_client: TestClient,
) -> None:
    session = agent_client.post(
        "/api/v1/agent/sessions",
        json={
            "schema_version": "1.0",
            "client_session_id": str(uuid4()),
            "goal": "打开设置",
            "target_package": "com.android.settings",
        },
    ).json()
    headers = {"X-Agent-Session-Token": session["access_token"]}
    turn_id = str(uuid4())
    request = {
        "schema_version": "1.0",
        "client_turn_id": turn_id,
        "image_media_type": "image/png",
        "screen_width": 8,
        "screen_height": 12,
        "screenshot_base64": _png_base64(8, 12),
    }

    first = agent_client.post(
        f"/api/v1/agent/sessions/{session['session_id']}/runs",
        headers=headers,
        json=request,
    )
    repeated = agent_client.post(
        f"/api/v1/agent/sessions/{session['session_id']}/runs",
        headers=headers,
        json=request,
    )
    changed = agent_client.post(
        f"/api/v1/agent/sessions/{session['session_id']}/runs",
        headers=headers,
        json={**request, "screenshot_base64": _png_base64(8, 12, color=(80, 20, 40))},
    )

    assert repeated.status_code == 202
    assert repeated.json()["run_id"] == first.json()["run_id"]
    assert changed.status_code == 409
    assert changed.json() == {"detail": "client_turn_id payload does not match"}


def test_invalid_token_does_not_disclose_session(agent_client: TestClient) -> None:
    session = agent_client.post(
        "/api/v1/agent/sessions",
        json={
            "schema_version": "1.0",
            "client_session_id": str(uuid4()),
            "goal": "打开设置",
            "target_package": "com.android.settings",
        },
    ).json()
    response = agent_client.post(
        f"/api/v1/agent/sessions/{session['session_id']}/runs",
        headers={"X-Agent-Session-Token": "invalid"},
        json={
            "schema_version": "1.0",
            "client_turn_id": str(uuid4()),
            "image_media_type": "image/png",
            "screen_width": 8,
            "screen_height": 12,
            "screenshot_base64": _png_base64(8, 12),
        },
    )
    assert response.status_code == 404


def test_three_turn_session_rebuilds_text_history_and_completes(tmp_path: Path) -> None:
    settings = Settings(
        environment=AppEnvironment.TEST,
        database_url=f"sqlite:///{tmp_path / 'three-turn.db'}",
    )
    database = Database(settings.database_url)
    Base.metadata.create_all(database.engine)
    service = AgentService(SqlAlchemyAgentRepository(database))
    registry = FakeSandboxRegistry()
    agent = SequencedAgent()
    coordinator = AgentRunCoordinator(
        service,
        agent,
        registry,
        maximum_concurrency=1,
        queue_capacity=1,
    )
    try:
        with TestClient(
            create_app(
                settings,
                agent_service=service,
                visual_agent=agent,
                sandbox_registry=registry,
                agent_coordinator=coordinator,
            )
        ) as client:
            session = client.post(
                "/api/v1/agent/sessions",
                json={
                    "schema_version": "1.0",
                    "client_session_id": str(uuid4()),
                    "goal": "完成三步操作",
                    "target_package": "com.example.target",
                },
            ).json()
            headers = {"X-Agent-Session-Token": session["access_token"]}
            statuses = []
            for _index in range(3):
                accepted = client.post(
                    f"/api/v1/agent/sessions/{session['session_id']}/runs",
                    headers=headers,
                    json={
                        "schema_version": "1.0",
                        "client_turn_id": str(uuid4()),
                        "image_media_type": "image/png",
                        "screen_width": 8,
                        "screen_height": 12,
                        "screenshot_base64": _png_base64(8, 12),
                    },
                )
                result = _wait_for_terminal(client, accepted.json()["run_id"], headers)
                decision = cast(dict[str, object], result["result"])
                statuses.append(decision["status"])

            blocked = client.post(
                f"/api/v1/agent/sessions/{session['session_id']}/runs",
                headers=headers,
                json={
                    "schema_version": "1.0",
                    "client_turn_id": str(uuid4()),
                    "image_media_type": "image/png",
                    "screen_width": 8,
                    "screen_height": 12,
                    "screenshot_base64": _png_base64(8, 12),
                },
            )
    finally:
        database.dispose()

    assert statuses == ["continue", "continue", "completed"]
    assert agent.history_lengths == [0, 1, 2]
    assert blocked.status_code == 409


def test_run_can_be_cancelled_without_exposing_agent_state(tmp_path: Path) -> None:
    settings = Settings(
        environment=AppEnvironment.TEST,
        database_url=f"sqlite:///{tmp_path / 'cancel.db'}",
    )
    database = Database(settings.database_url)
    Base.metadata.create_all(database.engine)
    service = AgentService(SqlAlchemyAgentRepository(database))
    registry = FakeSandboxRegistry()
    agent = SlowAgent()
    coordinator = AgentRunCoordinator(
        service,
        agent,
        registry,
        maximum_concurrency=1,
        queue_capacity=1,
    )
    try:
        with TestClient(
            create_app(
                settings,
                agent_service=service,
                visual_agent=agent,
                sandbox_registry=registry,
                agent_coordinator=coordinator,
            )
        ) as client:
            session = client.post(
                "/api/v1/agent/sessions",
                json={
                    "schema_version": "1.0",
                    "client_session_id": str(uuid4()),
                    "goal": "打开设置",
                    "target_package": "com.android.settings",
                },
            ).json()
            headers = {"X-Agent-Session-Token": session["access_token"]}
            accepted = client.post(
                f"/api/v1/agent/sessions/{session['session_id']}/runs",
                headers=headers,
                json={
                    "schema_version": "1.0",
                    "client_turn_id": str(uuid4()),
                    "image_media_type": "image/png",
                    "screen_width": 8,
                    "screen_height": 12,
                    "screenshot_base64": _png_base64(8, 12),
                },
            ).json()
            _wait_for_status(client, accepted["run_id"], headers, "running")
            queued = client.post(
                f"/api/v1/agent/sessions/{session['session_id']}/runs",
                headers=headers,
                json={
                    "schema_version": "1.0",
                    "client_turn_id": str(uuid4()),
                    "image_media_type": "image/png",
                    "screen_width": 8,
                    "screen_height": 12,
                    "screenshot_base64": _png_base64(8, 12),
                },
            )
            overflow = client.post(
                f"/api/v1/agent/sessions/{session['session_id']}/runs",
                headers=headers,
                json={
                    "schema_version": "1.0",
                    "client_turn_id": str(uuid4()),
                    "image_media_type": "image/png",
                    "screen_width": 8,
                    "screen_height": 12,
                    "screenshot_base64": _png_base64(8, 12),
                },
            )
            cancelled = client.delete(
                f"/api/v1/agent/runs/{accepted['run_id']}",
                headers=headers,
            )
            result = client.get(
                f"/api/v1/agent/runs/{accepted['run_id']}",
                headers=headers,
            ).json()
            closed = client.delete(
                f"/api/v1/agent/sessions/{session['session_id']}",
                headers=headers,
            )
    finally:
        database.dispose()

    assert cancelled.status_code == 204
    assert queued.status_code == 202
    assert overflow.status_code == 429
    assert overflow.json() == {"detail": "agent run queue is full"}
    assert result["status"] == "cancelled"
    assert result["result"] is None
    assert closed.status_code == 204


def _png_base64(
    width: int,
    height: int,
    *,
    color: tuple[int, int, int] = (20, 40, 80),
) -> str:
    output = io.BytesIO()
    Image.new("RGB", (width, height), color=color).save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def _wait_for_terminal(
    client: TestClient,
    run_id: str,
    headers: dict[str, str],
) -> dict[str, object]:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        payload = client.get(f"/api/v1/agent/runs/{run_id}", headers=headers).json()
        if payload["status"] in {"completed", "failed", "cancelled"}:
            return cast(dict[str, object], payload)
        time.sleep(0.01)
    raise AssertionError("agent run did not finish")


def _wait_for_status(
    client: TestClient,
    run_id: str,
    headers: dict[str, str],
    expected: str,
) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        payload = client.get(f"/api/v1/agent/runs/{run_id}", headers=headers).json()
        if payload["status"] == expected:
            return
        time.sleep(0.01)
    raise AssertionError(f"agent run did not reach {expected}")
