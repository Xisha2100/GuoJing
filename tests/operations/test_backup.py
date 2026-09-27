import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from tests.infrastructure.persistence.test_device_repository import activate, setup

from guojing.application.agent.service import AgentService
from guojing.domain.device_access import AccessDenied
from guojing.infrastructure.persistence.agent_repository import SqlAlchemyAgentRepository
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.device_repository import SqlAlchemyDeviceRepository
from guojing.infrastructure.persistence.models import Base, DeviceRecord
from guojing.infrastructure.runtime import ProcessLease
from guojing.operations.backup import export_authorization, prune_backups, restore_authorization


def test_backup_excludes_content_and_restore_preserves_auth_but_pauses_analysis(
    tmp_path: Path,
) -> None:
    database, _repository, access = setup(tmp_path)
    device, credential = activate(access)
    service = AgentService(SqlAlchemyAgentRepository(database))
    service.create_session(
        client_session_id=uuid4(), goal="PRIVATE GOAL", target_package="private.app"
    )
    run = uuid4()
    access.reserve(run, device)
    access.start(run)
    access.finish(run)
    snapshot = export_authorization(database)
    assert b"PRIVATE GOAL" not in snapshot and b"private.app" not in snapshot
    assert set(json.loads(snapshot)["tables"]) == {"devices", "device_invitations", "daily_usage"}
    restored = Database(f"sqlite:///{tmp_path / 'restored.db'}")
    Base.metadata.create_all(restored.engine)
    restore_authorization(restored, snapshot)
    restored_access = type(access)(SqlAlchemyDeviceRepository(restored))
    assert restored_access.authenticate(credential).device_id == device
    with pytest.raises(AccessDenied, match="service_paused"):
        restored_access.reserve(uuid4(), device)
    with pytest.raises(ValueError, match="empty database"):
        restore_authorization(restored, snapshot)
    restored.dispose()
    database.dispose()


def test_restore_rolls_back_all_authorization_on_invalid_payload(tmp_path: Path) -> None:
    database, _, access = setup(tmp_path)
    activate(access)
    data = json.loads(export_authorization(database))
    data["tables"]["daily_usage"] = [{"unexpected": "invalid"}]
    restored = Database(f"sqlite:///{tmp_path / 'restored.db'}")
    Base.metadata.create_all(restored.engine)
    with pytest.raises(ValueError):
        restore_authorization(restored, json.dumps(data).encode())
    with restored.new_session() as db:
        assert db.get(DeviceRecord, data["tables"]["devices"][0]["device_id"]) is None
    database.dispose()
    restored.dispose()


def test_process_lease_blocks_second_instance_until_owner_releases(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'lease.db'}"
    first, second = ProcessLease(url), ProcessLease(url)
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match="another API process"):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


class FakeOss:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.deleted: list[str] = []

    def list_objects_v2(self, request: Any) -> Any:
        old = SimpleNamespace(key="old", last_modified=self.now - timedelta(hours=24))
        recent = SimpleNamespace(key="recent", last_modified=self.now - timedelta(hours=23))
        return SimpleNamespace(contents=[old, recent], is_truncated=False)

    def delete_object(self, request: Any) -> None:
        self.deleted.append(request.key)


def test_oss_retention_removes_only_snapshots_at_least_24_hours_old() -> None:
    now = datetime.now(UTC)
    client = FakeOss(now)
    prune_backups(client, "private-bucket", "prefix/", now)
    assert client.deleted == ["old"]


def test_session_expiry_cascades_runs_and_steps_and_rejects_access(tmp_path: Path) -> None:
    from sqlalchemy import func, select
    from tests.application.agent.test_coordinator import _new_run

    from guojing.application.agent.service import AgentSessionNotFound
    from guojing.domain.agent_guidance import GuidanceDecision, GuidanceStatus
    from guojing.infrastructure.persistence.models import AgentRunRecord, GuidanceStepRecord

    database, _, _ = setup(tmp_path)
    now = datetime.now(UTC)
    service = AgentService(SqlAlchemyAgentRepository(database), clock=lambda: now)
    session, token = service.create_session(
        client_session_id=uuid4(), goal="private", target_package="synthetic.app"
    )
    run = _new_run(service, session)
    service.complete_run(
        run,
        session,
        GuidanceDecision(GuidanceStatus.CANNOT_DETERMINE, "private instruction", None, 0.3),
        1,
    )
    now += timedelta(hours=24)
    with pytest.raises(AgentSessionNotFound):
        service.require_session(session.session_id, token)
    assert service.purge_expired() == [session.session_id]
    with database.new_session() as db:
        assert db.scalar(select(func.count()).select_from(AgentRunRecord)) == 0
        assert db.scalar(select(func.count()).select_from(GuidanceStepRecord)) == 0
    database.dispose()


def test_completion_constraint_failure_rolls_back_run_and_session(tmp_path: Path) -> None:
    from sqlalchemy.exc import IntegrityError
    from tests.application.agent.test_coordinator import _new_run

    from guojing.domain.agent_guidance import GuidanceDecision, GuidanceStatus

    database, _, _ = setup(tmp_path)
    service = AgentService(SqlAlchemyAgentRepository(database))
    session, _ = service.create_session(
        client_session_id=uuid4(), goal="private", target_package="synthetic.app"
    )
    first, second = _new_run(service, session), _new_run(service, session)
    decision = GuidanceDecision(GuidanceStatus.CANNOT_DETERMINE, "instruction", None, 0.3)
    service.complete_run(first, session, decision, 1)
    # Deliberately use the stale step counter: duplicate step insertion must roll back every write.
    with pytest.raises(IntegrityError):
        service.complete_run(second, session, decision, 1)
    saved = service.get_run(second.run_id)
    current = service.get_session(session.session_id)
    assert saved and saved.status.value == "queued" and saved.result is None
    assert current and current.current_step == 1
    database.dispose()
