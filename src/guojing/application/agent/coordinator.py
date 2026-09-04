"""Bounded in-process execution queue for screenshot analysis runs."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from time import monotonic
from uuid import UUID

from guojing.application.agent.ports import SandboxRegistry, VisualGuidanceAgent
from guojing.application.agent.service import AgentService
from guojing.domain.agent_guidance import AgentRun, AgentRunStatus, AgentSession


class AgentQueueFull(RuntimeError):
    """No more screenshot payloads can be retained in memory."""


@dataclass(slots=True)
class PendingAgentRun:
    run: AgentRun
    session: AgentSession
    screenshot: bytearray

    def erase(self) -> None:
        self.screenshot[:] = b"\x00" * len(self.screenshot)
        self.screenshot.clear()


class AgentRunCoordinator:
    """Execute agent runs without persisting raw screenshots."""

    def __init__(
        self,
        service: AgentService,
        agent: VisualGuidanceAgent,
        sandboxes: SandboxRegistry,
        *,
        maximum_concurrency: int = 4,
        queue_capacity: int = 20,
        run_timeout_seconds: int = 90,
    ) -> None:
        self._service = service
        self._agent = agent
        self._sandboxes = sandboxes
        self._queue: asyncio.Queue[PendingAgentRun] = asyncio.Queue(maxsize=queue_capacity)
        self._maximum_concurrency = maximum_concurrency
        self._run_timeout_seconds = run_timeout_seconds
        self._workers: list[asyncio.Task[None]] = []
        self._active: dict[UUID, asyncio.Task[None]] = {}
        self._active_sessions: dict[UUID, UUID] = {}
        self._session_locks: dict[UUID, asyncio.Lock] = {}
        self._events: dict[UUID, asyncio.Event] = {}

    async def start(self) -> None:
        if self._workers:
            return
        self._service.fail_incomplete_runs()
        self._workers = [
            asyncio.create_task(self._worker(), name=f"agent-worker-{index}")
            for index in range(self._maximum_concurrency)
        ]

    async def stop(self) -> None:
        for task in self._active.values():
            task.cancel()
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._active.values(), *self._workers, return_exceptions=True)
        self._active.clear()
        self._active_sessions.clear()
        self._session_locks.clear()
        self._workers.clear()
        while not self._queue.empty():
            pending = self._queue.get_nowait()
            pending.erase()
            self._queue.task_done()
        await self._sandboxes.close()

    async def submit(
        self,
        *,
        run: AgentRun,
        session: AgentSession,
        screenshot: bytes,
    ) -> None:
        if self._queue.full():
            raise AgentQueueFull("agent run queue is full")
        pending = PendingAgentRun(run=run, session=session, screenshot=bytearray(screenshot))
        try:
            self._queue.put_nowait(pending)
        except asyncio.QueueFull as error:
            pending.erase()
            raise AgentQueueFull("agent run queue is full") from error
        self._notify(run.run_id)

    async def cancel(self, run: AgentRun) -> AgentRun:
        updated = self._service.cancel_run(run)
        task = self._active.get(run.run_id)
        if task is not None:
            task.cancel()
        self._notify(run.run_id)
        return updated

    async def events(self, run_id: UUID) -> AsyncIterator[AgentRun]:
        while True:
            run = self._service.get_run(run_id)
            if run is None:
                return
            yield run
            if run.status in {
                AgentRunStatus.COMPLETED,
                AgentRunStatus.FAILED,
                AgentRunStatus.CANCELLED,
            }:
                self._events.pop(run_id, None)
                return
            event = self._events.setdefault(run_id, asyncio.Event())
            try:
                await asyncio.wait_for(event.wait(), timeout=15)
            except TimeoutError:
                continue
            finally:
                event.clear()

    async def destroy_session(self, session_id: UUID) -> None:
        tasks: list[asyncio.Task[None]] = []
        for run_id, active_session_id in list(self._active_sessions.items()):
            if active_session_id == session_id:
                task = self._active.get(run_id)
                if task is not None:
                    task.cancel()
                    tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._sandboxes.destroy(session_id)
        self._session_locks.pop(session_id, None)

    async def _worker(self) -> None:
        while True:
            pending = await self._queue.get()
            try:
                latest = self._service.get_run(pending.run.run_id)
                if latest is None or latest.status is not AgentRunStatus.QUEUED:
                    continue
                session = self._service.get_session(pending.session.session_id)
                if session is None or session.status.value != "active":
                    self._service.cancel_run(latest)
                    self._notify(latest.run_id)
                    continue
                task = asyncio.create_task(self._execute(pending, session))
                self._active[pending.run.run_id] = task
                self._active_sessions[pending.run.run_id] = pending.session.session_id
                try:
                    await task
                finally:
                    self._active.pop(pending.run.run_id, None)
                    self._active_sessions.pop(pending.run.run_id, None)
            finally:
                pending.erase()
                self._queue.task_done()

    async def _execute(self, pending: PendingAgentRun, session: AgentSession) -> None:
        lock = self._session_locks.setdefault(session.session_id, asyncio.Lock())
        async with lock:
            queued_run = self._service.get_run(pending.run.run_id)
            current_session = self._service.get_session(session.session_id)
            if queued_run is None or queued_run.status is not AgentRunStatus.QUEUED:
                return
            if current_session is None or current_session.status.value != "active":
                self._service.cancel_run(queued_run)
                self._notify(queued_run.run_id)
                return
            await self._execute_serialized(pending, queued_run, current_session)

    async def _execute_serialized(
        self,
        pending: PendingAgentRun,
        queued_run: AgentRun,
        session: AgentSession,
    ) -> None:
        run = self._service.mark_running(queued_run)
        self._notify(run.run_id)
        started = monotonic()
        sandbox = None
        try:
            sandbox = await self._sandboxes.acquire(session.session_id)
            active_session = self._service.attach_sandbox(session, sandbox.id)
            decision = await asyncio.wait_for(
                self._agent.analyze(
                    session=active_session,
                    history=self._service.get_history(pending.session.session_id),
                    screenshot=bytes(pending.screenshot),
                    image_media_type=pending.run.image_media_type,
                    sandbox=sandbox,
                ),
                timeout=self._run_timeout_seconds,
            )
            latest = self._service.get_run(run.run_id)
            if latest is None or latest.status is AgentRunStatus.CANCELLED:
                return
            duration_ms = round((monotonic() - started) * 1000)
            completed = self._service.complete_run(
                latest,
                active_session,
                decision,
                duration_ms,
            )
            self._notify(completed.run_id)
        except asyncio.CancelledError:
            latest = self._service.get_run(run.run_id)
            if latest is not None and latest.status is not AgentRunStatus.CANCELLED:
                self._service.cancel_run(latest)
            self._notify(run.run_id)
            raise
        except TimeoutError:
            self._fail(run.run_id, "agent_timeout", retryable=True)
        except Exception:
            self._fail(run.run_id, "agent_unavailable", retryable=True)
        finally:
            if sandbox is not None:
                try:
                    await asyncio.to_thread(
                        sandbox.upload_files,
                        [
                            (
                                "/workspace/current-screen.jpg",
                                bytes(len(pending.screenshot)),
                            )
                        ],
                    )
                except Exception:
                    pass
                try:
                    await asyncio.to_thread(sandbox.delete, "/workspace/current-screen.jpg")
                except Exception:
                    pass

    def _fail(self, run_id: UUID, error_code: str, *, retryable: bool) -> None:
        latest = self._service.get_run(run_id)
        if latest is not None and latest.status is not AgentRunStatus.CANCELLED:
            self._service.fail_run(latest, error_code, retryable=retryable)
        self._notify(run_id)

    def _notify(self, run_id: UUID) -> None:
        self._events.setdefault(run_id, asyncio.Event()).set()
