"""Browser session, CSRF, throttling, and audit HTTP behavior."""

from pathlib import Path

from sqlalchemy import select
from tests.auth_helpers import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    admin_api_client,
    login_test_admin,
)
from tests.tutorial_factory import make_tutorial_graph

from guojing.application.tutorials.dto import TutorialGraphDto
from guojing.core.security import (
    ADMIN_CSRF_COOKIE,
    ADMIN_CSRF_HEADER,
    ADMIN_SESSION_COOKIE,
)
from guojing.infrastructure.persistence.models import (
    AdminAuditEventRecord,
    AdminSessionRecord,
)


def test_login_sets_scoped_cookie_and_me_uses_server_session(tmp_path: Path) -> None:
    with admin_api_client(tmp_path) as (client, _database, _auth_service):
        response = client.post(
            "/api/v1/admin/auth/login",
            json={"username": ADMIN_USERNAME.upper(), "password": ADMIN_PASSWORD},
        )
        me = client.get("/api/v1/admin/auth/me")

    assert response.status_code == 200
    assert response.json()["username"] == ADMIN_USERNAME
    set_cookie = response.headers.get_list("set-cookie")
    session_cookie = next(value for value in set_cookie if ADMIN_SESSION_COOKIE in value)
    csrf_cookie = next(value for value in set_cookie if ADMIN_CSRF_COOKIE in value)
    assert "HttpOnly" in session_cookie
    assert "SameSite=strict" in session_cookie
    assert "Path=/api/v1/admin" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "Path=/" in csrf_cookie
    assert me.status_code == 200


def test_secure_deployment_marks_both_browser_cookies_secure(tmp_path: Path) -> None:
    with admin_api_client(tmp_path, cookie_secure=True) as (client, _database, _auth_service):
        response = client.post(
            "/api/v1/admin/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )

    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 2
    assert all("Secure" in cookie for cookie in cookies)


def test_database_stores_only_session_and_csrf_hashes(tmp_path: Path) -> None:
    with admin_api_client(tmp_path) as (client, database, _auth_service):
        login_test_admin(client)
        raw_session = client.cookies.get(ADMIN_SESSION_COOKIE)
        raw_csrf = client.cookies.get(ADMIN_CSRF_COOKIE)
        with database.new_session() as session:
            record = session.scalar(select(AdminSessionRecord))

    assert record is not None
    assert raw_session not in {record.session_token_hash, record.csrf_token_hash}
    assert raw_csrf not in {record.session_token_hash, record.csrf_token_hash}
    assert len(record.session_token_hash) == 64
    assert len(record.csrf_token_hash) == 64


def test_wrong_and_unknown_credentials_have_the_same_response(tmp_path: Path) -> None:
    with admin_api_client(tmp_path) as (client, _database, _auth_service):
        wrong_password = client.post(
            "/api/v1/admin/auth/login",
            json={"username": ADMIN_USERNAME, "password": "wrong-password"},
        )
        unknown_user = client.post(
            "/api/v1/admin/auth/login",
            json={"username": "unknown-admin", "password": "wrong-password"},
        )

    assert wrong_password.status_code == 401
    assert unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()


def test_repeated_failures_are_throttled(tmp_path: Path) -> None:
    with admin_api_client(tmp_path, maximum_failures=2) as (
        client,
        _database,
        _auth_service,
    ):
        for _ in range(2):
            response = client.post(
                "/api/v1/admin/auth/login",
                json={"username": ADMIN_USERNAME, "password": "wrong-password"},
            )
            assert response.status_code == 401
        throttled = client.post(
            "/api/v1/admin/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )

    assert throttled.status_code == 429
    assert throttled.headers["retry-after"] == "900"


def test_logout_revokes_session_and_clears_cookies(tmp_path: Path) -> None:
    with admin_api_client(tmp_path) as (client, _database, _auth_service):
        headers = login_test_admin(client)
        logged_out = client.post("/api/v1/admin/auth/logout", headers=headers)
        me = client.get("/api/v1/admin/auth/me")

    assert logged_out.status_code == 204
    assert me.status_code == 401
    deleted_cookies = logged_out.headers.get_list("set-cookie")
    deleted_session = next(
        value for value in deleted_cookies if value.startswith(f'{ADMIN_SESSION_COOKIE}=""')
    )
    deleted_csrf = next(
        value for value in deleted_cookies if value.startswith(f'{ADMIN_CSRF_COOKIE}=""')
    )
    assert "Path=/api/v1/admin" in deleted_session
    assert "Path=/" in deleted_csrf


def test_tutorial_mutation_appends_actor_audit_event(tmp_path: Path) -> None:
    graph = make_tutorial_graph()
    with admin_api_client(tmp_path) as (client, database, _auth_service):
        response = client.post(
            "/api/v1/admin/tutorials/drafts",
            headers=login_test_admin(client),
            json=TutorialGraphDto.from_domain(graph).model_dump(mode="json"),
        )
        with database.new_session() as session:
            actions = session.scalars(
                select(AdminAuditEventRecord.action).order_by(AdminAuditEventRecord.occurred_at)
            ).all()

    assert response.status_code == 201
    assert "admin.login" in actions
    assert "tutorial_revision.create_requested" in actions


def test_csrf_header_must_match_cookie(tmp_path: Path) -> None:
    with admin_api_client(tmp_path) as (client, _database, _auth_service):
        login_test_admin(client)
        response = client.post(
            "/api/v1/admin/tutorials/drafts",
            headers={ADMIN_CSRF_HEADER: "wrong-csrf-token"},
            json=TutorialGraphDto.from_domain(make_tutorial_graph()).model_dump(mode="json"),
        )

    assert response.status_code == 403
