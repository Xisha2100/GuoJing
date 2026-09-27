"""Allowlisted authorization backups: session content never enters the payload."""

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import alibabacloud_oss_v2 as oss  # type: ignore[import-untyped]
from alibabacloud_credentials import client as credential_client  # type: ignore[import-untyped]
from alibabacloud_credentials import models as credential_models
from sqlalchemy import DateTime, Table, func, select

from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.device_repository import SqlAlchemyDeviceRepository
from guojing.infrastructure.persistence.models import (
    AgentSessionRecord,
    DailyUsageRecord,
    DeviceRecord,
    InvitationRecord,
    OperationsRecord,
)

TABLES = tuple(
    cast(Table, model.__table__) for model in (DeviceRecord, InvitationRecord, DailyUsageRecord)
)


def export_authorization(database: Database) -> bytes:
    with SqlAlchemyDeviceRepository(database).transaction() as db:
        tables = {
            table.name: [dict(row) for row in db.execute(select(table)).mappings()]
            for table in TABLES
        }
        limit = db.get(OperationsRecord, "global_limit")
        payload = {
            "format": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "tables": tables,
            "global_limit": limit.value if limit else None,
        }
    return json.dumps(payload, default=_serialize, ensure_ascii=False).encode()


def _serialize(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError("unsupported backup field")


def restore_authorization(database: Database, payload: bytes) -> None:
    """Caller must hold ProcessLease. Restore only into a migrated, empty database."""
    data = json.loads(payload)
    if data.get("format") != 1 or set(data["tables"]) != {table.name for table in TABLES}:
        raise ValueError("unsupported backup")
    with SqlAlchemyDeviceRepository(database).transaction() as db:
        for table in (*TABLES, AgentSessionRecord.__table__):
            if db.scalar(select(func.count()).select_from(table)):
                raise ValueError("restore requires an empty database")
        for table in TABLES:
            for row in data["tables"][table.name]:
                if set(row) != set(table.columns.keys()):
                    raise ValueError("unexpected backup fields")
                for column in table.columns:
                    if isinstance(column.type, DateTime) and row[column.name] is not None:
                        row[column.name] = datetime.fromisoformat(row[column.name])
                db.execute(table.insert().values(**row))
        if data.get("global_limit") is not None:
            limit = int(data["global_limit"])
            if limit < 0:
                raise ValueError("invalid limit")
            db.merge(OperationsRecord(key="global_limit", value=str(limit)))
        db.merge(OperationsRecord(key="paused", value="1"))
        db.merge(OperationsRecord(key="restored_at", value=datetime.now(UTC).isoformat()))


def oss_client() -> Any:
    # Explicit ECS provider prevents accidental fallback to developer AccessKeys.
    credentials = credential_client.Client(
        credential_models.Config(
            type="ecs_ram_role",
            role_name=os.environ.get("GUOJING_OSS_ROLE_NAME"),
            enable_imds_v2=True,
            disable_imds_v1=True,
            connect_timeout=3000,
            timeout=5000,
        )
    )

    def provide() -> Any:
        value = credentials.get_credential()
        return oss.credentials.Credentials(
            value.access_key_id, value.access_key_secret, value.security_token
        )

    return oss.Client(
        oss.Config(
            region="cn-hangzhou",
            endpoint="https://oss-cn-hangzhou-internal.aliyuncs.com",
            credentials_provider=oss.credentials.CredentialsProviderFunc(provide),
            connect_timeout=5,
            readwrite_timeout=20,
            retry_max_attempts=2,
            enabled_redirect=False,
        )
    )


def upload_backup(database: Database, deployment_id: str) -> str:
    bucket = os.environ["GUOJING_OSS_BUCKET"]
    client = oss_client()
    try:
        # Versioned buckets would retain deleted sensitive authorization snapshots.
        acl = client.get_bucket_acl(oss.GetBucketAclRequest(bucket=bucket))
        if acl.acl != "private":
            raise RuntimeError("backup bucket must be private")
        version = client.get_bucket_versioning(oss.GetBucketVersioningRequest(bucket=bucket))
        if version.version_status in {"Enabled", "Suspended"}:
            raise RuntimeError("backup bucket must never have versioning enabled")
        prefix = f"guojing/{deployment_id}/authorization/"
        now = datetime.now(UTC)
        key = f"{prefix}{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid4()}.json"
        client.put_object(
            oss.PutObjectRequest(
                bucket=bucket,
                key=key,
                body=export_authorization(database),
                acl="private",
                server_side_encryption="AES256",
                content_type="application/json",
                forbid_overwrite=True,
            )
        )
        prune_backups(client, bucket, prefix, now)
        with SqlAlchemyDeviceRepository(database).transaction() as db:
            db.merge(OperationsRecord(key="backup_success_at", value=now.isoformat()))
        return key
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()


def prune_backups(client: Any, bucket: str, prefix: str, now: datetime) -> None:
    continuation = None
    while True:
        result = client.list_objects_v2(
            oss.ListObjectsV2Request(bucket=bucket, prefix=prefix, continuation_token=continuation)
        )
        for item in result.contents or []:
            modified = item.last_modified
            if modified is None:
                raise RuntimeError("OSS object lacks modification time")
            if modified.tzinfo is None:
                modified = modified.replace(tzinfo=UTC)
            if modified <= now - timedelta(hours=24):
                client.delete_object(oss.DeleteObjectRequest(bucket=bucket, key=item.key))
        if not result.is_truncated:
            break
        continuation = result.next_continuation_token


def download_backup(key: str, deployment_id: str) -> bytes:
    if not key.startswith(f"guojing/{deployment_id}/authorization/") or not key.endswith(".json"):
        raise ValueError("unexpected backup key")
    client = oss_client()
    try:
        result = client.get_object(
            oss.GetObjectRequest(bucket=os.environ["GUOJING_OSS_BUCKET"], key=key)
        )
        payload = result.body.read(8 * 1024 * 1024 + 1)
        if len(payload) > 8 * 1024 * 1024:
            raise ValueError("backup too large")
        return bytes(payload)
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()
