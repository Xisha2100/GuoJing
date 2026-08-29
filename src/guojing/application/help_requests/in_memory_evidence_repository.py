"""In-memory evidence repository used by unit tests and local composition."""

from datetime import datetime
from threading import RLock
from uuid import UUID

from guojing.application.help_requests.evidence_ports import HelpRequestEvidenceRepository
from guojing.domain.evidence import EvidenceEnvelope


class InMemoryHelpRequestEvidenceRepository(HelpRequestEvidenceRepository):
    """Bounded store that applies the same expiry rules as the SQL adapter."""

    def __init__(self, *, max_envelopes: int = 1_000) -> None:
        if max_envelopes < 1:
            raise ValueError("max_envelopes must be positive")
        self._max_envelopes = max_envelopes
        self._envelopes: dict[UUID, EvidenceEnvelope] = {}
        self._lock = RLock()

    def save(self, envelope: EvidenceEnvelope, now: datetime) -> None:
        with self._lock:
            self._purge_expired(now)
            self._envelopes[envelope.evidence_id] = envelope
            if len(self._envelopes) > self._max_envelopes:
                oldest = sorted(
                    self._envelopes.values(),
                    key=lambda item: item.captured_at,
                )[: len(self._envelopes) - self._max_envelopes]
                for item in oldest:
                    self._envelopes.pop(item.evidence_id, None)

    def get_latest(self, request_id: UUID, now: datetime) -> EvidenceEnvelope | None:
        with self._lock:
            self._purge_expired(now)
            matching = [
                envelope
                for envelope in self._envelopes.values()
                if envelope.request_id == request_id
            ]
            return max(matching, key=lambda item: item.captured_at, default=None)

    def _purge_expired(self, now: datetime) -> None:
        for evidence_id, envelope in tuple(self._envelopes.items()):
            if envelope.is_expired(now):
                del self._envelopes[evidence_id]
