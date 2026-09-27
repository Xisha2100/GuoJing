"""Bounded, expiring in-process work with cancellation-safe workers."""

import asyncio
import json
import logging
from collections import deque
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from time import monotonic
from uuid import UUID

from guojing.application.agent.ports import SandboxRegistry, VisualGuidanceAgent
from guojing.application.agent.service import AgentService
from guojing.application.agent.usage import ModelCallLimit, ModelUsage, current_usage
from guojing.application.device_access import DeviceAccessService
from guojing.domain.agent_guidance import AgentRun, AgentRunStatus, AgentSession
from guojing.domain.device_access import AccessDenied

logger = logging.getLogger(__name__)
_TERMINAL = {AgentRunStatus.COMPLETED, AgentRunStatus.FAILED, AgentRunStatus.CANCELLED}


class AgentQueueFull(RuntimeError):
    pass


@dataclass(slots=True)
class PendingAgentRun:
    run: AgentRun
    session: AgentSession
    screenshot: bytearray
    deadline: float
    expiry_handle: asyncio.TimerHandle | None = None

    def erase(self) -> None:
        self.screenshot[:] = b"\x00" * len(self.screenshot)
        self.screenshot.clear()


class _PendingQueue:
    """A removable queue: expired screenshots immediately release queue capacity."""

    def __init__(self, capacity: int) -> None:
        self.items: deque[PendingAgentRun] = deque()
        self.capacity = capacity
        self._available = asyncio.Event()
        self._joined = asyncio.Event()
        self._joined.set()
        self._unfinished = 0

    def full(self) -> bool:
        return len(self.items) >= self.capacity

    def put_nowait(self, item: PendingAgentRun) -> None:
        if self.full():
            raise AgentQueueFull("queue_full")
        self.items.append(item)
        self._unfinished += 1
        self._joined.clear()
        self._available.set()

    async def get(self) -> PendingAgentRun:
        while not self.items:
            await self._available.wait()
        item = self.items.popleft()
        if item.expiry_handle is not None:
            item.expiry_handle.cancel()
        if not self.items:
            self._available.clear()
        return item

    def discard(self, item: PendingAgentRun) -> None:
        self.items.remove(item)
        if item.expiry_handle is not None:
            item.expiry_handle.cancel()
        if not self.items:
            self._available.clear()
        item.erase()
        self.task_done()

    def task_done(self) -> None:
        self._unfinished -= 1
        if self._unfinished == 0:
            self._joined.set()

    async def join(self) -> None:
        await self._joined.wait()


class AgentRunCoordinator:
    def __init__(
        self,
        service: AgentService,
        agent: VisualGuidanceAgent,
        sandboxes: SandboxRegistry,
        *,
        maximum_concurrency: int = 2,
        queue_capacity: int = 8,
        run_timeout_seconds: float = 90,
        queue_timeout_seconds: float = 30,
        cleanup_timeout_seconds: float = 5,
        access: DeviceAccessService | None = None,
    ) -> None:
        self._service = service
        self._agent = agent
        self._sandboxes = sandboxes
        self._access = access
        self._queue = _PendingQueue(queue_capacity)
        self._maximum_concurrency = maximum_concurrency
        self._run_timeout_seconds = run_timeout_seconds
        self._queue_timeout_seconds = queue_timeout_seconds
        self._cleanup_timeout_seconds = cleanup_timeout_seconds
        self._workers: list[asyncio.Task[None]] = []
        self._active: dict[UUID, asyncio.Task[None]] = {}
        self._active_sessions: dict[UUID, UUID] = {}
        self._session_locks: dict[UUID, asyncio.Lock] = {}
        self._events: dict[UUID, set[asyncio.Event]] = {}
        self._maintenance: asyncio.Task[None] | None = None
        self._cleanup_tasks: set[asyncio.Task[None]] = set()
        self._stopping = False
        self._cleanup_failed = False
        self.completed_count = 0
        self.failed_count = 0
        self.consecutive_failures = 0
        self.model_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.last_duration_ms = 0

    def bind_access(self, access: DeviceAccessService) -> None:
        if self._workers:
            raise RuntimeError("access must be bound before startup")
        self._access = access

    @property
    def ready(self) -> bool:
        return (
            not self._stopping
            and not self._cleanup_failed
            and len(self._workers) == self._maximum_concurrency
            and all(not task.done() for task in self._workers)
            and self._maintenance is not None
            and not self._maintenance.done()
        )

    @property
    def queue_depth(self) -> int:
        return len(self._queue.items)

    @property
    def active_count(self) -> int:
        return len(self._active)

    async def start(self) -> None:
        if self._workers:
            return
        self._stopping = False
        if self._access:
            self._access.recover()
        self._service.fail_incomplete_runs()
        self._workers = [
            asyncio.create_task(self._worker(), name=f"agent-worker-{index}")
            for index in range(self._maximum_concurrency)
        ]
        self._maintenance = asyncio.create_task(self._maintain())

    async def stop(self) -> None:
        self._stopping = True
        for item in list(self._queue.items):
            self._fail(item.run.run_id, "server_restarted", retryable=True)
            self._finish(item.run.run_id)
            self._queue.discard(item)
        tasks = list(self._active.values()) + self._workers
        if self._maintenance:
            tasks.append(self._maintenance)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._workers.clear()
        self._events.clear()
        self._session_locks.clear()
        try:
            await asyncio.wait_for(self._sandboxes.close(), self._cleanup_timeout_seconds)
        except (TimeoutError, Exception):
            self._cleanup_failed = True

    async def submit(self, *, run: AgentRun, session: AgentSession, screenshot: bytes) -> None:
        if not self.ready or self._queue.full():
            raise AgentQueueFull("queue_full")
        item = PendingAgentRun(
            run,
            session,
            bytearray(screenshot),
            monotonic() + self._queue_timeout_seconds,
        )
        try:
            self._queue.put_nowait(item)
            item.expiry_handle = asyncio.get_running_loop().call_at(
                item.deadline, self._expire_queued, item
            )
        except BaseException:
            item.erase()
            raise
        self._notify(run.run_id)

    def _expire_queued(self, item: PendingAgentRun) -> None:
        if item in self._queue.items:
            self._fail(item.run.run_id, "queue_timeout", retryable=True)
            self._finish(item.run.run_id)
            self._queue.discard(item)

    async def cancel(self, run: AgentRun) -> AgentRun:
        updated = self._service.cancel_run(run)
        for item in list(self._queue.items):
            if item.run.run_id == run.run_id:
                self._finish(run.run_id)
                self._queue.discard(item)
        task = self._active.get(run.run_id)
        if task is not None and not task.cancelling():
            task.cancel()
        self._notify(run.run_id)
        return updated

    async def events(self, run_id: UUID) -> AsyncGenerator[AgentRun, None]:
        event = asyncio.Event()
        self._events.setdefault(run_id, set()).add(event)
        try:
            while True:
                event.clear()
                run = self._service.get_run(run_id)
                if run is None:
                    return
                yield run
                if run.status in _TERMINAL:
                    return
                try:
                    await asyncio.wait_for(event.wait(), timeout=15)
                except TimeoutError:
                    pass
        finally:
            listeners = self._events.get(run_id)
            if listeners is not None:
                listeners.discard(event)
                if not listeners:
                    self._events.pop(run_id, None)

    async def destroy_session(self, session_id: UUID) -> None:
        for item in list(self._queue.items):
            if item.session.session_id == session_id:
                await self.cancel(item.run)
        tasks = []
        for run_id, active_session in list(self._active_sessions.items()):
            if active_session == session_id:
                task = self._active.get(run_id)
                if task:
                    task.cancel()
                    tasks.append(task)
        await asyncio.gather(*tasks, return_exceptions=True)
        self._session_locks.pop(session_id, None)

    async def _maintain(self) -> None:
        next_retention = monotonic() + 60
        while True:
            await asyncio.sleep(min(1, self._queue_timeout_seconds))
            for item in list(self._queue.items):
                if item.deadline <= monotonic():
                    self._fail(item.run.run_id, "queue_timeout", retryable=True)
                    self._finish(item.run.run_id)
                    self._queue.discard(item)
                elif not self._session_allowed(item.session):
                    await self.cancel(item.run)
            for run_id, session_id in list(self._active_sessions.items()):
                session = self._service.get_session(session_id)
                if session is None or not self._session_allowed(session):
                    run = self._service.get_run(run_id)
                    if run:
                        await self.cancel(run)
            if monotonic() >= next_retention:
                for session_id in self._service.purge_expired():
                    self._session_locks.pop(session_id, None)
                next_retention = monotonic() + 60

    def _session_allowed(self, session: AgentSession) -> bool:
        if not self._service.session_is_active(session):
            return False
        if self._access and session.device_id:
            try:
                self._access.require_active(session.device_id)
            except AccessDenied:
                return False
        return True

    async def _worker(self) -> None:
        while not self._stopping:
            item = await self._queue.get()
            run_id = item.run.run_id
            try:
                task = asyncio.create_task(self._execute(item))
                self._active[run_id] = task
                self._active_sessions[run_id] = item.session.session_id
                try:
                    await task
                except asyncio.CancelledError:
                    if self._stopping:
                        raise
                except Exception:
                    self._fail(run_id, "agent_unavailable", retryable=True)
            finally:
                self._active.pop(run_id, None)
                self._active_sessions.pop(run_id, None)
                self._finish(run_id)
                item.erase()
                self._queue.task_done()

    async def _execute(self, item: PendingAgentRun) -> None:
        session_id = item.session.session_id
        run_id = item.run.run_id
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        usage = ModelUsage(lambda: self._access.start(run_id) if self._access else None)
        token = current_usage.set(usage)
        started = monotonic()
        acquired = False
        try:
            async with asyncio.timeout(self._run_timeout_seconds):
                await lock.acquire()
                acquired = True
                run = self._service.get_run(run_id)
                session = self._service.get_session(session_id)
                if run is None or run.status is not AgentRunStatus.QUEUED:
                    return
                if session is None or not self._session_allowed(session):
                    self._service.cancel_run(run)
                    return
                if item.deadline <= monotonic():
                    self._fail(run_id, "queue_timeout", retryable=True)
                    return
                run = self._service.mark_running(run)
                self._notify(run_id)
                sandbox = await self._sandboxes.acquire(session_id)
                decision = await self._agent.analyze(
                    session=session,
                    history=self._service.get_history(session_id),
                    screenshot=bytes(item.screenshot),
                    image_media_type=run.image_media_type,
                    sandbox=sandbox,
                )
                latest = self._service.get_run(run_id)
                current = self._service.get_session(session_id)
                if latest and latest.status not in _TERMINAL and current:
                    if self._session_allowed(current):
                        self._service.complete_run(
                            latest,
                            current,
                            decision,
                            round((monotonic() - started) * 1000),
                        )
                    else:
                        self._service.cancel_run(latest)
        except asyncio.CancelledError:
            run = self._service.get_run(run_id)
            if run:
                self._service.cancel_run(run)
            raise
        except TimeoutError:
            self._fail(run_id, "agent_timeout", retryable=True)
        except ModelCallLimit:
            self._fail(run_id, "model_call_limit", retryable=True)
        except AccessDenied as error:
            self._fail(run_id, error.code, retryable=False)
        except Exception:
            self._fail(run_id, "agent_unavailable", retryable=True)
        finally:
            usage.closed = True
            current_usage.reset(token)
            item.erase()
            if acquired:
                cleanup = asyncio.create_task(self._sandboxes.destroy(session_id))
                self._cleanup_tasks.add(cleanup)
                cleanup.add_done_callback(self._cleanup_finished)
                try:
                    await asyncio.wait_for(asyncio.shield(cleanup), self._cleanup_timeout_seconds)
                except (asyncio.CancelledError, Exception):
                    self._cleanup_failed = True
                finally:
                    lock.release()
            self._finish(run_id)
            self._notify(run_id)
            final_run = self._service.get_run(run_id)
            self.model_calls += usage.calls
            self.input_tokens += usage.input_tokens
            self.output_tokens += usage.output_tokens
            self.last_duration_ms = round((monotonic() - started) * 1000)
            if final_run and final_run.status is AgentRunStatus.COMPLETED:
                self.completed_count += 1
                self.consecutive_failures = 0
            elif final_run and final_run.status is AgentRunStatus.FAILED:
                self.failed_count += 1
                self.consecutive_failures += 1
            logger.info(
                "agent_run %s",
                json.dumps(
                    {
                        "run_id": str(run_id),
                        "status": final_run.status.value if final_run else "expired",
                        "error_code": final_run.error_code if final_run else None,
                        "model_calls": usage.calls,
                        "input_tokens": usage.input_tokens,
                        "output_tokens": usage.output_tokens,
                        "duration_ms": round((monotonic() - started) * 1000),
                    }
                ),
            )
            # Only waiting/active sessions need a lock; do not retain session IDs forever.
            if not any(p.session.session_id == session_id for p in self._queue.items):
                if (
                    not lock.locked()
                    and sum(value == session_id for value in self._active_sessions.values()) <= 1
                ):
                    self._session_locks.pop(session_id, None)

    def _cleanup_finished(self, task: asyncio.Task[None]) -> None:
        self._cleanup_tasks.discard(task)
        if task.cancelled() or task.exception() is not None:
            self._cleanup_failed = True

    def _finish(self, run_id: UUID) -> None:
        if self._access:
            self._access.finish(run_id)

    def _fail(self, run_id: UUID, code: str, *, retryable: bool) -> None:
        latest = self._service.get_run(run_id)
        if latest and latest.status not in _TERMINAL:
            self._service.fail_run(latest, code, retryable=retryable)
        self._notify(run_id)

    def _notify(self, run_id: UUID) -> None:
        listeners = self._events.get(run_id)
        if listeners is not None:
            for event in listeners:
                event.set()
