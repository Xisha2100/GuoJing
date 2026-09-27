import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from guojing.application.device_access import DeviceAccessService
from guojing.domain.device_access import AccessDenied
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.device_repository import SqlAlchemyDeviceRepository
from guojing.infrastructure.persistence.models import Base, DailyUsageRecord, DeviceRecord


def setup(
    tmp_path: Path, limit: int = 50
) -> tuple[Database, SqlAlchemyDeviceRepository, DeviceAccessService]:
    db = Database(f"sqlite:///{tmp_path / 'access.db'}")
    Base.metadata.create_all(db.engine)
    repo = SqlAlchemyDeviceRepository(db)
    return db, repo, DeviceAccessService(repo, device_limit=limit, global_limit=limit)


def activate(service: DeviceAccessService) -> tuple[UUID, str]:
    secret = secrets.token_urlsafe(32)
    device = service.activate(service.invite("tester"), uuid4(), secret)
    return device.device_id, f"Bearer {device.device_id}.{secret}"


def test_activation_is_idempotent_but_cannot_be_reused_by_another_installation(
    tmp_path: Path,
) -> None:
    db, _, service = setup(tmp_path)
    code, install, secret = service.invite("tester"), uuid4(), secrets.token_urlsafe(32)
    first = service.activate(code, install, secret)
    assert service.activate(code, install, secret) == first
    with pytest.raises(AccessDenied, match="invitation_already_used"):
        service.activate(code, uuid4(), secret)
    with db.new_session() as session:
        saved = session.get(DeviceRecord, str(first.device_id))
        assert saved and secret not in saved.secret_digest
    db.dispose()


def test_expired_invitation_and_revoked_device_fail_closed(tmp_path: Path) -> None:
    db, repo, _ = setup(tmp_path)
    now = datetime(2026, 9, 27, tzinfo=UTC)
    service = DeviceAccessService(repo, clock=lambda: now)
    code = service.invite("tester")
    device_id, token = activate(service)
    now += timedelta(days=8)
    with pytest.raises(AccessDenied, match="invitation_expired"):
        service.activate(code, uuid4(), secrets.token_urlsafe(32))
    with repo.transaction() as session:
        device = session.get(DeviceRecord, str(device_id))
        assert device
        device.revoked = True
    with pytest.raises(AccessDenied, match="device_revoked"):
        service.authenticate(token)
    db.dispose()


def test_reservation_refunds_only_before_model_and_retry_charges_again(tmp_path: Path) -> None:
    db, _, service = setup(tmp_path, limit=2)
    device, _ = activate(service)
    run = uuid4()
    service.reserve(run, device)
    service.reserve(run, device)
    service.finish(run)
    service.reserve(run, device)
    service.start(run)
    service.finish(run)
    service.reserve(run, device)
    service.start(run)
    service.finish(run)
    with pytest.raises(AccessDenied, match="device_daily_quota_exhausted"):
        service.reserve(uuid4(), device)
    with db.new_session() as session:
        assert {item.count for item in session.scalars(select(DailyUsageRecord))} == {2}
    db.dispose()


def test_global_quota_cannot_be_exceeded_by_concurrent_devices(tmp_path: Path) -> None:
    db, _, service = setup(tmp_path, limit=3)
    devices = [activate(service)[0] for _ in range(10)]

    def reserve(device: UUID) -> bool:
        try:
            service.reserve(uuid4(), device)
            return True
        except AccessDenied:
            return False

    with ThreadPoolExecutor(max_workers=10) as pool:
        assert sum(pool.map(reserve, devices)) == 3
    db.dispose()


def test_one_pending_run_per_device_and_beijing_midnight_reset(tmp_path: Path) -> None:
    db, repo, _ = setup(tmp_path)
    now = datetime(2026, 9, 27, 15, 59, 59, tzinfo=UTC)
    service = DeviceAccessService(repo, device_limit=1, global_limit=1, clock=lambda: now)
    device, _ = activate(service)
    run = uuid4()
    service.reserve(run, device)
    with pytest.raises(AccessDenied, match="device_run_in_progress"):
        service.reserve(uuid4(), device)
    service.start(run)
    service.finish(run)
    now += timedelta(seconds=2)
    service.reserve(uuid4(), device)
    assert service.accepting()
    db.dispose()


def test_restart_refunds_reserved_but_preserves_started_charges(tmp_path: Path) -> None:
    db, repo, service = setup(tmp_path)
    first, _ = activate(service)
    second, _ = activate(service)
    run1, run2 = uuid4(), uuid4()
    service.reserve(run1, first)
    service.reserve(run2, second)
    service.start(run1)
    repo.recover()
    with db.new_session() as session:
        global_count = next(
            item.count
            for item in session.scalars(select(DailyUsageRecord))
            if item.scope == "global"
        )
        assert global_count == 1
    service.reserve(uuid4(), first)
    db.dispose()
