"""Use cases for accepting privacy-safe screen evidence."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from guojing.application.help_requests.evidence_ports import HelpRequestEvidenceRepository
from guojing.application.help_requests.in_memory_evidence_repository import (
    InMemoryHelpRequestEvidenceRepository,
)
from guojing.application.help_requests.service import HelpRequestNotFound, HelpRequestService
from guojing.domain.evidence import EvidenceEnvelope


class InvalidHelpRequestEvidence(ValueError):
    """Raised when evidence violates the explicit network privacy contract."""


class HelpRequestEvidenceService:
    """Validate request ownership and privacy before persisting an envelope."""

    def __init__(
        self,
        help_request_service: HelpRequestService,
        repository: HelpRequestEvidenceRepository | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._help_request_service = help_request_service
        self._repository = repository or InMemoryHelpRequestEvidenceRepository()
        self._clock = clock or (lambda: datetime.now(UTC))

    def record(self, request_id: UUID, envelope: EvidenceEnvelope) -> EvidenceEnvelope:
        """Accept only current, network-allowed evidence belonging to the request."""
        now = self._clock()
        if envelope.request_id != request_id:
            raise InvalidHelpRequestEvidence("evidence request_id does not match the URL")
        try:
            self._help_request_service.get_result(request_id)
        except HelpRequestNotFound as error:
            raise InvalidHelpRequestEvidence("help request result was not found") from error
        try:
            envelope.require_network_allowed(now)
        except ValueError as error:
            raise InvalidHelpRequestEvidence(str(error)) from error
        self._repository.save(envelope, now)
        return envelope

    def get_latest(self, request_id: UUID) -> EvidenceEnvelope | None:
        """Read the newest envelope without returning expired evidence."""
        return self._repository.get_latest(request_id, self._clock())
