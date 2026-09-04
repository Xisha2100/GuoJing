"""Ports owned by the visual guidance application layer."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from deepagents.backends.protocol import SandboxBackendProtocol

from guojing.domain.agent_guidance import AgentRun, AgentSession, GuidanceDecision, GuidanceStep


class AgentRepository(Protocol):
    def create_session(self, session: AgentSession) -> bool: ...

    def get_session(self, session_id: UUID) -> AgentSession | None: ...

    def get_session_by_client_id(self, client_session_id: UUID) -> AgentSession | None: ...

    def update_session(self, session: AgentSession) -> None: ...

    def create_run(self, run: AgentRun) -> bool: ...

    def get_run(self, run_id: UUID) -> AgentRun | None: ...

    def get_run_by_turn(self, session_id: UUID, client_turn_id: UUID) -> AgentRun | None: ...

    def update_run(self, run: AgentRun) -> None: ...

    def list_steps(self, session_id: UUID) -> Sequence[GuidanceStep]: ...

    def add_step(self, step: GuidanceStep) -> None: ...

    def fail_incomplete_runs(self, *, completed_at: datetime) -> int: ...

    def cancel_incomplete_runs(self, session_id: UUID, *, completed_at: datetime) -> int: ...


class VisualGuidanceAgent(Protocol):
    async def analyze(
        self,
        *,
        session: AgentSession,
        history: Sequence[GuidanceStep],
        screenshot: bytes,
        image_media_type: str,
        sandbox: SandboxBackendProtocol,
    ) -> GuidanceDecision: ...


class SandboxRegistry(Protocol):
    async def acquire(self, session_id: UUID) -> SandboxBackendProtocol: ...

    async def destroy(self, session_id: UUID) -> None: ...

    async def cleanup_idle(self) -> None: ...

    async def close(self) -> None: ...
