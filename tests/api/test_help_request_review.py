"""Authenticated review endpoint tests for module 19."""

from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from tests.auth_helpers import admin_api_client, login_test_admin

from guojing.api.help_request_review import (
    GuidanceRequest,
    process_help_request,
    publish_reviewed_guidance,
)
from guojing.application.auth.service import AdminAuthService
from guojing.application.help_requests.dto import HelpRequestRequest
from guojing.application.help_requests.service import HelpRequestService
from guojing.domain.auth import AuthenticatedAdminSession
from guojing.domain.help_requests import HelpRequestProcessingStatus


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
            service=service,
            auth_service=cast(AdminAuthService, FailingAuditService()),
        )

    assert service.get_result(request.request_id).processing_status is (
        HelpRequestProcessingStatus.RECEIVED
    )
