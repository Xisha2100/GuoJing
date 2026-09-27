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
async def test_closing_one_event_stream_keeps_other_stream_live(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'event-listeners.db'}")
    Base.metadata.create_all(database.engine)
    service = AgentService(SqlAlchemyAgentRepository(database))
    session, _ = service.create_session(
        client_session_id=uuid4(), goal="设置", target_package="com.test.app"
    )
    agent = BlockingAgent()
    coordinator = AgentRunCoordinator(service, agent, FakeRegistry(), maximum_concurrency=1)
    await coordinator.start()
    first_stream = None
    second_stream = None
    try:
        run = _new_run(service, session)
        await coordinator.submit(run=run, session=session, screenshot=b"private-screen")
        await asyncio.wait_for(agent.started.wait(), 1)
        first_stream = coordinator.events(run.run_id)
        second_stream = coordinator.events(run.run_id)
        assert (await anext(first_stream)).status.value == "running"
        assert (await anext(second_stream)).status.value == "running"
        await first_stream.aclose()

        next_update = asyncio.create_task(anext(second_stream))
        await asyncio.sleep(0)
        agent.release.set()
        completed = await asyncio.wait_for(next_update, 1)
        assert completed.status.value == "completed"
    finally:
        agent.release.set()
        if first_stream is not None:
            await first_stream.aclose()
        if second_stream is not None:
            await second_stream.aclose()
        await coordinator.stop()
        database.dispose()


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


@pytest.mark.asyncio
async def test_cancelled_run_does_not_kill_worker(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'cancel-worker.db'}")
    Base.metadata.create_all(database.engine)
    service = AgentService(SqlAlchemyAgentRepository(database))
    session, _ = service.create_session(
        client_session_id=uuid4(), goal="设置", target_package="com.test.app"
    )
    agent = BlockingAgent()
    coordinator = AgentRunCoordinator(service, agent, FakeRegistry(), maximum_concurrency=1)
    await coordinator.start()
    try:
        first = _new_run(service, session)
        await coordinator.submit(run=first, session=session, screenshot=b"private-screen")
        await asyncio.wait_for(agent.started.wait(), 1)
        await coordinator.cancel(first)
        await asyncio.wait_for(coordinator._queue.join(), 1)
        assert coordinator.ready
        agent.release.set()
        second = _new_run(service, session)
        await coordinator.submit(run=second, session=session, screenshot=b"private-screen")
        await asyncio.wait_for(coordinator._queue.join(), 1)
        assert service.get_run(second.run_id).status.value == "completed"  # type: ignore[union-attr]
        assert agent.calls == 2
    finally:
        await coordinator.stop()
        database.dispose()


@pytest.mark.asyncio
async def test_queue_timeout_erases_image_and_frees_capacity_before_worker_finishes(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'expire.db'}")
    Base.metadata.create_all(database.engine)
    service = AgentService(SqlAlchemyAgentRepository(database))
    session, _ = service.create_session(
        client_session_id=uuid4(), goal="设置", target_package="com.test.app"
    )
    agent = BlockingAgent()
    coordinator = AgentRunCoordinator(
        service,
        agent,
        FakeRegistry(),
        maximum_concurrency=1,
        queue_capacity=1,
        queue_timeout_seconds=0.03,
    )
    await coordinator.start()
    try:
        first = _new_run(service, session)
        second = _new_run(service, session)
        await coordinator.submit(run=first, session=session, screenshot=b"private-screen")
        await asyncio.wait_for(agent.started.wait(), 1)
        await coordinator.submit(run=second, session=session, screenshot=b"private-screen")
        image = coordinator._queue.items[0].screenshot
        await asyncio.sleep(0.08)
        assert image == bytearray()
        assert coordinator.queue_depth == 0
        assert service.get_run(second.run_id).error_code == "queue_timeout"  # type: ignore[union-attr]
    finally:
        await coordinator.stop()
        database.dispose()


@pytest.mark.asyncio
async def test_failed_cleanup_stops_admission(tmp_path: Path) -> None:
    class BrokenCleanup(FakeRegistry):
        async def destroy(self, _session_id: UUID) -> None:
            raise RuntimeError("cleanup failed")

    database = Database(f"sqlite:///{tmp_path / 'cleanup.db'}")
    Base.metadata.create_all(database.engine)
    service = AgentService(SqlAlchemyAgentRepository(database))
    session, _ = service.create_session(
        client_session_id=uuid4(), goal="设置", target_package="com.test.app"
    )
    agent = BlockingAgent()
    agent.release.set()
    coordinator = AgentRunCoordinator(service, agent, BrokenCleanup())
    await coordinator.start()
    try:
        run = _new_run(service, session)
        await coordinator.submit(run=run, session=session, screenshot=b"private-screen")
        await asyncio.wait_for(coordinator._queue.join(), 1)
        assert not coordinator.ready
        with pytest.raises(AgentQueueFull):
            await coordinator.submit(
                run=_new_run(service, session), session=session, screenshot=b"private-screen"
            )
    finally:
        await coordinator.stop()
        database.dispose()


@pytest.mark.asyncio
async def test_revoked_device_cancels_running_task_and_worker_survives(tmp_path: Path) -> None:
    import secrets

    from guojing.application.device_access import DeviceAccessService
    from guojing.infrastructure.persistence.device_repository import SqlAlchemyDeviceRepository
    from guojing.infrastructure.persistence.models import DeviceRecord

    database = Database(f"sqlite:///{tmp_path / 'revoke-active.db'}")
    Base.metadata.create_all(database.engine)
    repository = SqlAlchemyDeviceRepository(database)
    access = DeviceAccessService(repository)
    device = access.activate(access.invite("device"), uuid4(), secrets.token_urlsafe(32))
    service = AgentService(SqlAlchemyAgentRepository(database))
    session, _ = service.create_session(
        client_session_id=uuid4(),
        goal="设置",
        target_package="synthetic.app",
        device_id=device.device_id,
    )
    agent = BlockingAgent()
    coordinator = AgentRunCoordinator(
        service, agent, FakeRegistry(), maximum_concurrency=1, access=access
    )
    await coordinator.start()
    try:
        run = _new_run(service, session)
        access.reserve(run.run_id, device.device_id)
        await coordinator.submit(run=run, session=session, screenshot=b"private-screen")
        await asyncio.wait_for(agent.started.wait(), 1)
        with repository.transaction() as db:
            saved = db.get(DeviceRecord, str(device.device_id))
            assert saved
            saved.revoked = True
        await asyncio.wait_for(coordinator._queue.join(), 3)
        final = service.get_run(run.run_id)
        assert final and final.status.value == "cancelled"
        assert coordinator.ready
    finally:
        agent.release.set()
        await coordinator.stop()
        database.dispose()
