"""Fast deterministic authentication helpers for HTTP and persistence tests."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

from fastapi.testclient import TestClient

from guojing.application.auth.service import AdminAuthService
from guojing.application.tutorial_drafts.service import TutorialDraftService
from guojing.application.tutorials.service import TutorialService
from guojing.core.config import AppEnvironment, Settings
from guojing.core.security import ADMIN_CSRF_COOKIE, ADMIN_CSRF_HEADER
from guojing.infrastructure.persistence.admin_auth_repository import (
    SqlAlchemyAdminAuthRepository,
)
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import Base
from guojing.infrastructure.persistence.tutorial_draft_repository import (
    SqlAlchemyTutorialDraftRepository,
)
from guojing.infrastructure.persistence.tutorial_repository import (
    SqlAlchemyTutorialRepository,
)
from guojing.main import create_app

ADMIN_USERNAME = "test-admin"
ADMIN_PASSWORD = "correct-test-password"


class FastPasswordHasher:
    """Test double preserving one-way behavior without Argon2's intentional cost."""

    def hash(self, password: str) -> str:
        return "test-sha256$" + sha256(password.encode()).hexdigest()

    def verify_and_update(self, password: str, encoded_hash: str) -> tuple[bool, str | None]:
        return self.hash(password) == encoded_hash, None


def create_test_auth_service(
    database: Database,
    *,
    maximum_failures: int = 5,
) -> AdminAuthService:
    service = AdminAuthService(
        SqlAlchemyAdminAuthRepository(database),
        FastPasswordHasher(),
        session_ttl=timedelta(hours=1),
        maximum_failures=maximum_failures,
        clock=lambda: datetime.now(UTC),
    )
    service.create_admin(ADMIN_USERNAME, ADMIN_PASSWORD)
    return service


def login_test_admin(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/admin/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    csrf_token = client.cookies.get(ADMIN_CSRF_COOKIE)
    assert csrf_token is not None
    return {ADMIN_CSRF_HEADER: csrf_token}


@contextmanager
def admin_api_client(
    tmp_path: Path,
    *,
    maximum_failures: int = 5,
    cookie_secure: bool = False,
) -> Iterator[tuple[TestClient, Database, AdminAuthService]]:
    database = Database(f"sqlite:///{tmp_path / 'admin-api.db'}")
    Base.metadata.create_all(database.engine)
    auth_service = create_test_auth_service(
        database,
        maximum_failures=maximum_failures,
    )
    app = create_app(
        Settings(
            environment=AppEnvironment.TEST,
            database_url=f"sqlite:///{tmp_path / 'unused.db'}",
            admin_cookie_secure=cookie_secure,
        ),
        tutorial_service=TutorialService(SqlAlchemyTutorialRepository(database)),
        tutorial_draft_service=TutorialDraftService(SqlAlchemyTutorialDraftRepository(database)),
        admin_auth_service=auth_service,
    )
    with TestClient(app) as client:
        yield client, database, auth_service
    database.dispose()
