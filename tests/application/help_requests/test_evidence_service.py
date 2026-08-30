"""Server-owned time and parent-result boundaries for evidence envelopes."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

import pytest

from guojing.application.help_requests.dto import HelpRequestRequest
from guojing.application.help_requests.evidence_service import (
    HelpRequestEvidenceService,
    InvalidHelpRequestEvidence,
)
from guojing.application.help_requests.service import HelpRequestService
from guojing.domain.evidence import (
    EvidenceAnchor,
    EvidenceEnvelope,
    EvidenceSharingPolicy,
    EvidenceSource,
)


def _request() -> HelpRequestRequest:
    image = b"\xff\xd8\xff\xd9"
    return HelpRequestRequest(
        client_request_id=uuid4(),
        intent="recorded_tutorial",
        question="这个页面下一步怎么做?",
        image_media_type="image/jpeg",
        image_width=720,
        image_height=1_440,
        redaction_count=1,
        no_sensitive_content_confirmed=False,
        sanitized_sha256=sha256(image).hexdigest(),
        send_consent=True,
        sanitized_image_base64="/9j/2Q==",
    )


def _envelope(
    request_id: UUID,
    *,
    captured_at: datetime,
    expires_at: datetime,
) -> EvidenceEnvelope:
    return EvidenceEnvelope(
        evidence_id=uuid4(),
        request_id=request_id,
        package_name="com.tencent.mm",
        version_name="8.0.60",
        version_code=2_600,
        source=EvidenceSource.ACCESSIBILITY,
        sharing_policy=EvidenceSharingPolicy.SANITIZED_NETWORK_ALLOWED,
        structure_score=0.95,
        captured_at=captured_at,
        expires_at=expires_at,
        anchors=(EvidenceAnchor("family_chat", 0.95),),
    )


def test_server_truncates_evidence_expiry_to_its_own_ttl() -> None:
    now = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    help_service = HelpRequestService(clock=lambda: now)
    receipt = help_service.accept(_request())
    evidence_service = HelpRequestEvidenceService(
        help_service,
        clock=lambda: now,
        server_ttl=timedelta(minutes=10),
    )

    stored = evidence_service.record(
        receipt.request_id,
        _envelope(
            receipt.request_id,
            captured_at=now,
            expires_at=now + timedelta(days=1),
        ),
    )

    assert stored.expires_at == now + timedelta(minutes=10)


def test_server_rejects_evidence_with_a_future_capture_time() -> None:
    now = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    help_service = HelpRequestService(clock=lambda: now)
    receipt = help_service.accept(_request())
    evidence_service = HelpRequestEvidenceService(help_service, clock=lambda: now)

    with pytest.raises(InvalidHelpRequestEvidence, match="too far in the future"):
        evidence_service.record(
            receipt.request_id,
            _envelope(
                receipt.request_id,
                captured_at=now + timedelta(minutes=2),
                expires_at=now + timedelta(minutes=3),
            ),
        )


def test_latest_evidence_uses_server_receipt_order_not_client_capture_time() -> None:
    current = [datetime(2026, 8, 30, 8, 0, tzinfo=UTC)]
    help_service = HelpRequestService(clock=lambda: current[0])
    receipt = help_service.accept(_request())
    evidence_service = HelpRequestEvidenceService(
        help_service,
        clock=lambda: current[0],
        max_capture_age=timedelta(minutes=5),
    )
    first = _envelope(
        receipt.request_id,
        captured_at=current[0] - timedelta(seconds=10),
        expires_at=current[0] + timedelta(minutes=1),
    )
    evidence_service.record(receipt.request_id, first)

    current[0] += timedelta(seconds=1)
    second = _envelope(
        receipt.request_id,
        captured_at=current[0] - timedelta(minutes=1),
        expires_at=current[0] + timedelta(minutes=1),
    )
    evidence_service.record(receipt.request_id, second)

    latest = evidence_service.get_latest(receipt.request_id)

    assert latest is not None
    assert latest.evidence_id == second.evidence_id


def test_latest_evidence_is_hidden_when_its_parent_request_has_expired() -> None:
    current = [datetime(2026, 8, 30, 8, 0, tzinfo=UTC)]
    help_service = HelpRequestService(
        clock=lambda: current[0],
        result_ttl=timedelta(minutes=1),
    )
    receipt = help_service.accept(_request())
    evidence_service = HelpRequestEvidenceService(
        help_service,
        clock=lambda: current[0],
        server_ttl=timedelta(minutes=10),
    )
    evidence_service.record(
        receipt.request_id,
        _envelope(
            receipt.request_id,
            captured_at=current[0],
            expires_at=current[0] + timedelta(minutes=10),
        ),
    )

    current[0] += timedelta(minutes=2)

    assert evidence_service.get_latest(receipt.request_id) is None
