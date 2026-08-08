"""Framework-independent administrator identity and session values."""

from dataclasses import dataclass
from datetime import datetime
from re import fullmatch

_USERNAME_PATTERN = r"[a-z0-9][a-z0-9._-]{2,63}"
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256


def normalize_username(value: str) -> str:
    """Normalize an administrator login identifier to one canonical form."""
    normalized = value.strip().casefold()
    if fullmatch(_USERNAME_PATTERN, normalized) is None:
        raise ValueError(
            "username must be 3-64 characters using lowercase letters, numbers, '.', '_' or '-'"
        )
    return normalized


def require_valid_password(password: str) -> None:
    """Apply length and non-blank policy without silently modifying a password."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must contain at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"password must contain at most {MAX_PASSWORD_LENGTH} characters")
    if not password.strip():
        raise ValueError("password must not be blank")


@dataclass(frozen=True, slots=True)
class AdminUser:
    """One administrator account with an irreversible password hash."""

    user_id: str
    username: str
    password_hash: str
    active: bool
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.user_id.strip():
            raise ValueError("user_id must not be blank")
        if self.username != normalize_username(self.username):
            raise ValueError("username must already be normalized")
        if not self.password_hash.strip():
            raise ValueError("password_hash must not be blank")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("admin timestamps must include a timezone")


@dataclass(frozen=True, slots=True)
class AuthenticatedAdminSession:
    """Server-side session context; it never contains the raw browser token."""

    session_id: str
    admin: AdminUser
    csrf_token_hash: str
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id must not be blank")
        if fullmatch(r"[0-9a-f]{64}", self.csrf_token_hash) is None:
            raise ValueError("csrf_token_hash must be a SHA-256 hex digest")
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("session timestamps must include a timezone")
        if self.expires_at <= self.created_at:
            raise ValueError("session must expire after it is created")
