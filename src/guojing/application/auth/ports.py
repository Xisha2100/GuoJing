"""Ports used by administrator authentication application services."""

from datetime import datetime
from typing import Protocol

from guojing.application.auth.models import AuditEvent
from guojing.domain.auth import AdminUser, AuthenticatedAdminSession


class AdminUsernameConflictError(ValueError):
    """Raised when a normalized username already exists."""


class AdminUserNotFoundError(LookupError):
    """Raised when a CLI account-management target does not exist."""


class InvalidAdminCredentialsError(PermissionError):
    """Generic login failure that does not reveal which credential was wrong."""


class AdminLoginRateLimitedError(PermissionError):
    """Raised after too many failures for one normalized username."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("too many login attempts; try again later")


class InvalidAdminSessionError(PermissionError):
    """Raised for missing, expired, revoked, or unknown sessions."""


class InvalidCsrfTokenError(PermissionError):
    """Raised when a state-changing browser request fails CSRF verification."""


class PasswordHasher(Protocol):
    """Adaptive password hashing implementation boundary."""

    def hash(self, password: str) -> str:
        """Create an encoded, salted password hash."""

    def verify_and_update(self, password: str, encoded_hash: str) -> tuple[bool, str | None]:
        """Verify and optionally return a hash using newer parameters."""


class AdminAuthRepository(Protocol):
    """Atomic persistence operations for accounts, sessions, and security events."""

    def create_admin(
        self,
        username: str,
        password_hash: str,
        now: datetime,
    ) -> AdminUser:
        """Atomically create one active administrator and its bootstrap audit."""

    def get_admin_by_username(self, username: str) -> AdminUser | None:
        """Look up one normalized login identifier."""

    def update_password_hash(
        self,
        user_id: str,
        password_hash: str,
        now: datetime,
    ) -> None:
        """Upgrade an encoded hash after a successful login."""

    def reset_password_and_revoke_sessions(
        self,
        user_id: str,
        password_hash: str,
        now: datetime,
    ) -> None:
        """Atomically replace a hash, invalidate sessions, and append audit."""

    def count_recent_failures(self, username: str, since: datetime) -> int:
        """Count failures since the window start or most recent success."""

    def record_login_attempt(
        self,
        username: str,
        succeeded: bool,
        occurred_at: datetime,
    ) -> None:
        """Persist an attempt for restart-safe throttling."""

    def create_session(
        self,
        admin_user_id: str,
        session_token_hash: str,
        csrf_token_hash: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> AuthenticatedAdminSession:
        """Persist credential hashes and login audit in one transaction."""

    def get_active_session(
        self,
        session_token_hash: str,
        now: datetime,
    ) -> AuthenticatedAdminSession | None:
        """Resolve and touch a live session with an active administrator."""

    def revoke_session(self, session_id: str, revoked_at: datetime) -> None:
        """Atomically invalidate one server-side session and audit logout."""

    def record_audit_event(
        self,
        admin_user_id: str | None,
        action: str,
        resource_type: str,
        resource_id: str | None,
        occurred_at: datetime,
        details: dict[str, str | int | bool | None],
    ) -> AuditEvent:
        """Append a security audit event without storing secrets."""
