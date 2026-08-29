"""Pure privacy and validation tests for evidence envelopes."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from guojing.domain.evidence import (
    EvidenceAnchor,
    EvidenceBounds,
    EvidenceEnvelope,
    EvidenceSharingPolicy,
    EvidenceSource,
)


def _envelope(
    *, policy: EvidenceSharingPolicy = EvidenceSharingPolicy.LOCAL_ONLY
) -> EvidenceEnvelope:
    captured = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    return EvidenceEnvelope(
        evidence_id=uuid4(),
        request_id=uuid4(),
        package_name="com.tencent.mm",
        version_name="8.0.60",
        version_code=8060000,
        source=EvidenceSource.OCR,
        sharing_policy=policy,
        structure_score=0.95,
        captured_at=captured,
        expires_at=captured + timedelta(minutes=10),
        anchors=(
            EvidenceAnchor(
                anchor_id="chat_tab",
                confidence=0.93,
                normalized_bounds=EvidenceBounds(0.1, 0.8, 0.3, 0.95),
            ),
        ),
    )


def test_network_guard_rejects_local_only_evidence() -> None:
    with pytest.raises(ValueError, match="local_only"):
        _envelope().require_network_allowed(datetime(2026, 8, 30, 8, 1, tzinfo=UTC))


def test_network_guard_rejects_expired_evidence() -> None:
    envelope = _envelope(policy=EvidenceSharingPolicy.SANITIZED_NETWORK_ALLOWED)

    with pytest.raises(ValueError, match="expired"):
        envelope.require_network_allowed(datetime(2026, 8, 30, 8, 11, tzinfo=UTC))


def test_duplicate_anchor_ids_are_rejected() -> None:
    envelope = _envelope()
    with pytest.raises(ValueError, match="unique"):
        replace(
            envelope,
            anchors=(envelope.anchors[0], envelope.anchors[0]),
        )
