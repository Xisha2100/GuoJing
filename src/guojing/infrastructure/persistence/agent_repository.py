"""SQLAlchemy repository for visual guidance sessions and runs."""

import json
from datetime import UTC, datetime
from typing import Any, cast, overload
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError

from guojing.domain.agent_guidance import (
    AgentRun,
    AgentRunStatus,
    AgentSession,
    AgentSessionStatus,
    GuidanceDecision,
    GuidanceStatus,
    GuidanceStep,
    NormalizedTarget,
)
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import (
    AgentRunRecord,
    AgentSessionRecord,
    GuidanceStepRecord,
)


class SqlAlchemyAgentRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def create_session(self, session: AgentSession) -> bool:
        with self._database.new_session() as db:
            db.add(_session_record(session))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                return False
            return True

    def get_session(self, session_id: UUID) -> AgentSession | None:
        with self._database.new_session() as db:
            record = db.get(AgentSessionRecord, str(session_id))
            return _to_session(record) if record is not None else None

    def get_session_by_client_id(self, client_session_id: UUID) -> AgentSession | None:
        with self._database.new_session() as db:
            record = db.scalar(
                select(AgentSessionRecord).where(
                    AgentSessionRecord.client_session_id == str(client_session_id)
                )
            )
            return _to_session(record) if record is not None else None

    def update_session(self, session: AgentSession) -> None:
        with self._database.new_session() as db:
            db.merge(_session_record(session))
            db.commit()

    def create_run(self, run: AgentRun) -> bool:
        with self._database.new_session() as db:
            db.add(_run_record(run))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                return False
            return True

    def get_run(self, run_id: UUID) -> AgentRun | None:
        with self._database.new_session() as db:
            record = db.get(AgentRunRecord, str(run_id))
            return _to_run(record) if record is not None else None

    def get_run_by_turn(self, session_id: UUID, client_turn_id: UUID) -> AgentRun | None:
        with self._database.new_session() as db:
            record = db.scalar(
                select(AgentRunRecord).where(
                    AgentRunRecord.session_id == str(session_id),
                    AgentRunRecord.client_turn_id == str(client_turn_id),
                )
            )
            return _to_run(record) if record is not None else None

    def update_run(self, run: AgentRun) -> None:
        with self._database.new_session() as db:
            db.merge(_run_record(run))
            db.commit()

    def list_steps(self, session_id: UUID) -> list[GuidanceStep]:
        with self._database.new_session() as db:
            records = db.scalars(
                select(GuidanceStepRecord)
                .where(GuidanceStepRecord.session_id == str(session_id))
                .order_by(GuidanceStepRecord.step_number)
            ).all()
            return [_to_step(record) for record in records]

    def add_step(self, step: GuidanceStep) -> None:
        target_json = None
        if step.decision.target is not None:
            target_json = json.dumps(
                {
                    "left": step.decision.target.left,
                    "top": step.decision.target.top,
                    "right": step.decision.target.right,
                    "bottom": step.decision.target.bottom,
                },
                separators=(",", ":"),
            )
        with self._database.new_session() as db:
            db.add(
                GuidanceStepRecord(
                    step_id=str(uuid4()),
                    session_id=str(step.session_id),
                    run_id=str(step.run_id),
                    step_number=step.step_number,
                    status=step.decision.status.value,
                    instruction=step.decision.instruction,
                    target_json=target_json,
                    confidence=step.decision.confidence,
                    created_at=step.created_at,
                )
            )
            db.commit()

    def fail_incomplete_runs(self, *, completed_at: datetime) -> int:
        with self._database.new_session() as db:
            result = db.execute(
                update(AgentRunRecord)
                .where(AgentRunRecord.status.in_(["queued", "running"]))
                .values(
                    status=AgentRunStatus.FAILED.value,
                    error_code="server_restarted",
                    retryable=True,
                    completed_at=completed_at,
                )
            )
            db.commit()
            return int(cast(CursorResult[Any], result).rowcount or 0)

    def cancel_incomplete_runs(self, session_id: UUID, *, completed_at: datetime) -> int:
        with self._database.new_session() as db:
            result = db.execute(
                update(AgentRunRecord)
                .where(
                    AgentRunRecord.session_id == str(session_id),
                    AgentRunRecord.status.in_(["queued", "running"]),
                )
                .values(
                    status=AgentRunStatus.CANCELLED.value,
                    error_code="cancelled",
                    retryable=False,
                    completed_at=completed_at,
                )
            )
            db.commit()
            return int(cast(CursorResult[Any], result).rowcount or 0)


def _session_record(value: AgentSession) -> AgentSessionRecord:
    return AgentSessionRecord(
        session_id=str(value.session_id),
        client_session_id=str(value.client_session_id),
        access_token_digest=value.access_token_digest,
        goal=value.goal,
        target_package=value.target_package,
        status=value.status.value,
        current_step=value.current_step,
        sandbox_id=value.sandbox_id,
        created_at=value.created_at,
        updated_at=value.updated_at,
        expires_at=value.expires_at,
    )


def _run_record(value: AgentRun) -> AgentRunRecord:
    target = value.result.target if value.result is not None else None
    return AgentRunRecord(
        run_id=str(value.run_id),
        session_id=str(value.session_id),
        client_turn_id=str(value.client_turn_id),
        status=value.status.value,
        image_sha256=value.image_sha256,
        image_media_type=value.image_media_type,
        screen_width=value.screen_width,
        screen_height=value.screen_height,
        result_status=value.result.status.value if value.result is not None else None,
        instruction=value.result.instruction if value.result is not None else None,
        target_left=target.left if target is not None else None,
        target_top=target.top if target is not None else None,
        target_right=target.right if target is not None else None,
        target_bottom=target.bottom if target is not None else None,
        confidence=value.result.confidence if value.result is not None else None,
        error_code=value.error_code,
        retryable=value.retryable,
        model_name=value.model_name,
        duration_ms=value.duration_ms,
        created_at=value.created_at,
        started_at=value.started_at,
        completed_at=value.completed_at,
    )


def _to_session(record: AgentSessionRecord) -> AgentSession:
    return AgentSession(
        session_id=UUID(record.session_id),
        client_session_id=UUID(record.client_session_id),
        access_token_digest=record.access_token_digest,
        goal=record.goal,
        target_package=record.target_package,
        status=AgentSessionStatus(record.status),
        current_step=record.current_step,
        sandbox_id=record.sandbox_id,
        created_at=_as_utc(record.created_at),
        updated_at=_as_utc(record.updated_at),
        expires_at=_as_utc(record.expires_at),
    )


def _to_run(record: AgentRunRecord) -> AgentRun:
    result = None
    if record.result_status is not None and record.confidence is not None:
        target = None
        if record.target_left is not None:
            assert record.target_top is not None
            assert record.target_right is not None
            assert record.target_bottom is not None
            target = NormalizedTarget(
                left=record.target_left,
                top=record.target_top,
                right=record.target_right,
                bottom=record.target_bottom,
            )
        result = GuidanceDecision(
            status=GuidanceStatus(record.result_status),
            instruction=record.instruction,
            target=target,
            confidence=record.confidence,
        )
    return AgentRun(
        run_id=UUID(record.run_id),
        session_id=UUID(record.session_id),
        client_turn_id=UUID(record.client_turn_id),
        status=AgentRunStatus(record.status),
        image_sha256=record.image_sha256,
        image_media_type=record.image_media_type,
        screen_width=record.screen_width,
        screen_height=record.screen_height,
        result=result,
        error_code=record.error_code,
        retryable=record.retryable,
        model_name=record.model_name,
        duration_ms=record.duration_ms,
        created_at=_as_utc(record.created_at),
        started_at=_as_utc(record.started_at),
        completed_at=_as_utc(record.completed_at),
    )


def _to_step(record: GuidanceStepRecord) -> GuidanceStep:
    target = None
    if record.target_json is not None:
        target = NormalizedTarget(**json.loads(record.target_json))
    return GuidanceStep(
        session_id=UUID(record.session_id),
        run_id=UUID(record.run_id),
        step_number=record.step_number,
        decision=GuidanceDecision(
            status=GuidanceStatus(record.status),
            instruction=record.instruction,
            target=target,
            confidence=record.confidence,
        ),
        created_at=_as_utc(record.created_at),
    )


@overload
def _as_utc(value: datetime) -> datetime: ...


@overload
def _as_utc(value: None) -> None: ...


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
