"""Persistence ports for transient help-request result metadata."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from guojing.domain.help_requests import HelpRequestProcessingStatus, HelpRequestResult


class ClientRequestConflictError(ValueError):
    """Raised when one idempotency key is reused with different request data."""


class HelpRequestRepository(Protocol):
    """Store only bounded result metadata, never the submitted image bytes."""

    def create_or_get(
        self,
        result: HelpRequestResult,
        fingerprint: str,
        expires_at: datetime,
        now: datetime,
    ) -> HelpRequestResult:
        """Create a result or return the identical idempotent submission."""

    def get(self, request_id: UUID, now: datetime) -> HelpRequestResult | None:
        """Read one non-expired result."""

    def list(
        self,
        status: HelpRequestProcessingStatus | None,
        now: datetime,
    ) -> tuple[HelpRequestResult, ...]:
        """List non-expired results, newest first."""

    def save(self, result: HelpRequestResult, now: datetime) -> None:
        """Persist one state transition."""
