"""HTTP contract tests for transient screenshot help submissions."""

import base64
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import cast
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from guojing.application.help_requests.service import HelpRequestService
from guojing.domain.help_requests import HelpRequestGuidance, HelpRequestGuidanceStep


def _payload(
    image: bytes = b"\xff\xd8\xff\xd9",
    *,
    intent: str = "recorded_tutorial",
    redaction_count: int = 1,
    no_sensitive_content_confirmed: bool = False,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "client_request_id": str(uuid4()),
        "intent": intent,
        "question": "下一步应该点哪里?",
        "image_media_type": "image/jpeg",
        "image_width": 720,
        "image_height": 1_440,
        "redaction_count": redaction_count,
        "no_sensitive_content_confirmed": no_sensitive_content_confirmed,
        "sanitized_sha256": sha256(image).hexdigest(),
        "send_consent": True,
        "sanitized_image_base64": base64.b64encode(image).decode("ascii"),
    }


def test_accepts_a_locally_sanitized_image_and_returns_only_a_route_receipt(
    client: TestClient,
) -> None:
    response = client.post("/api/v1/help-requests", json=_payload())

    assert response.status_code == 202
    body = response.json()
    assert body["intent"] == "recorded_tutorial"
    assert body["processing_route"] == "tutorial_match"
    assert body["processing_status"] == "received"
    assert body["image_disposition"] == "discarded_after_validation"
    assert body["status_endpoint"] == f"/api/v1/help-requests/{body['request_id']}"
    assert body["schema_version"] == "1.2"
    assert body["access_token"]
    assert "sanitized_image_base64" not in body
    assert response.headers["cache-control"] == "no-store"

    result_response = client.get(
        body["status_endpoint"],
        headers={"X-Help-Request-Token": body["access_token"]},
    )

    assert result_response.status_code == 200
    assert result_response.json()["processing_status"] == "received"
    assert result_response.json()["guidance"] is None
    assert "sanitized_image_base64" not in result_response.json()
    assert result_response.headers["cache-control"] == "no-store"


def test_routes_general_guidance_without_claiming_that_ai_ran(client: TestClient) -> None:
    response = client.post(
        "/api/v1/help-requests",
        json=_payload(
            intent="general_guidance",
            redaction_count=0,
            no_sensitive_content_confirmed=True,
        ),
    )

    assert response.status_code == 202
    assert response.json()["processing_route"] == "general_guidance"
    assert response.json()["processing_status"] == "received"


def test_unknown_result_id_returns_not_found(client: TestClient) -> None:
    response = client.get(f"/api/v1/help-requests/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "help request was not found"


def test_result_and_evidence_require_the_request_capability(client: TestClient) -> None:
    accepted = client.post("/api/v1/help-requests", json=_payload()).json()
    request_id = accepted["request_id"]
    bad_headers = {"X-Help-Request-Token": "not-the-issued-capability"}

    result = client.get(f"/api/v1/help-requests/{request_id}", headers=bad_headers)
    evidence = client.post(
        f"/api/v1/help-requests/{request_id}/evidence",
        headers=bad_headers,
        json={
            "schema_version": "1.0",
            "evidence_id": str(uuid4()),
            "package_name": "com.tencent.mm",
            "version_name": "8.0.60",
            "version_code": 8_060_000,
            "source": "accessibility",
            "sharing_policy": "sanitized_network_allowed",
            "structure_score": 0.9,
            "captured_at": datetime.now(UTC).isoformat(),
            "expires_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
            "anchors": [{"anchor_id": "chat_tab", "confidence": 0.95}],
        },
    )

    assert result.status_code == 404
    assert evidence.status_code == 404


def test_result_endpoint_exposes_review_and_guidance_states_without_image(
    client: TestClient,
) -> None:
    response = client.post("/api/v1/help-requests", json=_payload())
    request_id = response.json()["request_id"]
    service = cast(FastAPI, client.app).state.help_request_service
    assert isinstance(service, HelpRequestService)

    service.mark_processing(UUID(request_id))
    service.mark_needs_human_review(
        UUID(request_id),
        "包含支付确认, 需要人工复核.",
    )

    access_token = response.json()["access_token"]
    review_response = client.get(
        f"/api/v1/help-requests/{request_id}",
        headers={"X-Help-Request-Token": access_token},
    )

    assert review_response.status_code == 200
    assert review_response.json()["processing_status"] == "needs_human_review"
    assert review_response.json()["human_review_reason"] == "包含支付确认, 需要人工复核."
    assert "sanitized_image_base64" not in review_response.json()

    service.publish_guidance(
        UUID(request_id),
        HelpRequestGuidance(
            title="基础指引",
            steps=(
                HelpRequestGuidanceStep(
                    step_id="manual-step",
                    title="先看标题",
                    instruction="请你亲自确认页面标题.",
                ),
            ),
        ),
    )

    ready_response = client.get(
        f"/api/v1/help-requests/{request_id}",
        headers={"X-Help-Request-Token": access_token},
    )

    assert ready_response.json()["processing_status"] == "guidance_ready"
    assert ready_response.json()["guidance"]["steps"][0]["requires_manual_action"] is True


def test_rejects_a_digest_that_does_not_match_the_image(client: TestClient) -> None:
    payload = _payload()
    payload["sanitized_sha256"] = "0" * 64

    response = client.post("/api/v1/help-requests", json=payload)

    assert response.status_code == 422
    assert "digest" in response.json()["detail"]
    assert str(payload["sanitized_image_base64"]) not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_rejects_missing_explicit_send_consent(client: TestClient) -> None:
    payload = _payload()
    payload.pop("send_consent")

    response = client.post("/api/v1/help-requests", json=payload)

    assert response.status_code == 422


def test_rejects_conflicting_privacy_metadata(client: TestClient) -> None:
    payload = _payload(redaction_count=1, no_sensitive_content_confirmed=True)

    response = client.post("/api/v1/help-requests", json=payload)

    assert response.status_code == 422


def test_rejects_non_base64_image_bytes(client: TestClient) -> None:
    payload = _payload()
    payload["sanitized_image_base64"] = "not-base64"

    response = client.post("/api/v1/help-requests", json=payload)

    assert response.status_code == 422


def test_validation_error_does_not_echo_question_or_image(client: TestClient) -> None:
    payload = _payload()
    payload["question"] = "这是不应出现在错误响应中的问题"
    payload["redaction_count"] = 1
    payload["no_sensitive_content_confirmed"] = True

    response = client.post("/api/v1/help-requests", json=payload)

    assert response.status_code == 422
    assert str(payload["question"]) not in response.text
    assert str(payload["sanitized_image_base64"]) not in response.text
    assert response.json()["detail"]["code"] == "invalid_help_request"
    assert all("input" not in issue for issue in response.json()["detail"]["issues"])
    assert response.headers["cache-control"] == "no-store"


def test_oversized_raw_body_is_rejected_before_json_parsing(client: TestClient) -> None:
    oversized = b"{" + b"x" * (12 * 1024 * 1024) + b"}"

    response = client.post(
        "/api/v1/help-requests",
        content=oversized,
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "request_body_too_large"
    assert response.headers["cache-control"] == "no-store"


def test_repeating_the_same_client_request_is_idempotent(client: TestClient) -> None:
    payload = _payload()

    first = client.post("/api/v1/help-requests", json=payload)
    second = client.post("/api/v1/help-requests", json=payload)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["request_id"] == first.json()["request_id"]


def test_reusing_a_client_request_id_for_different_data_is_rejected(client: TestClient) -> None:
    payload = _payload()
    client.post("/api/v1/help-requests", json=payload)
    payload["question"] = "这是另一件事"

    response = client.post("/api/v1/help-requests", json=payload)

    assert response.status_code == 422
    assert "reused" in response.json()["detail"]
    assert str(payload["question"]) not in response.text


def test_replayed_post_keeps_acceptance_receipt_shape_after_processing(
    client: TestClient,
) -> None:
    payload = _payload(intent="general_guidance")
    first = client.post("/api/v1/help-requests", json=payload)
    request_id = UUID(first.json()["request_id"])
    service = cast(FastAPI, client.app).state.help_request_service
    assert isinstance(service, HelpRequestService)
    service.mark_processing(request_id)
    service.publish_guidance(
        request_id,
        HelpRequestGuidance(
            title="基础指引",
            steps=(
                HelpRequestGuidanceStep(
                    step_id="one",
                    title="看标题",
                    instruction="请你亲自确认页面标题。",
                ),
            ),
        ),
    )

    replay = client.post("/api/v1/help-requests", json=payload)

    assert replay.status_code == 202
    assert replay.json()["processing_status"] == "received"
    assert replay.json()["guidance"] is None
