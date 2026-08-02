"""HTTP contract tests for incremental tutorial authoring."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient
from tests.tutorial_factory import make_complete_draft_document

from guojing.application.tutorial_drafts.dto import TutorialDraftDocumentDto
from guojing.application.tutorial_drafts.service import TutorialDraftService
from guojing.application.tutorials.service import TutorialService
from guojing.core.config import AppEnvironment, Settings
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import Base
from guojing.infrastructure.persistence.tutorial_draft_repository import (
    SqlAlchemyTutorialDraftRepository,
)
from guojing.infrastructure.persistence.tutorial_repository import (
    SqlAlchemyTutorialRepository,
)
from guojing.main import create_app

ADMIN_TOKEN = "test-admin-token-that-is-at-least-32-characters"


@contextmanager
def _client(tmp_path: Path) -> Iterator[TestClient]:
    database = Database(f"sqlite:///{tmp_path / 'authoring-api.db'}")
    Base.metadata.create_all(database.engine)
    tutorial_repository = SqlAlchemyTutorialRepository(database)
    settings = Settings(
        environment=AppEnvironment.TEST,
        admin_api_token=ADMIN_TOKEN,
        database_url=f"sqlite:///{tmp_path / 'unused.db'}",
    )
    app = create_app(
        settings,
        tutorial_service=TutorialService(tutorial_repository),
        tutorial_draft_service=TutorialDraftService(SqlAlchemyTutorialDraftRepository(database)),
    )
    with TestClient(app) as client:
        yield client
    database.dispose()


def _authorization() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def test_empty_workspace_reports_completeness_issues(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        created = client.post(
            "/api/v1/admin/tutorial-drafts",
            headers=_authorization(),
            json={},
        )
        workspace_id = created.json()["workspace_id"]
        validated = client.post(
            f"/api/v1/admin/tutorial-drafts/{workspace_id}/validate",
            headers=_authorization(),
        )
        listed = client.get(
            "/api/v1/admin/tutorial-drafts",
            headers=_authorization(),
        )

    assert created.status_code == 201
    assert created.json()["version"] == 1
    assert validated.status_code == 200
    assert validated.json()["ready"] is False
    assert listed.json()[0]["workspace_id"] == workspace_id
    assert "document" not in listed.json()[0]
    assert {issue["code"] for issue in validated.json()["issues"]} >= {
        "missing_graph_id",
        "no_nodes",
    }


def test_stale_editor_update_returns_a_version_conflict(tmp_path: Path) -> None:
    document = TutorialDraftDocumentDto.from_domain(make_complete_draft_document()).model_dump(
        mode="json"
    )
    with _client(tmp_path) as client:
        created = client.post(
            "/api/v1/admin/tutorial-drafts",
            headers=_authorization(),
            json={},
        ).json()
        first_update = client.put(
            f"/api/v1/admin/tutorial-drafts/{created['workspace_id']}",
            headers=_authorization(),
            json={"expected_version": 1, "document": document},
        )
        stale_update = client.put(
            f"/api/v1/admin/tutorial-drafts/{created['workspace_id']}",
            headers=_authorization(),
            json={"expected_version": 1, "document": document},
        )

    assert first_update.status_code == 200
    assert first_update.json()["version"] == 2
    assert stale_update.status_code == 409
    assert stale_update.json()["detail"]["current_version"] == 2


def test_promoting_valid_workspace_creates_unpublished_revision(tmp_path: Path) -> None:
    document = TutorialDraftDocumentDto.from_domain(make_complete_draft_document()).model_dump(
        mode="json"
    )
    with _client(tmp_path) as client:
        created = client.post(
            "/api/v1/admin/tutorial-drafts",
            headers=_authorization(),
            json={"document": document},
        ).json()
        promoted = client.post(
            f"/api/v1/admin/tutorial-drafts/{created['workspace_id']}/promote",
            headers=_authorization(),
            json={"expected_version": 1},
        )
        public_catalog = client.get("/api/v1/tutorials")

    assert promoted.status_code == 200
    assert promoted.json()["revision_number"] == 1
    assert promoted.json()["workspace"]["version"] == 2
    assert public_catalog.json() == []


def test_incomplete_workspace_cannot_be_promoted(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        created = client.post(
            "/api/v1/admin/tutorial-drafts",
            headers=_authorization(),
            json={},
        ).json()
        response = client.post(
            f"/api/v1/admin/tutorial-drafts/{created['workspace_id']}/promote",
            headers=_authorization(),
            json={"expected_version": 1},
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["code"] == "missing_graph_id"


def test_complete_but_structurally_invalid_workspace_reports_graph_issues(
    tmp_path: Path,
) -> None:
    document = TutorialDraftDocumentDto.from_domain(make_complete_draft_document()).model_dump(
        mode="json"
    )
    document["graph"]["start_node_id"] = "unknown"
    with _client(tmp_path) as client:
        created = client.post(
            "/api/v1/admin/tutorial-drafts",
            headers=_authorization(),
            json={"document": document},
        ).json()
        response = client.post(
            f"/api/v1/admin/tutorial-drafts/{created['workspace_id']}/validate",
            headers=_authorization(),
        )

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["issues"][0]["code"] == "missing_start_node"
    assert response.json()["issues"][0]["path"] is None
