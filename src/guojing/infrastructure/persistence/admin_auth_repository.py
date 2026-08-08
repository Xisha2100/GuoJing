"""SQLAlchemy persistence for administrator accounts, sessions, and audit."""

import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from guojing.application.auth.models import AuditEvent
from guojing.application.auth.ports import AdminUsernameConflictError
from guojing.domain.auth import AdminUser, AuthenticatedAdminSession
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import (
    AdminAuditEventRecord,
    AdminLoginAttemptRecord,
    AdminSessionRecord,
    AdminUserRecord,
)
from guojing.infrastructure.persistence.tutorial_storage import as_utc


class SqlAlchemyAdminAuthRepository:
    """Keep raw passwords and browser tokens outside persistent storage."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create_admin(
        self,
        username: str,
        password_hash: str,
        now: datetime,
    ) -> AdminUser:
        record = AdminUserRecord(
            user_id=str(uuid4()),
            username=username,
            password_hash=password_hash,
            active=True,
            created_at=now,
            updated_at=now,
        )
        try:
            with self._database.new_session() as session, session.begin():
                session.add(record)
                session.add(
                    _audit_record(
                        admin_user_id=None,
                        action="admin.created_by_cli",
                        resource_type="admin_user",
                        resource_id=record.user_id,
                        occurred_at=now,
                        details={"username": username},
                    )
                )
        except IntegrityError as error:
            raise AdminUsernameConflictError(
                f"administrator username {username!r} already exists"
            ) from error
        return _to_admin(record)

    def get_admin_by_username(self, username: str) -> AdminUser | None:
        with self._database.new_session() as session:
            record = session.scalar(
                select(AdminUserRecord).where(AdminUserRecord.username == username)
            )
        return _to_admin(record) if record is not None else None

    def update_password_hash(
        self,
        user_id: str,
        password_hash: str,
        now: datetime,
    ) -> None:
        with self._database.new_session() as session, session.begin():
            session.execute(
                update(AdminUserRecord)
                .where(AdminUserRecord.user_id == user_id)
                .values(password_hash=password_hash, updated_at=now)
            )

    def reset_password_and_revoke_sessions(
        self,
        user_id: str,
        password_hash: str,
        now: datetime,
    ) -> None:
        with self._database.new_session() as session, session.begin():
            admin = session.get(AdminUserRecord, user_id)
            if admin is None:
                raise ValueError("administrator does not exist")
            session.execute(
                update(AdminUserRecord)
                .where(AdminUserRecord.user_id == user_id)
                .values(password_hash=password_hash, updated_at=now)
            )
            session.execute(
                update(AdminSessionRecord)
                .where(
                    AdminSessionRecord.admin_user_id == user_id,
                    AdminSessionRecord.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            session.add(
                _audit_record(
                    admin_user_id=None,
                    action="admin.password_reset_by_cli",
                    resource_type="admin_user",
                    resource_id=user_id,
                    occurred_at=now,
                    details={"username": admin.username},
                )
            )

    def count_recent_failures(self, username: str, since: datetime) -> int:
        with self._database.new_session() as session:
            latest_success = session.scalar(
                select(func.max(AdminLoginAttemptRecord.occurred_at)).where(
                    AdminLoginAttemptRecord.username == username,
                    AdminLoginAttemptRecord.succeeded.is_(True),
                    AdminLoginAttemptRecord.occurred_at >= since,
                )
            )
            threshold = max(since, as_utc(latest_success)) if latest_success else since
            count = session.scalar(
                select(func.count(AdminLoginAttemptRecord.attempt_id)).where(
                    AdminLoginAttemptRecord.username == username,
                    AdminLoginAttemptRecord.succeeded.is_(False),
                    AdminLoginAttemptRecord.occurred_at >= threshold,
                )
            )
        return count or 0

    def record_login_attempt(
        self,
        username: str,
        succeeded: bool,
        occurred_at: datetime,
    ) -> None:
        with self._database.new_session() as session, session.begin():
            session.add(
                AdminLoginAttemptRecord(
                    attempt_id=str(uuid4()),
                    username=username,
                    succeeded=succeeded,
                    occurred_at=occurred_at,
                )
            )

    def create_session(
        self,
        admin_user_id: str,
        session_token_hash: str,
        csrf_token_hash: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> AuthenticatedAdminSession:
        record = AdminSessionRecord(
            session_id=str(uuid4()),
            admin_user_id=admin_user_id,
            session_token_hash=session_token_hash,
            csrf_token_hash=csrf_token_hash,
            created_at=created_at,
            last_seen_at=created_at,
            expires_at=expires_at,
            revoked_at=None,
        )
        with self._database.new_session() as session, session.begin():
            admin = session.get(AdminUserRecord, admin_user_id)
            if admin is None or not admin.active:
                raise ValueError("cannot create a session for an inactive administrator")
            session.add(record)
            session.add(
                _audit_record(
                    admin_user_id=admin_user_id,
                    action="admin.login",
                    resource_type="admin_session",
                    resource_id=record.session_id,
                    occurred_at=created_at,
                    details={},
                )
            )
            admin_value = _to_admin(admin)
        return _to_session(record, admin_value)

    def get_active_session(
        self,
        session_token_hash: str,
        now: datetime,
    ) -> AuthenticatedAdminSession | None:
        statement = (
            select(AdminSessionRecord, AdminUserRecord)
            .join(
                AdminUserRecord,
                AdminUserRecord.user_id == AdminSessionRecord.admin_user_id,
            )
            .where(
                AdminSessionRecord.session_token_hash == session_token_hash,
                AdminSessionRecord.revoked_at.is_(None),
                AdminSessionRecord.expires_at > now,
                AdminUserRecord.active.is_(True),
            )
        )
        with self._database.new_session() as session, session.begin():
            row = session.execute(statement).one_or_none()
            if row is None:
                return None
            session_record, admin_record = row
            session_record.last_seen_at = now
            return _to_session(session_record, _to_admin(admin_record))

    def revoke_session(self, session_id: str, revoked_at: datetime) -> None:
        with self._database.new_session() as session, session.begin():
            record = session.get(AdminSessionRecord, session_id)
            if record is None or record.revoked_at is not None:
                return
            session.execute(
                update(AdminSessionRecord)
                .where(
                    AdminSessionRecord.session_id == session_id,
                    AdminSessionRecord.revoked_at.is_(None),
                )
                .values(revoked_at=revoked_at)
            )
            session.add(
                _audit_record(
                    admin_user_id=record.admin_user_id,
                    action="admin.logout",
                    resource_type="admin_session",
                    resource_id=session_id,
                    occurred_at=revoked_at,
                    details={},
                )
            )

    def record_audit_event(
        self,
        admin_user_id: str | None,
        action: str,
        resource_type: str,
        resource_id: str | None,
        occurred_at: datetime,
        details: dict[str, str | int | bool | None],
    ) -> AuditEvent:
        record = _audit_record(
            admin_user_id=admin_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            occurred_at=occurred_at,
            details=details,
        )
        with self._database.new_session() as session, session.begin():
            session.add(record)
        return AuditEvent(
            event_id=record.event_id,
            admin_user_id=admin_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            occurred_at=occurred_at,
            details=details,
        )


def _to_admin(record: AdminUserRecord) -> AdminUser:
    return AdminUser(
        user_id=record.user_id,
        username=record.username,
        password_hash=record.password_hash,
        active=record.active,
        created_at=as_utc(record.created_at),
        updated_at=as_utc(record.updated_at),
    )


def _audit_record(
    *,
    admin_user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    occurred_at: datetime,
    details: dict[str, str | int | bool | None],
) -> AdminAuditEventRecord:
    return AdminAuditEventRecord(
        event_id=str(uuid4()),
        admin_user_id=admin_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        occurred_at=occurred_at,
        details_json=json.dumps(
            details,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
    )


def _to_session(
    record: AdminSessionRecord,
    admin: AdminUser,
) -> AuthenticatedAdminSession:
    return AuthenticatedAdminSession(
        session_id=record.session_id,
        admin=admin,
        csrf_token_hash=record.csrf_token_hash,
        created_at=as_utc(record.created_at),
        expires_at=as_utc(record.expires_at),
    )
