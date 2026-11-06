from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from guojing.application.agent.service import AgentService, AgentSessionNotFound
from guojing.domain.agent_guidance import (
    AgentRunStatus,
    AgentSessionStatus,
    GuidanceDecision,
    GuidanceStatus,
)
from guojing.domain.device_access import AccessDenied
from guojing.infrastructure.persistence.agent_repository import SqlAlchemyAgentRepository
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import Base


def test_session_token_is_stored_only_as_digest(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'repository.db'}")
    Base.metadata.create_all(database.engine)
    service = AgentService(
        SqlAlchemyAgentRepository(database),
        clock=lambda: datetime(2026, 9, 4, tzinfo=UTC),
    )

    session, token = service.create_session(
        client_session_id=uuid4(),
        goal="打开设置",
        target_package="com.android.settings",
    )

    assert session.status is AgentSessionStatus.ACTIVE
    assert token not in session.access_token_digest
    assert service.require_session(session.session_id, token) == session
    database.dispose()


def test_startup_marks_incomplete_runs_as_retryable(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'restart.db'}")
    Base.metadata.create_all(database.engine)
    now = datetime(2026, 9, 4, tzinfo=UTC)
    service = AgentService(SqlAlchemyAgentRepository(database), clock=lambda: now)
    session, _token = service.create_session(
        client_session_id=uuid4(),
        goal="打开设置",
        target_package="com.android.settings",
    )
    run, _created = service.create_or_get_run(
        session=session,
        client_turn_id=uuid4(),
        image_sha256="a" * 64,
        image_media_type="image/jpeg",
        screen_width=100,
        screen_height=200,
        model_name="vision-model",
    )

    assert service.fail_incomplete_runs() == 1
    failed = service.get_run(run.run_id)
    assert failed is not None
    assert failed.status is AgentRunStatus.FAILED
    assert failed.retryable is True
    database.dispose()


def test_closing_session_cancels_incomplete_runs(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'close.db'}")
    Base.metadata.create_all(database.engine)
    service = AgentService(SqlAlchemyAgentRepository(database))
    session, _token = service.create_session(
        client_session_id=uuid4(),
        goal="打开设置",
        target_package="com.android.settings",
    )
    attached = service.attach_sandbox(session, "sandbox-id")
    run, _created = service.create_or_get_run(
        session=attached,
        client_turn_id=uuid4(),
        image_sha256="a" * 64,
        image_media_type="image/png",
        screen_width=100,
        screen_height=200,
        model_name="vision-model",
    )

    closed = service.close_session(attached)
    cancelled = service.get_run(run.run_id)

    assert closed.status is AgentSessionStatus.CLOSED
    assert closed.sandbox_id is None
    assert cancelled is not None
    assert cancelled.status is AgentRunStatus.CANCELLED
    database.dispose()


def test_expired_session_token_is_rejected(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'expired.db'}")
    Base.metadata.create_all(database.engine)
    now = datetime(2026, 9, 4, tzinfo=UTC)
    current = now
    service = AgentService(
        SqlAlchemyAgentRepository(database),
        clock=lambda: current,
    )
    session, token = service.create_session(
        client_session_id=uuid4(),
        goal="打开设置",
        target_package="com.android.settings",
    )
    current = session.expires_at

    with pytest.raises(AgentSessionNotFound):
        service.require_session(session.session_id, token)
    database.dispose()


def test_session_capacity_is_atomic_persistent_and_released_after_expiry(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'capacity.db'}")
    Base.metadata.create_all(database.engine)
    now = datetime(2026, 11, 6, tzinfo=UTC)
    device_id = uuid4()
    service = AgentService(SqlAlchemyAgentRepository(database), clock=lambda: now)

    def create() -> bool:
        try:
            session, _ = service.create_session(
                client_session_id=uuid4(),
                goal="设置",
                target_package="test.app",
                device_id=device_id,
            )
            service.close_session(session)
            return True
        except AccessDenied as error:
            assert error.code == "session_capacity_reached"
            return False

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            assert sum(pool.map(lambda _: create(), range(105))) == 100
        # A new repository cannot reset the persisted limit; closed sessions still count.
        service = AgentService(SqlAlchemyAgentRepository(database), clock=lambda: now)
        assert not create()
        now += timedelta(hours=24)
        assert create()
    finally:
        database.dispose()


@pytest.mark.parametrize("close_session", [False, True])
def test_late_completion_cannot_overwrite_cancellation(tmp_path: Path, close_session: bool) -> None:
    database = Database(f"sqlite:///{tmp_path / 'race.db'}")
    Base.metadata.create_all(database.engine)
    service = AgentService(SqlAlchemyAgentRepository(database))
    try:
        session, _ = service.create_session(
            client_session_id=uuid4(), goal="设置", target_package="test.app"
        )
        run, _ = service.create_or_get_run(
            session=session,
            client_turn_id=uuid4(),
            image_sha256="a" * 64,
            image_media_type="image/png",
            screen_width=10,
            screen_height=10,
            model_name="fake",
        )
        running = service.mark_running(run)
        if close_session:
            service.close_session(session)
        else:
            service.cancel_run(running)
        service.complete_run(
            running,
            session,
            GuidanceDecision(GuidanceStatus.CANNOT_DETERMINE, "重试", None, 0.5),
            1,
        )
        service.mark_running(run)
        stored = service.get_run(run.run_id)
        assert stored is not None and stored.status is AgentRunStatus.CANCELLED
        assert service.get_history(session.session_id) == []
        if close_session:
            restored = service.get_session(session.session_id)
            assert restored is not None and restored.status is AgentSessionStatus.CLOSED
    finally:
        database.dispose()


def test_sqlite_lock_timeout_returns_safe_retryable_error(tmp_path: Path) -> None:
    from sqlalchemy import text

    database = Database(f"sqlite:///{tmp_path / 'busy.db'}")
    try:
        with database.engine.connect() as writer:
            writer.exec_driver_sql("BEGIN IMMEDIATE")
            with pytest.raises(AccessDenied) as caught, database.new_session() as waiting:
                waiting.execute(text("PRAGMA busy_timeout=20"))
                waiting.execute(text("BEGIN IMMEDIATE"))
            assert caught.value.code == "service_busy"
            assert caught.value.status == 503
            assert caught.value.retry_after == 5
            writer.rollback()
    finally:
        database.dispose()
