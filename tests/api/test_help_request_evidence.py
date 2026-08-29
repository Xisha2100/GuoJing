"""HTTP privacy boundary tests for semantic evidence envelopes."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from fastapi.testclient import TestClient


def _request_payload() -> dict[str, object]:
    image = b"\xff\xd8\xff\xd9"
    return {
        "schema_version": "1.0",
        "client_request_id": str(uuid4()),
        "intent": "recorded_tutorial",
        "question": "下一步应该点哪里?",
        "image_media_type": "image/jpeg",
        "image_width": 720,
        "image_height": 1_440,
        "redaction_count": 1,
        "no_sensitive_content_confirmed": False,
        "sanitized_sha256": sha256(image).hexdigest(),
        "send_consent": True,
        "sanitized_image_base64": "/9j/2Q==",
    }


def _evidence_payload(
    *,
    sharing_policy: str = "sanitized_network_allowed",
    captured_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> dict[str, object]:
    captured = captured_at or datetime.now(UTC)
    expires = expires_at or captured + timedelta(minutes=10)
    return {
        "schema_version": "1.0",
        "evidence_id": str(uuid4()),
        "package_name": "com.tencent.mm",
        "version_name": "8.0.60",
        "version_code": 8060000,
        "source": "ocr",
        "sharing_policy": sharing_policy,
        "structure_score": 0.92,
        "captured_at": captured.isoformat(),
        "expires_at": expires.isoformat(),
        "anchors": [
            {
                "anchor_id": "chat_tab",
                "confidence": 0.96,
                "normalized_bounds": {
                    "left": 0.1,
                    "top": 0.8,
                    "right": 0.3,
                    "bottom": 0.95,
                },
            },
        ],
    }


def test_accepts_sanitized_network_evidence_without_raw_text(client: TestClient) -> None:
    request = client.post("/api/v1/help-requests", json=_request_payload())
    request_id = request.json()["request_id"]

    response = client.post(
        f"/api/v1/help-requests/{request_id}/evidence",
        json=_evidence_payload(),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["request_id"] == request_id
    assert body["anchors"][0]["anchor_id"] == "chat_tab"
    assert "text" not in body
    assert "ocr_text" not in body
    assert "sanitized_image_base64" not in body

    latest = client.get(f"/api/v1/help-requests/{request_id}/evidence/latest")
    assert latest.status_code == 200
    assert latest.json()["evidence_id"] == body["evidence_id"]


def test_rejects_local_only_evidence_at_network_boundary(client: TestClient) -> None:
    request = client.post("/api/v1/help-requests", json=_request_payload())
    request_id = request.json()["request_id"]

    response = client.post(
        f"/api/v1/help-requests/{request_id}/evidence",
        json=_evidence_payload(sharing_policy="local_only"),
    )

    assert response.status_code == 422
    assert "local_only" in response.json()["detail"]


def test_rejects_raw_ocr_text_as_unknown_field(client: TestClient) -> None:
    request = client.post("/api/v1/help-requests", json=_request_payload())
    request_id = request.json()["request_id"]
    payload = _evidence_payload()
    payload["ocr_text"] = "微信"

    response = client.post(
        f"/api/v1/help-requests/{request_id}/evidence",
        json=payload,
    )

    assert response.status_code == 422


def test_rejects_expired_evidence(client: TestClient) -> None:
    request = client.post("/api/v1/help-requests", json=_request_payload())
    request_id = request.json()["request_id"]
    captured = datetime.now(UTC) - timedelta(minutes=20)

    response = client.post(
        f"/api/v1/help-requests/{request_id}/evidence",
        json=_evidence_payload(
            captured_at=captured,
            expires_at=captured + timedelta(minutes=1),
        ),
    )

    assert response.status_code == 422
    assert "expired" in response.json()["detail"]
