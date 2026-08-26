"""HTTP contract tests for transient screenshot help submissions."""

import base64
from hashlib import sha256
from uuid import uuid4

from fastapi.testclient import TestClient


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
    assert body["processing_status"] == "accepted_no_model"
    assert body["image_disposition"] == "discarded_after_validation"
    assert "sanitized_image_base64" not in body
    assert response.headers["cache-control"] == "no-store"


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
    assert response.json()["processing_status"] == "accepted_no_model"


def test_rejects_a_digest_that_does_not_match_the_image(client: TestClient) -> None:
    payload = _payload()
    payload["sanitized_sha256"] = "0" * 64

    response = client.post("/api/v1/help-requests", json=payload)

    assert response.status_code == 422
    assert "digest" in response.json()["detail"]


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
