"""HTTP contract tests for tutorial authoring and Android reads."""

from dataclasses import replace
from pathlib import Path

from tests.auth_helpers import admin_api_client, login_test_admin
from tests.tutorial_factory import make_tutorial_graph

from guojing.application.tutorials.dto import TutorialGraphDto
from guojing.domain.tutorials.models import RiskLevel, VerificationStatus


def test_admin_write_requires_a_login(tmp_path: Path) -> None:
    with admin_api_client(tmp_path) as (client, _database, _auth_service):
        response = client.post(
            "/api/v1/admin/tutorials/drafts",
            json=TutorialGraphDto.from_domain(make_tutorial_graph()).model_dump(mode="json"),
        )

    assert response.status_code == 401


def test_admin_write_rejects_missing_csrf_header(tmp_path: Path) -> None:
    with admin_api_client(tmp_path) as (client, _database, _auth_service):
        login_test_admin(client)
        response = client.post(
            "/api/v1/admin/tutorials/drafts",
            json=TutorialGraphDto.from_domain(make_tutorial_graph()).model_dump(mode="json"),
        )

    assert response.status_code == 403


def test_draft_publish_and_public_read_flow(tmp_path: Path) -> None:
    graph = make_tutorial_graph()
    payload = TutorialGraphDto.from_domain(graph).model_dump(mode="json")
    with admin_api_client(tmp_path) as (client, _database, _auth_service):
        csrf_headers = login_test_admin(client)
        draft_response = client.post(
            "/api/v1/admin/tutorials/drafts",
            headers=csrf_headers,
            json=payload,
        )
        empty_catalog_response = client.get("/api/v1/tutorials")
        publish_response = client.post(
            f"/api/v1/admin/tutorials/{graph.graph_id}/revisions/1/publish",
            headers=csrf_headers,
        )
        catalog_response = client.get("/api/v1/tutorials")
        tutorial_response = client.get(f"/api/v1/tutorials/{graph.graph_id}")

    assert draft_response.status_code == 201
    assert draft_response.json()["revision_number"] == 1
    assert empty_catalog_response.json() == []
    assert publish_response.status_code == 200
    assert catalog_response.json()[0]["graph_id"] == graph.graph_id
    assert tutorial_response.json()["graph"] == payload


def test_publish_rejects_revision_that_is_not_release_ready(tmp_path: Path) -> None:
    graph = make_tutorial_graph()
    unsafe = replace(
        graph,
        nodes=(
            replace(graph.nodes[0], verification_status=VerificationStatus.PROVISIONAL),
            *graph.nodes[1:],
        ),
        transitions=(replace(graph.transitions[0], risk_level=RiskLevel.SENSITIVE),),
    )
    with admin_api_client(tmp_path) as (client, _database, _auth_service):
        headers = login_test_admin(client)
        draft_response = client.post(
            "/api/v1/admin/tutorials/drafts",
            headers=headers,
            json=TutorialGraphDto.from_domain(unsafe).model_dump(mode="json"),
        )
        publish_response = client.post(
            f"/api/v1/admin/tutorials/{unsafe.graph_id}/revisions/1/publish",
            headers=headers,
        )

    assert draft_response.status_code == 201
    assert publish_response.status_code == 422
    assert "release-ready" in publish_response.json()["detail"]


def test_structurally_invalid_graph_returns_all_domain_issues(tmp_path: Path) -> None:
    payload = TutorialGraphDto.from_domain(make_tutorial_graph()).model_dump(mode="json")
    payload["start_node_id"] = "missing"
    payload["transitions"].append(payload["transitions"][0])
    with admin_api_client(tmp_path) as (client, _database, _auth_service):
        response = client.post(
            "/api/v1/admin/tutorials/drafts",
            headers=login_test_admin(client),
            json=payload,
        )

    assert response.status_code == 422
    issue_codes = {issue["code"] for issue in response.json()["detail"]}
    assert "missing_start_node" in issue_codes
    assert "duplicate_transition_id" in issue_codes


def test_unpublished_tutorial_returns_not_found(tmp_path: Path) -> None:
    with admin_api_client(tmp_path) as (client, _database, _auth_service):
        response = client.get("/api/v1/tutorials/unknown")

    assert response.status_code == 404
