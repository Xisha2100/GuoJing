"""Administrator login, session, CSRF, and audit workflows."""

import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import compare_digest

from guojing.application.auth.models import AdminSessionGrant, AuditEvent
from guojing.application.auth.ports import (
    AdminAuthRepository,
    AdminLoginRateLimitedError,
    AdminUserNotFoundError,
    InvalidAdminCredentialsError,
    InvalidAdminSessionError,
    InvalidCsrfTokenError,
    PasswordHasher,
)
from guojing.domain.auth import (
    AdminUser,
    AuthenticatedAdminSession,
    normalize_username,
    require_valid_password,
)

Clock = Callable[[], datetime]
TokenFactory = Callable[[], str]


class AdminAuthService:
    """Keep raw credentials at the boundary and store only irreversible hashes."""

    def __init__(
        self,
        repository: AdminAuthRepository,
        password_hasher: PasswordHasher,
        *,
        session_ttl: timedelta = timedelta(hours=8),
        login_window: timedelta = timedelta(minutes=15),
        maximum_failures: int = 5,
        clock: Clock | None = None,
        token_factory: TokenFactory | None = None,
    ) -> None:
        if session_ttl <= timedelta(0):
            raise ValueError("session_ttl must be positive")
        if login_window <= timedelta(0):
            raise ValueError("login_window must be positive")
        if maximum_failures < 1:
            raise ValueError("maximum_failures must be positive")
        self._repository = repository
        self._password_hasher = password_hasher
        self._session_ttl = session_ttl
        self._login_window = login_window
        self._maximum_failures = maximum_failures
        self._clock = clock or (lambda: datetime.now(UTC))
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._dummy_password_hash = password_hasher.hash("dummy-password-never-used-for-login")

    def create_admin(self, username: str, password: str) -> AdminUser:
        normalized = normalize_username(username)
        require_valid_password(password)
        return self._repository.create_admin(
            normalized,
            self._password_hasher.hash(password),
            self._clock(),
        )

    def reset_admin_password(self, username: str, new_password: str) -> AdminUser:
        normalized = normalize_username(username)
        require_valid_password(new_password)
        admin = self._repository.get_admin_by_username(normalized)
        if admin is None:
            raise AdminUserNotFoundError(f"administrator username {normalized!r} does not exist")
        now = self._clock()
        self._repository.reset_password_and_revoke_sessions(
            admin.user_id,
            self._password_hasher.hash(new_password),
            now,
        )
        updated = self._repository.get_admin_by_username(normalized)
        assert updated is not None
        return updated

    def login(self, username: str, password: str) -> AdminSessionGrant:
        normalized = normalize_username(username)
        now = self._clock()
        failure_count = self._repository.count_recent_failures(
            normalized,
            now - self._login_window,
        )
        if failure_count >= self._maximum_failures:
            raise AdminLoginRateLimitedError(int(self._login_window.total_seconds()))

        admin = self._repository.get_admin_by_username(normalized)
        encoded_hash = (
            admin.password_hash if admin is not None and admin.active else self._dummy_password_hash
        )
        valid, replacement_hash = self._password_hasher.verify_and_update(
            password,
            encoded_hash,
        )
        authenticated = admin is not None and admin.active and valid
        self._repository.record_login_attempt(normalized, authenticated, now)
        if not authenticated or admin is None:
            raise InvalidAdminCredentialsError("invalid username or password")

        if replacement_hash is not None:
            self._repository.update_password_hash(admin.user_id, replacement_hash, now)
        session_token = self._token_factory()
        csrf_token = self._token_factory()
        if len(session_token) < 32 or len(csrf_token) < 32:
            raise RuntimeError("token factory must provide at least 32 characters of entropy")
        if session_token == csrf_token:
            raise RuntimeError("token factory returned duplicate session and CSRF tokens")
        context = self._repository.create_session(
            admin.user_id,
            _token_hash(session_token),
            _token_hash(csrf_token),
            now,
            now + self._session_ttl,
        )
        return AdminSessionGrant(
            context=context,
            session_token=session_token,
            csrf_token=csrf_token,
        )

    def authenticate(self, session_token: str) -> AuthenticatedAdminSession:
        if not session_token:
            raise InvalidAdminSessionError("administrator session is required")
        context = self._repository.get_active_session(
            _token_hash(session_token),
            self._clock(),
        )
        if context is None:
            raise InvalidAdminSessionError("administrator session is invalid or expired")
        return context

    def require_csrf(
        self,
        context: AuthenticatedAdminSession,
        cookie_token: str,
        header_token: str,
    ) -> None:
        if (
            not cookie_token
            or not header_token
            or not compare_digest(
                cookie_token,
                header_token,
            )
        ):
            raise InvalidCsrfTokenError("CSRF cookie and header must match")
        if not compare_digest(_token_hash(header_token), context.csrf_token_hash):
            raise InvalidCsrfTokenError("CSRF token is invalid")

    def logout(self, context: AuthenticatedAdminSession) -> None:
        now = self._clock()
        self._repository.revoke_session(context.session_id, now)

    def record_action(
        self,
        context: AuthenticatedAdminSession,
        action: str,
        resource_type: str,
        resource_id: str | None,
        details: dict[str, str | int | bool | None] | None = None,
    ) -> AuditEvent:
        return self._repository.record_audit_event(
            context.admin.user_id,
            action,
            resource_type,
            resource_id,
            self._clock(),
            details or {},
        )


def _token_hash(token: str) -> str:
    """Hash a high-entropy random token for database storage."""
    return sha256(token.encode()).hexdigest()
