import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from deepagents.backends.protocol import SandboxBackendProtocol

from guojing.application.agent.coordinator import AgentQueueFull, AgentRunCoordinator
from guojing.application.agent.service import AgentService
from guojing.domain.agent_guidance import (
    AgentRun,
    AgentSession,
    GuidanceDecision,
    GuidanceStatus,
    GuidanceStep,
)
from guojing.infrastructure.persistence.agent_repository import SqlAlchemyAgentRepository
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import Base


class FakeSandbox:
    id = "sandbox-id"

    def delete(self, _path: str) -> None:
        return None


class FakeRegistry:
    def __init__(self) -> None:
        self.backend = cast(SandboxBackendProtocol, FakeSandbox())

    async def acquire(self, _session_id: UUID) -> SandboxBackendProtocol:
        return self.backend

    async def destroy(self, _session_id: UUID) -> None:
        return None

    async def cleanup_idle(self) -> None:
        return None

    async def close(self) -> None:
        return None


class UnavailableRegistry(FakeRegistry):
    async def acquire(self, _session_id: UUID) -> SandboxBackendProtocol:
        raise RuntimeError("docker details must not escape")


class BlockingAgent:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0
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
        del session, image_media_type, sandbox
        assert screenshot == b"private-screen"
        self.calls += 1
        self.history_lengths.append(len(history))
        self.started.set()
        await self.release.wait()
        return GuidanceDecision(
            status=GuidanceStatus.CANNOT_DETERMINE,
            instruction="请重试",
            target=None,
            confidence=0.4,
        )


@pytest.mark.asyncio
async def test_queue_is_bounded_while_worker_is_busy(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'queue.db'}")
    Base.metadata.create_all(database.engine)
    service = AgentService(SqlAlchemyAgentRepository(database))
    session, _token = service.create_session(
        client_session_id=uuid4(),
        goal="打开设置",
        target_package="com.android.settings",
    )
    agent = BlockingAgent()
    coordinator = AgentRunCoordinator(
        service,
        agent,
        FakeRegistry(),
        maximum_concurrency=1,
        queue_capacity=1,
    )
    await coordinator.start()
    try:
        first = _new_run(service, session)
        second = _new_run(service, session)
        overflow = _new_run(service, session)
        await coordinator.submit(run=first, session=session, screenshot=b"private-screen")
        await asyncio.wait_for(agent.started.wait(), timeout=1)
        await coordinator.submit(run=second, session=session, screenshot=b"private-screen")

        with pytest.raises(AgentQueueFull):
            await coordinator.submit(
                run=overflow,
                session=session,
                screenshot=b"private-screen",
            )
        agent.release.set()
        await asyncio.wait_for(coordinator._queue.join(), timeout=1)
    finally:
        agent.release.set()
        await coordinator.stop()
        database.dispose()


def _new_run(service: AgentService, session: AgentSession) -> AgentRun:
    run, created = service.create_or_get_run(
        session=session,
        client_turn_id=uuid4(),
        image_sha256="a" * 64,
        image_media_type="image/png",
        screen_width=100,
        screen_height=200,
        model_name="fake-model",
    )
    assert created is True
    return run


@pytest.mark.asyncio
async def test_docker_failure_becomes_sanitized_retryable_run(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'docker-failure.db'}")
    Base.metadata.create_all(database.engine)
    service = AgentService(SqlAlchemyAgentRepository(database))
    session, _token = service.create_session(
        client_session_id=uuid4(),
        goal="打开设置",
        target_package="com.android.settings",
    )
    coordinator = AgentRunCoordinator(
        service,
        BlockingAgent(),
        UnavailableRegistry(),
        maximum_concurrency=1,
        queue_capacity=1,
    )
    await coordinator.start()
    try:
        run = _new_run(service, session)
        await coordinator.submit(run=run, session=session, screenshot=b"private-screen")
        snapshots = [snapshot async for snapshot in coordinator.events(run.run_id)]
    finally:
        await coordinator.stop()
        database.dispose()

    failed = snapshots[-1]
    assert failed.status.value == "failed"
    assert failed.error_code == "agent_unavailable"
    assert failed.retryable is True
    assert "docker details" not in repr(failed)


@pytest.mark.asyncio
async def test_runs_share_no_sandbox_state_concurrently_within_session(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'serialized.db'}")
    Base.metadata.create_all(database.engine)
    service = AgentService(SqlAlchemyAgentRepository(database))
    session, _token = service.create_session(
        client_session_id=uuid4(),
        goal="打开设置",
        target_package="com.android.settings",
    )
    agent = BlockingAgent()
    coordinator = AgentRunCoordinator(
        service,
        agent,
        FakeRegistry(),
        maximum_concurrency=2,
        queue_capacity=2,
    )
    await coordinator.start()
    try:
        first = _new_run(service, session)
        second = _new_run(service, session)
        await coordinator.submit(run=first, session=session, screenshot=b"private-screen")
        await coordinator.submit(run=second, session=session, screenshot=b"private-screen")
        await asyncio.wait_for(agent.started.wait(), timeout=1)
        await asyncio.sleep(0.02)
        assert agent.calls == 1
        agent.release.set()
        await asyncio.wait_for(coordinator._queue.join(), timeout=1)
    finally:
        agent.release.set()
        await coordinator.stop()
        database.dispose()

    assert agent.calls == 2
    assert agent.history_lengths == [0, 1]
