"""Repository port for expiring help-request evidence envelopes."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from guojing.domain.evidence import EvidenceEnvelope


class HelpRequestEvidenceRepository(Protocol):
    """Persist bounded evidence without coupling the application to SQLAlchemy."""

    def save(self, envelope: EvidenceEnvelope, now: datetime) -> EvidenceEnvelope:
        """Store one immutable envelope or return the matching idempotent record."""

    def get_latest(self, request_id: UUID, now: datetime) -> EvidenceEnvelope | None:
        """Return the newest non-expired envelope for a request."""
