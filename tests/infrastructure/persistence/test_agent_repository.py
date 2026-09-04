from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from guojing.application.agent.service import AgentService, AgentSessionNotFound
from guojing.domain.agent_guidance import AgentRunStatus, AgentSessionStatus
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
