"""Serialized SQLite transactions for admission, device ownership and quotas."""

import hmac
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from guojing.domain.device_access import (
    AccessDenied,
    DeviceIdentity,
    quota_day,
    seconds_until_reset,
)
from guojing.infrastructure.persistence.agent_repository import _as_utc
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import (
    DailyUsageRecord,
    DeviceRecord,
    InvitationRecord,
    OperationsRecord,
    RunReservationRecord,
)


class SqlAlchemyDeviceRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        with self.database.new_session() as db:
            # All writers, including the local operations CLI, share this DB lock.
            if self.database.engine.dialect.name == "sqlite":
                db.execute(text("BEGIN IMMEDIATE"))
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def invite(self, digest: str, label: str, expires_at: datetime) -> None:
        with self.transaction() as db:
            db.add(InvitationRecord(digest=digest, label=label, expires_at=expires_at))

    def activate(
        self,
        invite_digest: str,
        installation_id: UUID,
        secret_digest: str,
        now: datetime,
        expires_at: datetime,
        maximum_devices: int,
    ) -> DeviceIdentity:
        with self.transaction() as db:
            invite = db.get(InvitationRecord, invite_digest)
            if invite is None:
                raise AccessDenied("invalid_invitation", 401)
            if invite.device_id is not None:
                device = _active(db, UUID(invite.device_id), now)
                if device.installation_id != str(installation_id) or not hmac.compare_digest(
                    device.secret_digest,
                    secret_digest,
                ):
                    raise AccessDenied("invitation_already_used", 409)
                return _identity(device)
            if _as_utc(invite.expires_at) <= now:
                raise AccessDenied("invitation_expired", 403)
            if (
                db.scalar(
                    select(DeviceRecord).where(
                        DeviceRecord.installation_id == str(installation_id),
                    )
                )
                is not None
            ):
                raise AccessDenied("installation_already_registered", 409)
            active_count = (
                db.scalar(
                    select(func.count())
                    .select_from(DeviceRecord)
                    .where(
                        DeviceRecord.revoked.is_(False),
                        DeviceRecord.expires_at > now,
                    )
                )
                or 0
            )
            if active_count >= maximum_devices:
                raise AccessDenied("device_capacity_reached", 403)
            device = DeviceRecord(
                device_id=str(uuid4()),
                installation_id=str(installation_id),
                secret_digest=secret_digest,
                label=invite.label,
                revoked=False,
                created_at=now,
                expires_at=expires_at,
            )
            db.add(device)
            invite.device_id = device.device_id
            return _identity(device)

    def authenticate(self, device_id: UUID, digest: str, now: datetime) -> DeviceIdentity:
        with self.database.new_session() as db:
            device = db.get(DeviceRecord, str(device_id))
            if device is None or not hmac.compare_digest(device.secret_digest, digest):
                raise AccessDenied("invalid_device_credentials", 401)
            return _identity(_active(db, device_id, now))

    def require_active(self, device_id: UUID, now: datetime) -> None:
        with self.database.new_session() as db:
            _active(db, device_id, now)

    def reserve(
        self,
        run_id: UUID,
        device_id: UUID,
        now: datetime,
        device_limit: int,
        global_limit: int,
    ) -> None:
        with self.transaction() as db:
            device = _active(db, device_id, now)
            if _setting(db, "paused", "0") != "0":
                raise AccessDenied("service_paused", 503, 60)
            existing = db.get(RunReservationRecord, str(run_id))
            if existing is not None and existing.status in {"reserved", "started"}:
                return
            busy = db.scalar(
                select(RunReservationRecord).where(
                    RunReservationRecord.device_id == str(device_id),
                    RunReservationRecord.status.in_(["reserved", "started"]),
                )
            )
            if busy is not None:
                raise AccessDenied("device_run_in_progress", 409)
            day = quota_day(now)
            limits = [
                (
                    str(device_id),
                    device.daily_limit if device.daily_limit is not None else device_limit,
                    "device_daily_quota_exhausted",
                ),
                (
                    "global",
                    int(_setting(db, "global_limit", str(global_limit))),
                    "global_daily_quota_exhausted",
                ),
            ]
            for scope, limit, code in limits:
                usage = db.get(DailyUsageRecord, (day, scope))
                if usage is None:
                    usage = DailyUsageRecord(day=day, scope=scope, count=0)
                    db.add(usage)
                if usage.count >= limit:
                    raise AccessDenied(code, 429, seconds_until_reset(now))
                usage.count += 1
            db.merge(
                RunReservationRecord(
                    run_id=str(run_id),
                    device_id=str(device_id),
                    day=day,
                    status="reserved",
                )
            )

    def start(self, run_id: UUID, now: datetime) -> None:
        with self.transaction() as db:
            reservation = db.get(RunReservationRecord, str(run_id))
            if reservation is None or reservation.status != "reserved":
                raise AccessDenied("run_not_reserved", 409)
            _active(db, UUID(reservation.device_id), now)
            if _setting(db, "paused", "0") != "0":
                raise AccessDenied("service_paused", 503)
            reservation.status = "started"

    def finish(self, run_id: UUID) -> None:
        with self.transaction() as db:
            item = db.get(RunReservationRecord, str(run_id))
            if item is not None:
                _finish(db, item)

    def recover(self) -> None:
        with self.transaction() as db:
            for item in db.scalars(
                select(RunReservationRecord).where(
                    RunReservationRecord.status.in_(["reserved", "started"]),
                )
            ):
                _finish(db, item)

    def accepting(self) -> bool:
        with self.database.new_session() as db:
            return _setting(db, "paused", "0") == "0"


def _finish(db: Session, item: RunReservationRecord) -> None:
    if item.status == "reserved":
        for scope in (item.device_id, "global"):
            usage = db.get(DailyUsageRecord, (item.day, scope))
            if usage is not None:
                usage.count = max(0, usage.count - 1)
    item.status = "finished"


def _active(db: Session, device_id: UUID, now: datetime) -> DeviceRecord:
    device = db.get(DeviceRecord, str(device_id))
    if device is None:
        raise AccessDenied("invalid_device_credentials", 401)
    if device.revoked:
        raise AccessDenied("device_revoked")
    if _as_utc(device.expires_at) <= now:
        raise AccessDenied("device_expired")
    return device


def _identity(device: DeviceRecord) -> DeviceIdentity:
    return DeviceIdentity(
        UUID(device.device_id),
        UUID(device.installation_id),
        _as_utc(device.expires_at),
    )


def _setting(db: Session, key: str, default: str) -> str:
    item = db.get(OperationsRecord, key)
    return item.value if item is not None else default
