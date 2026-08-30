"""Authenticated review endpoint tests for modules 19 and 27."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.auth_helpers import admin_api_client, login_test_admin
from tests.tutorial_factory import make_tutorial_graph

from guojing.api.help_request_review import (
    GuidanceRequest,
    process_help_request,
    publish_reviewed_guidance,
)
from guojing.application.auth.service import AdminAuthService
from guojing.application.help_requests.dto import HelpRequestRequest
from guojing.application.help_requests.evidence_service import HelpRequestEvidenceService
from guojing.application.help_requests.service import HelpRequestService
from guojing.application.help_requests.workflow import HelpRequestWorkflow
from guojing.application.tutorial_drafts.service import TutorialDraftService
from guojing.application.tutorials.dto import TutorialGraphDto
from guojing.application.tutorials.service import TutorialService
from guojing.core.config import AppEnvironment, Settings
from guojing.domain.auth import AuthenticatedAdminSession
from guojing.domain.help_requests import HelpRequestProcessingStatus
from guojing.infrastructure.persistence.help_request_evidence_repository import (
    SqlAlchemyHelpRequestEvidenceRepository,
)
from guojing.infrastructure.persistence.help_request_repository import (
    SqlAlchemyHelpRequestRepository,
)
from guojing.infrastructure.persistence.tutorial_draft_repository import (
    SqlAlchemyTutorialDraftRepository,
)
from guojing.infrastructure.persistence.tutorial_repository import SqlAlchemyTutorialRepository
from guojing.main import create_app


def _payload() -> dict[str, object]:
    import base64
    from hashlib import sha256

    image = b"\xff\xd8\xff\xd9"
    return {
        "schema_version": "1.0",
        "client_request_id": "11111111-1111-4111-8111-111111111111",
        "intent": "recorded_tutorial",
        "question": "下一步应该点哪里?",
        "image_media_type": "image/jpeg",
        "image_width": 720,
        "image_height": 1440,
        "redaction_count": 1,
        "no_sensitive_content_confirmed": False,
        "sanitized_sha256": sha256(image).hexdigest(),
        "send_consent": True,
        "sanitized_image_base64": base64.b64encode(image).decode("ascii"),
    }


def _evidence_payload() -> dict[str, object]:
    captured_at = datetime.now(UTC)
    return {
        "schema_version": "1.0",
        "evidence_id": "22222222-2222-4222-8222-222222222222",
        "package_name": "com.tencent.mm",
        "version_name": "8.0.60",
        "version_code": 2_600,
        "source": "accessibility",
        "sharing_policy": "sanitized_network_allowed",
        "structure_score": 1.0,
        "captured_at": captured_at.isoformat(),
        "expires_at": (captured_at + timedelta(minutes=10)).isoformat(),
        "anchors": [
            {
                "anchor_id": "family_chat",
                "confidence": 1.0,
            },
        ],
    }


def test_review_endpoints_require_admin_session(tmp_path: Path) -> None:
    with admin_api_client(tmp_path) as (client, _database, _auth):
        response = client.get("/api/v1/admin/help-requests/reviews")

    assert response.status_code == 401


def test_reviewer_lists_and_publishes_safe_guidance(tmp_path: Path) -> None:
    with admin_api_client(tmp_path) as (client, _database, _auth):
        submit = client.post("/api/v1/help-requests", json=_payload())
        request_id = UUID(submit.json()["request_id"])
        app_service = cast(FastAPI, client.app).state.help_request_service
        app_service.mark_processing(request_id)
        app_service.mark_needs_human_review(request_id, "需要人工确认")

        headers = login_test_admin(client)
        reviews = client.get("/api/v1/admin/help-requests/reviews", headers=headers)

        assert reviews.status_code == 200
        assert reviews.json()[0]["request_id"] == str(request_id)
        assert "sanitized_image_base64" not in reviews.json()[0]

        published = client.post(
            f"/api/v1/admin/help-requests/{request_id}/guidance",
            headers=headers,
            json={
                "title": "安全基础指引",
                "steps": [
                    {
                        "step_id": "look",
                        "title": "看标题",
                        "instruction": "请你亲自确认页面顶部的标题。",
                    },
                ],
            },
        )

    assert published.status_code == 200
    assert published.json()["processing_status"] == "guidance_ready"


def test_reviewer_cannot_publish_financial_instruction(tmp_path: Path) -> None:
    with admin_api_client(tmp_path) as (client, _database, _auth):
        submit = client.post("/api/v1/help-requests", json=_payload())
        request_id = UUID(submit.json()["request_id"])
        app_service = cast(FastAPI, client.app).state.help_request_service
        app_service.mark_processing(request_id)
        app_service.mark_needs_human_review(request_id, "需复核")
        headers = login_test_admin(client)
        response = client.post(
            f"/api/v1/admin/help-requests/{request_id}/guidance",
            headers=headers,
            json={
                "title": "支付",
                "steps": [
                    {
                        "step_id": "pay",
                        "title": "确认支付",
                        "instruction": "请点击支付并输入密码。",
                    },
                ],
            },
        )

    assert response.status_code == 422


def test_admin_can_run_the_no_model_processor_end_to_end(tmp_path: Path) -> None:
    with admin_api_client(tmp_path) as (client, _database, _auth):
        submit_payload = _payload()
        submit_payload["intent"] = "general_guidance"
        submit_payload["redaction_count"] = 0
        submit_payload["no_sensitive_content_confirmed"] = True
        submit = client.post("/api/v1/help-requests", json=submit_payload)
        request_id = submit.json()["request_id"]
        headers = login_test_admin(client)

        processed = client.post(
            f"/api/v1/admin/help-requests/{request_id}/process",
            headers=headers,
        )

    assert processed.status_code == 200
    assert processed.json()["processing_status"] == "guidance_ready"
    assert len(processed.json()["guidance"]["steps"]) == 3


def test_tutorial_workflow_is_composed_and_checkpoint_survives_new_app(
    tmp_path: Path,
) -> None:
    graph = make_tutorial_graph()
    with admin_api_client(tmp_path) as (client, database, auth_service):
        headers = login_test_admin(client)
        draft = client.post(
            "/api/v1/admin/tutorials/drafts",
            headers=headers,
            json=TutorialGraphDto.from_domain(graph).model_dump(mode="json"),
        )
        published = client.post(
            f"/api/v1/admin/tutorials/{graph.graph_id}/revisions/1/publish",
            headers=headers,
        )
        submitted = client.post("/api/v1/help-requests", json=_payload())
        request_id = submitted.json()["request_id"]
        request_headers = {"X-Help-Request-Token": submitted.json()["access_token"]}
        evidence = client.post(
            f"/api/v1/help-requests/{request_id}/evidence",
            json=_evidence_payload(),
            headers=request_headers,
        )
        processed = client.post(
            f"/api/v1/admin/help-requests/{request_id}/process",
            headers=headers,
        )

        restarted_app = create_app(
            Settings(environment=AppEnvironment.TEST, database_url="sqlite:///:memory:"),
            tutorial_service=TutorialService(SqlAlchemyTutorialRepository(database)),
            tutorial_draft_service=TutorialDraftService(
                SqlAlchemyTutorialDraftRepository(database),
            ),
            admin_auth_service=auth_service,
            help_request_service=HelpRequestService(
                repository=SqlAlchemyHelpRequestRepository(database),
            ),
            help_request_evidence_service=HelpRequestEvidenceService(
                HelpRequestService(repository=SqlAlchemyHelpRequestRepository(database)),
                SqlAlchemyHelpRequestEvidenceRepository(database),
            ),
        )
        with TestClient(restarted_app) as restarted_client:
            polled = restarted_client.get(
                f"/api/v1/help-requests/{request_id}",
                headers=request_headers,
            )

    assert draft.status_code == 201
    assert published.status_code == 200
    assert submitted.status_code == 202
    assert evidence.status_code == 202
    assert processed.status_code == 200
    assert processed.json()["processing_status"] == "needs_human_review"
    assert processed.json()["workflow_stage"] == "tutorial_matched"
    assert processed.json()["tutorial_match"] == {
        "status": "matched",
        "reason": "strong_match",
        "graph_id": graph.graph_id,
        "node_id": "chat_list",
        "revision_number": 1,
    }
    assert polled.status_code == 200
    assert polled.json()["workflow_stage"] == "tutorial_matched"
    assert polled.json()["tutorial_match"] == processed.json()["tutorial_match"]
    assert "sanitized_image_base64" not in polled.json()


def test_audit_failure_does_not_publish_guidance() -> None:
    service = HelpRequestService()
    payload = _payload()

    request = service.accept(HelpRequestRequest.model_validate(payload))
    service.mark_processing(request.request_id)
    service.mark_needs_human_review(request.request_id, "需要复核")

    class FailingAuditService:
        def record_action(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("audit store unavailable")

    with pytest.raises(RuntimeError, match="audit store unavailable"):
        publish_reviewed_guidance(
            request_id=request.request_id,
            guidance=GuidanceRequest.model_validate(
                {
                    "title": "安全基础指引",
                    "steps": [
                        {
                            "step_id": "look",
                            "title": "看标题",
                            "instruction": "请你亲自确认页面顶部标题。",
                        },
                    ],
                },
            ),
            admin=cast(AuthenticatedAdminSession, object()),
            service=service,
            auth_service=cast(AdminAuthService, FailingAuditService()),
        )

    assert service.get_result(request.request_id).processing_status is (
        HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW
    )


def test_audit_failure_does_not_start_processing() -> None:
    service = HelpRequestService()
    request = service.accept(HelpRequestRequest.model_validate(_payload()))

    class FailingAuditService:
        def record_action(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("audit store unavailable")

    with pytest.raises(RuntimeError, match="audit store unavailable"):
        process_help_request(
            request_id=request.request_id,
            _admin=cast(AuthenticatedAdminSession, object()),
            workflow=cast(HelpRequestWorkflow, object()),
            auth_service=cast(AdminAuthService, FailingAuditService()),
        )

    assert service.get_result(request.request_id).processing_status is (
        HelpRequestProcessingStatus.RECEIVED
    )
