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
        self._envelopes: dict[UUID, tuple[EvidenceEnvelope, datetime]] = {}
        self._lock = RLock()

    def save(self, envelope: EvidenceEnvelope, now: datetime) -> EvidenceEnvelope:
        with self._lock:
            self._purge_expired(now)
            existing = self._envelopes.get(envelope.evidence_id)
            if existing is not None:
                stored, _received_at = existing
                if not _same_submission(stored, envelope):
                    raise ValueError("evidence_id cannot be reused with different content")
                return stored
            self._envelopes[envelope.evidence_id] = (envelope, now)
            if len(self._envelopes) > self._max_envelopes:
                oldest = sorted(
                    self._envelopes.items(),
                    key=lambda item: (item[1][1], str(item[0])),
                )[: len(self._envelopes) - self._max_envelopes]
                for evidence_id, _item in oldest:
                    self._envelopes.pop(evidence_id, None)
            return envelope

    def get_latest(self, request_id: UUID, now: datetime) -> EvidenceEnvelope | None:
        with self._lock:
            self._purge_expired(now)
            matching = [
                envelope
                for envelope, _received_at in self._envelopes.values()
                if envelope.request_id == request_id
            ]
            return max(
                matching,
                key=lambda item: (self._envelopes[item.evidence_id][1], str(item.evidence_id)),
                default=None,
            )

    def _purge_expired(self, now: datetime) -> None:
        for evidence_id, (envelope, _received_at) in tuple(self._envelopes.items()):
            if envelope.is_expired(now):
                del self._envelopes[evidence_id]


def _same_submission(stored: EvidenceEnvelope, incoming: EvidenceEnvelope) -> bool:
    """Compare client-owned content while allowing server TTL normalization."""
    return (
        stored.evidence_id == incoming.evidence_id
        and stored.request_id == incoming.request_id
        and stored.package_name == incoming.package_name
        and stored.version_name == incoming.version_name
        and stored.version_code == incoming.version_code
        and stored.source is incoming.source
        and stored.sharing_policy is incoming.sharing_policy
        and stored.structure_score == incoming.structure_score
        and stored.captured_at == incoming.captured_at
        and stored.anchors == incoming.anchors
        and stored.sanitized_screenshot_sha256 == incoming.sanitized_screenshot_sha256
    )
