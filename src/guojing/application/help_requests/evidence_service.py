"""Use cases for accepting privacy-safe screen evidence."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from guojing.application.help_requests.evidence_ports import HelpRequestEvidenceRepository
from guojing.application.help_requests.in_memory_evidence_repository import (
    InMemoryHelpRequestEvidenceRepository,
)
from guojing.application.help_requests.service import HelpRequestNotFound, HelpRequestService
from guojing.domain.evidence import EvidenceEnvelope


class InvalidHelpRequestEvidence(ValueError):
    """Raised when evidence violates the explicit network privacy contract."""


DEFAULT_MAX_CAPTURE_AGE = timedelta(minutes=15)
DEFAULT_MAX_FUTURE_SKEW = timedelta(seconds=30)
DEFAULT_SERVER_EVIDENCE_TTL = timedelta(minutes=10)


class HelpRequestEvidenceService:
    """Validate request ownership and privacy before persisting an envelope."""

    def __init__(
        self,
        help_request_service: HelpRequestService,
        repository: HelpRequestEvidenceRepository | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        max_capture_age: timedelta = DEFAULT_MAX_CAPTURE_AGE,
        max_future_skew: timedelta = DEFAULT_MAX_FUTURE_SKEW,
        server_ttl: timedelta = DEFAULT_SERVER_EVIDENCE_TTL,
    ) -> None:
        if max_capture_age <= timedelta(0):
            raise ValueError("max_capture_age must be positive")
        if max_future_skew < timedelta(0):
            raise ValueError("max_future_skew cannot be negative")
        if server_ttl <= max_future_skew:
            raise ValueError("server_ttl must exceed max_future_skew")
        self._help_request_service = help_request_service
        self._repository = repository or InMemoryHelpRequestEvidenceRepository()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._max_capture_age = max_capture_age
        self._max_future_skew = max_future_skew
        self._server_ttl = server_ttl

    def record(self, request_id: UUID, envelope: EvidenceEnvelope) -> EvidenceEnvelope:
        """Accept only current, network-allowed evidence belonging to the request."""
        now = self._clock().astimezone(UTC)
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
        captured_at = envelope.captured_at.astimezone(UTC)
        if captured_at < now - self._max_capture_age:
            raise InvalidHelpRequestEvidence("evidence capture time is too old")
        if captured_at > now + self._max_future_skew:
            raise InvalidHelpRequestEvidence("evidence capture time is too far in the future")
        server_expires_at = now + self._server_ttl
        effective_expires_at = min(envelope.expires_at.astimezone(UTC), server_expires_at)
        if effective_expires_at <= captured_at:
            raise InvalidHelpRequestEvidence("evidence expires before the allowed capture window")
        bounded = replace(
            envelope,
            captured_at=captured_at,
            expires_at=effective_expires_at,
        )
        return self._repository.save(bounded, now)

    def get_latest(self, request_id: UUID) -> EvidenceEnvelope | None:
        """Read the newest envelope without returning expired evidence."""
        now = self._clock().astimezone(UTC)
        try:
            self._help_request_service.get_result(request_id)
        except HelpRequestNotFound:
            return None
        return self._repository.get_latest(request_id, now)
