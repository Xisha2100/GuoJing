"""Server-only invitation, admission and recovery commands."""

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select

from guojing.application.device_access import DeviceAccessService
from guojing.core.config import Settings
from guojing.domain.device_access import quota_day
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.device_repository import SqlAlchemyDeviceRepository
from guojing.infrastructure.persistence.models import (
    DailyUsageRecord,
    DeviceRecord,
    OperationsRecord,
    RunReservationRecord,
)
from guojing.infrastructure.runtime import ProcessLease
from guojing.operations.backup import (
    download_backup,
    export_authorization,
    oss_client,
    prune_backups,
    restore_authorization,
    upload_backup,
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("invite").add_argument("--label", required=True)
    commands.add_parser("devices")
    commands.add_parser("usage")
    commands.add_parser("revoke").add_argument("device_id", type=UUID)
    limit = commands.add_parser("limit")
    limit.add_argument("scope", help="device UUID or global")
    limit.add_argument("count", type=int)
    commands.add_parser("pause")
    resume = commands.add_parser("resume")
    resume.add_argument(
        "--reconciled", action="store_true", help="confirm restored authorization and usage checked"
    )
    commands.add_parser("drain").add_argument("--timeout", type=int, default=125)
    commands.add_parser("backup")
    commands.add_parser("prune-backups")
    commands.add_parser("export").add_argument("path", type=Path)
    restore = commands.add_parser("restore")
    source = restore.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path)
    source.add_argument("--oss-key")
    commands.add_parser("monitor")
    return root


def main() -> None:
    args = parser().parse_args()
    settings = Settings()
    database = Database(settings.database_url)
    repository = SqlAlchemyDeviceRepository(database)
    try:
        if args.command == "invite":
            if not 1 <= len(args.label) <= 120:
                raise ValueError("label must be 1..120 characters")
            print(DeviceAccessService(repository).invite(args.label))
        elif args.command == "devices":
            with database.new_session() as db:
                print(
                    json.dumps(
                        [
                            {
                                "device_id": d.device_id,
                                "label": d.label,
                                "revoked": d.revoked,
                                "expires_at": d.expires_at.isoformat(),
                                "daily_limit": d.daily_limit,
                            }
                            for d in db.scalars(select(DeviceRecord))
                        ],
                        ensure_ascii=False,
                    )
                )
        elif args.command == "usage":
            with database.new_session() as db:
                print(
                    json.dumps(
                        {
                            u.scope: u.count
                            for u in db.scalars(
                                select(DailyUsageRecord).where(
                                    DailyUsageRecord.day == quota_day(datetime.now(UTC))
                                )
                            )
                        }
                    )
                )
        elif args.command in {"pause", "resume", "drain", "revoke", "limit"}:
            with repository.transaction() as db:
                if args.command == "revoke":
                    device = db.get(DeviceRecord, str(args.device_id))
                    if device is None:
                        raise ValueError("device not found")
                    device.revoked = True
                elif args.command == "limit":
                    if args.count < 0:
                        raise ValueError("limit must be non-negative")
                    if args.scope == "global":
                        db.merge(OperationsRecord(key="global_limit", value=str(args.count)))
                    else:
                        device = db.get(DeviceRecord, str(UUID(args.scope)))
                        if device is None:
                            raise ValueError("device not found")
                        device.daily_limit = args.count
                else:
                    if args.command == "resume" and db.get(OperationsRecord, "restored_at"):
                        if not args.reconciled:
                            raise ValueError("restored database requires resume --reconciled")
                        db.delete(db.get(OperationsRecord, "restored_at"))
                    db.merge(
                        OperationsRecord(
                            key="paused", value="0" if args.command == "resume" else "1"
                        )
                    )
            if args.command == "drain":
                deadline = time.monotonic() + args.timeout
                while True:
                    with database.new_session() as db:
                        unfinished = db.scalar(
                            select(func.count())
                            .select_from(RunReservationRecord)
                            .where(RunReservationRecord.status.in_(["reserved", "started"]))
                        )
                    if not unfinished:
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError("drain timed out; admission remains paused")
                    time.sleep(1)
            print("ok")
        elif args.command == "backup":
            print(upload_backup(database, settings.deployment_id))
        elif args.command == "prune-backups":
            prune_backups(
                oss_client(),
                os.environ["GUOJING_OSS_BUCKET"],
                f"guojing/{settings.deployment_id}/authorization/",
                datetime.now(UTC),
            )
        elif args.command == "export":
            descriptor = os.open(args.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as file:
                file.write(export_authorization(database))
        elif args.command == "restore":
            lease = ProcessLease(settings.database_url)
            lease.acquire()
            try:
                payload = (
                    args.file.read_bytes()
                    if args.file
                    else download_backup(args.oss_key, settings.deployment_id)
                )
                restore_authorization(database, payload)
            finally:
                lease.release()
            print("restored; admission paused until resume --reconciled")
        elif args.command == "monitor":
            from guojing.operations.monitor import monitor

            monitor(database)
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
