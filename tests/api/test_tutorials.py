"""HTTP contract tests for tutorial authoring and Android reads."""

from pathlib import Path

from fastapi.testclient import TestClient
from tests.tutorial_factory import make_tutorial_graph

from guojing.application.tutorials.dto import TutorialGraphDto
from guojing.application.tutorials.service import TutorialService
from guojing.core.config import AppEnvironment, Settings
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import Base
from guojing.infrastructure.persistence.tutorial_repository import (
    SqlAlchemyTutorialRepository,
)
from guojing.main import create_app

ADMIN_TOKEN = "test-admin-token-that-is-at-least-32-characters"


def _client(tmp_path: Path, token: str | None = ADMIN_TOKEN) -> TestClient:
    database = Database(f"sqlite:///{tmp_path / 'api.db'}")
    Base.metadata.create_all(database.engine)
    settings = Settings(
        environment=AppEnvironment.TEST,
        database_url=f"sqlite:///{tmp_path / 'unused.db'}",
        admin_api_token=token,
    )
    service = TutorialService(SqlAlchemyTutorialRepository(database))
    return TestClient(create_app(settings, tutorial_service=service))


def _authorization(token: str = ADMIN_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_api_is_disabled_without_a_configured_token(tmp_path: Path) -> None:
    with _client(tmp_path, token=None) as client:
        response = client.post(
            "/api/v1/admin/tutorials/drafts",
            json=TutorialGraphDto.from_domain(make_tutorial_graph()).model_dump(mode="json"),
        )

    assert response.status_code == 503


def test_admin_api_rejects_an_invalid_token(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/admin/tutorials/drafts",
            headers=_authorization("wrong-token"),
            json=TutorialGraphDto.from_domain(make_tutorial_graph()).model_dump(mode="json"),
        )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_draft_publish_and_public_read_flow(tmp_path: Path) -> None:
    graph = make_tutorial_graph()
    payload = TutorialGraphDto.from_domain(graph).model_dump(mode="json")
    with _client(tmp_path) as client:
        draft_response = client.post(
            "/api/v1/admin/tutorials/drafts",
            headers=_authorization(),
            json=payload,
        )
        empty_catalog_response = client.get("/api/v1/tutorials")
        publish_response = client.post(
            f"/api/v1/admin/tutorials/{graph.graph_id}/revisions/1/publish",
            headers=_authorization(),
        )
        catalog_response = client.get("/api/v1/tutorials")
        tutorial_response = client.get(f"/api/v1/tutorials/{graph.graph_id}")

    assert draft_response.status_code == 201
    assert draft_response.json()["revision_number"] == 1
    assert empty_catalog_response.json() == []
    assert publish_response.status_code == 200
    assert catalog_response.json()[0]["graph_id"] == graph.graph_id
    assert tutorial_response.json()["graph"] == payload


def test_structurally_invalid_graph_returns_all_domain_issues(tmp_path: Path) -> None:
    payload = TutorialGraphDto.from_domain(make_tutorial_graph()).model_dump(mode="json")
    payload["start_node_id"] = "missing"
    payload["transitions"].append(payload["transitions"][0])
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/admin/tutorials/drafts",
            headers=_authorization(),
            json=payload,
        )

    assert response.status_code == 422
    issue_codes = {issue["code"] for issue in response.json()["detail"]}
    assert "missing_start_node" in issue_codes
    assert "duplicate_transition_id" in issue_codes


def test_unpublished_tutorial_returns_not_found(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/tutorials/unknown")

    assert response.status_code == 404
