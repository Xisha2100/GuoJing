"""Application results for administrator authentication."""

from dataclasses import dataclass
from datetime import datetime

from guojing.domain.auth import AdminUser, AuthenticatedAdminSession


@dataclass(frozen=True, slots=True)
class AdminSessionGrant:
    """Raw secrets returned exactly once when login succeeds."""

    context: AuthenticatedAdminSession
    session_token: str
    csrf_token: str


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One security-relevant administrator action."""

    event_id: str
    admin_user_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    occurred_at: datetime
    details: dict[str, str | int | bool | None]


@dataclass(frozen=True, slots=True)
class AdminIdentity:
    """Safe account fields returned to the browser."""

    user_id: str
    username: str

    @classmethod
    def from_domain(cls, value: AdminUser) -> "AdminIdentity":
        return cls(user_id=value.user_id, username=value.username)
