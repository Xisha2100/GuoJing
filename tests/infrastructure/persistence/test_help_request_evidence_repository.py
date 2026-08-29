"""SQLite round-trip tests for module 22 evidence persistence."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from guojing.application.help_requests.dto import HelpRequestRequest
from guojing.application.help_requests.evidence_service import HelpRequestEvidenceService
from guojing.application.help_requests.service import HelpRequestService
from guojing.domain.evidence import (
    EvidenceAnchor,
    EvidenceBounds,
    EvidenceEnvelope,
    EvidenceSharingPolicy,
    EvidenceSource,
)
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.help_request_evidence_repository import (
    SqlAlchemyHelpRequestEvidenceRepository,
)
from guojing.infrastructure.persistence.help_request_repository import (
    SqlAlchemyHelpRequestRepository,
)
from guojing.infrastructure.persistence.models import Base


def _request() -> HelpRequestRequest:
    image = b"\xff\xd8\xff\xd9"
    return HelpRequestRequest(
        client_request_id=uuid4(),
        intent="recorded_tutorial",
        question="当前页面是什么?",
        image_media_type="image/jpeg",
        image_width=720,
        image_height=1_440,
        redaction_count=1,
        no_sensitive_content_confirmed=False,
        sanitized_sha256=sha256(image).hexdigest(),
        send_consent=True,
        sanitized_image_base64="/9j/2Q==",
    )


def test_evidence_round_trips_and_latest_is_selected(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'evidence.db'}")
    Base.metadata.create_all(database.engine)
    now = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    help_service = HelpRequestService(
        clock=lambda: now,
        repository=SqlAlchemyHelpRequestRepository(database),
    )
    receipt = help_service.accept(_request())
    envelope = EvidenceEnvelope(
        evidence_id=uuid4(),
        request_id=receipt.request_id,
        package_name="com.tencent.mm",
        version_name="8.0.60",
        version_code=8_060_000,
        source=EvidenceSource.ACCESSIBILITY,
        sharing_policy=EvidenceSharingPolicy.SANITIZED_NETWORK_ALLOWED,
        structure_score=0.9,
        captured_at=now,
        expires_at=now + timedelta(minutes=5),
        anchors=(EvidenceAnchor("chat_tab", 0.95, EvidenceBounds(0.1, 0.8, 0.3, 0.95)),),
    )

    evidence_service = HelpRequestEvidenceService(
        help_service,
        SqlAlchemyHelpRequestEvidenceRepository(database),
        clock=lambda: now,
    )
    evidence_service.record(receipt.request_id, envelope)
    latest = HelpRequestEvidenceService(
        help_service,
        SqlAlchemyHelpRequestEvidenceRepository(database),
        clock=lambda: now + timedelta(seconds=1),
    ).get_latest(receipt.request_id)

    assert latest == envelope
    database.dispose()
