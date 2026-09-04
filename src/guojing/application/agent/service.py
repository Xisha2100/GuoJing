"""Session and run use cases for the visual guidance agent."""

import hmac
import secrets
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from guojing.application.agent.ports import AgentRepository
from guojing.domain.agent_guidance import (
    AgentRun,
    AgentRunStatus,
    AgentSession,
    AgentSessionStatus,
    GuidanceDecision,
    GuidanceStep,
)


class AgentSessionNotFound(LookupError):
    """The session is absent, expired, or inaccessible."""


class AgentRunNotFound(LookupError):
    """The run is absent or inaccessible."""


class AgentSessionConflict(ValueError):
    """A client session identifier was already consumed."""


class AgentSessionClosed(ValueError):
    """The requested session no longer accepts runs."""


class AgentService:
    """Persist safe metadata while keeping screenshots outside repositories."""

    def __init__(
        self,
        repository: AgentRepository,
        *,
        session_ttl: timedelta = timedelta(hours=24),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._session_ttl = session_ttl
        self._clock = clock or (lambda: datetime.now(UTC))

    def create_session(
        self,
        *,
        client_session_id: UUID,
        goal: str,
        target_package: str,
    ) -> tuple[AgentSession, str]:
        if self._repository.get_session_by_client_id(client_session_id) is not None:
            raise AgentSessionConflict("client_session_id already exists")
        now = self._now()
        token = secrets.token_urlsafe(32)
        session = AgentSession(
            session_id=uuid4(),
            client_session_id=client_session_id,
            access_token_digest=_token_digest(token),
            goal=goal,
            target_package=target_package,
            status=AgentSessionStatus.ACTIVE,
            current_step=0,
            sandbox_id=None,
            created_at=now,
            updated_at=now,
            expires_at=now + self._session_ttl,
        )
        if not self._repository.create_session(session):
            raise AgentSessionConflict("client_session_id already exists")
        return session, token

    def require_session(self, session_id: UUID, token: str) -> AgentSession:
        session = self._repository.get_session(session_id)
        if session is None or not hmac.compare_digest(
            session.access_token_digest,
            _token_digest(token),
        ):
            raise AgentSessionNotFound("agent session was not found")
        if session.expires_at <= self._now():
            raise AgentSessionNotFound("agent session was not found")
        return session

    def create_or_get_run(
        self,
        *,
        session: AgentSession,
        client_turn_id: UUID,
        image_sha256: str,
        image_media_type: str,
        screen_width: int,
        screen_height: int,
        model_name: str,
    ) -> tuple[AgentRun, bool]:
        if session.status is not AgentSessionStatus.ACTIVE:
            raise AgentSessionClosed("agent session is not active")
        existing = self._repository.get_run_by_turn(session.session_id, client_turn_id)
        if existing is not None:
            return existing, False
        run = AgentRun(
            run_id=uuid4(),
            session_id=session.session_id,
            client_turn_id=client_turn_id,
            status=AgentRunStatus.QUEUED,
            image_sha256=image_sha256,
            image_media_type=image_media_type,
            screen_width=screen_width,
            screen_height=screen_height,
            result=None,
            error_code=None,
            retryable=False,
            model_name=model_name,
            duration_ms=None,
            created_at=self._now(),
            started_at=None,
            completed_at=None,
        )
        if not self._repository.create_run(run):
            existing = self._repository.get_run_by_turn(session.session_id, client_turn_id)
            if existing is None:
                raise AgentSessionConflict("agent run could not be created")
            return existing, False
        return run, True

    def get_authorized_run(self, run_id: UUID, token: str) -> tuple[AgentSession, AgentRun]:
        run = self._repository.get_run(run_id)
        if run is None:
            raise AgentRunNotFound("agent run was not found")
        try:
            session = self.require_session(run.session_id, token)
        except AgentSessionNotFound as error:
            raise AgentRunNotFound("agent run was not found") from error
        return session, run

    def get_run(self, run_id: UUID) -> AgentRun | None:
        return self._repository.get_run(run_id)

    def get_session(self, session_id: UUID) -> AgentSession | None:
        return self._repository.get_session(session_id)

    def get_history(self, session_id: UUID) -> Sequence[GuidanceStep]:
        return self._repository.list_steps(session_id)

    def attach_sandbox(self, session: AgentSession, sandbox_id: str) -> AgentSession:
        updated = replace(session, sandbox_id=sandbox_id, updated_at=self._now())
        self._repository.update_session(updated)
        return updated

    def mark_running(self, run: AgentRun) -> AgentRun:
        updated = replace(run, status=AgentRunStatus.RUNNING, started_at=self._now())
        self._repository.update_run(updated)
        return updated

    def retry_run(self, run: AgentRun) -> AgentRun:
        if run.status is not AgentRunStatus.FAILED or not run.retryable:
            return run
        updated = replace(
            run,
            status=AgentRunStatus.QUEUED,
            result=None,
            error_code=None,
            retryable=False,
            duration_ms=None,
            started_at=None,
            completed_at=None,
        )
        self._repository.update_run(updated)
        return updated

    def complete_run(
        self,
        run: AgentRun,
        session: AgentSession,
        decision: GuidanceDecision,
        duration_ms: int,
    ) -> AgentRun:
        now = self._now()
        updated = replace(
            run,
            status=AgentRunStatus.COMPLETED,
            result=decision,
            retryable=False,
            duration_ms=duration_ms,
            completed_at=now,
        )
        step_number = session.current_step + 1
        self._repository.update_run(updated)
        self._repository.add_step(
            GuidanceStep(
                session_id=session.session_id,
                run_id=run.run_id,
                step_number=step_number,
                decision=decision,
                created_at=now,
            )
        )
        session_status = (
            AgentSessionStatus.COMPLETED
            if decision.status.value == "completed"
            else AgentSessionStatus.ACTIVE
        )
        self._repository.update_session(
            replace(
                session,
                status=session_status,
                current_step=step_number,
                updated_at=now,
            )
        )
        return updated

    def fail_run(self, run: AgentRun, error_code: str, *, retryable: bool) -> AgentRun:
        updated = replace(
            run,
            status=AgentRunStatus.FAILED,
            error_code=error_code,
            retryable=retryable,
            completed_at=self._now(),
        )
        self._repository.update_run(updated)
        return updated

    def cancel_run(self, run: AgentRun) -> AgentRun:
        if run.status in {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }:
            return run
        updated = replace(
            run,
            status=AgentRunStatus.CANCELLED,
            error_code="cancelled",
            retryable=False,
            completed_at=self._now(),
        )
        self._repository.update_run(updated)
        return updated

    def close_session(self, session: AgentSession) -> AgentSession:
        if session.status is AgentSessionStatus.CLOSED:
            return session
        updated = replace(
            session,
            status=AgentSessionStatus.CLOSED,
            sandbox_id=None,
            updated_at=self._now(),
        )
        self._repository.update_session(updated)
        self._repository.cancel_incomplete_runs(
            session.session_id,
            completed_at=self._now(),
        )
        return updated

    def fail_incomplete_runs(self) -> int:
        return self._repository.fail_incomplete_runs(completed_at=self._now())

    def _now(self) -> datetime:
        return self._clock().astimezone(UTC)


def _token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()
