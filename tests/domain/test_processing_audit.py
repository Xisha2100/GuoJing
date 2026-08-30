from datetime import UTC, datetime
from uuid import uuid4

import pytest

from guojing.domain.processing_audit import ProcessingAuditEvent


def test_audit_event_accepts_only_operational_metadata() -> None:
    event = ProcessingAuditEvent(uuid4(), "worker-a", "lease_acquired", datetime.now(UTC), 1)
    assert event.action == "lease_acquired"

    with pytest.raises(ValueError, match="action"):
        ProcessingAuditEvent(uuid4(), "worker-a", "uploaded screenshot bytes", datetime.now(UTC), 1)
