"""Authentication application-service behavior across persistence boundaries."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tests.auth_helpers import ADMIN_PASSWORD, ADMIN_USERNAME, FastPasswordHasher

from guojing.application.auth.ports import (
    InvalidAdminCredentialsError,
    InvalidAdminSessionError,
)
from guojing.application.auth.service import AdminAuthService
from guojing.infrastructure.persistence.admin_auth_repository import (
    SqlAlchemyAdminAuthRepository,
)
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import Base


@dataclass
class MutableClock:
    current: datetime

    def __call__(self) -> datetime:
        return self.current


def _service(database: Database, clock: MutableClock) -> AdminAuthService:
    token_number = 0

    def tokens() -> str:
        nonlocal token_number
        token_number += 1
        return f"test-token-{token_number:04d}-with-at-least-32-characters"

    return AdminAuthService(
        SqlAlchemyAdminAuthRepository(database),
        FastPasswordHasher(),
        session_ttl=timedelta(minutes=30),
        clock=clock,
        token_factory=tokens,
    )


def test_session_expires_at_its_fixed_deadline(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'auth.db'}")
    Base.metadata.create_all(database.engine)
    clock = MutableClock(datetime(2026, 8, 2, 9, 0, tzinfo=UTC))
    service = _service(database, clock)
    service.create_admin(ADMIN_USERNAME, ADMIN_PASSWORD)
    grant = service.login(ADMIN_USERNAME, ADMIN_PASSWORD)

    clock.current = grant.context.expires_at

    with pytest.raises(InvalidAdminSessionError):
        service.authenticate(grant.session_token)
    database.dispose()


def test_password_reset_revokes_sessions_and_changes_credentials(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'auth.db'}")
    Base.metadata.create_all(database.engine)
    clock = MutableClock(datetime(2026, 8, 2, 9, 0, tzinfo=UTC))
    service = _service(database, clock)
    service.create_admin(ADMIN_USERNAME, ADMIN_PASSWORD)
    old_session = service.login(ADMIN_USERNAME, ADMIN_PASSWORD)
    new_password = "replacement-test-password"

    service.reset_admin_password(ADMIN_USERNAME, new_password)

    with pytest.raises(InvalidAdminSessionError):
        service.authenticate(old_session.session_token)
    with pytest.raises(InvalidAdminCredentialsError):
        service.login(ADMIN_USERNAME, ADMIN_PASSWORD)
    assert service.login(ADMIN_USERNAME, new_password).context.admin.username == ADMIN_USERNAME
    database.dispose()
