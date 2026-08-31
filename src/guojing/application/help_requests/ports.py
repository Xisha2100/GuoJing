"""Persistence ports for transient help-request result metadata."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from guojing.domain.help_requests import HelpRequestProcessingStatus, HelpRequestResult


class ClientRequestConflictError(ValueError):
    """Raised when one idempotency key is reused with different request data."""


class HelpRequestStateConflictError(ValueError):
    """Raised when another worker has already changed a help-request result."""


class HelpRequestCapacityError(RuntimeError):
    """Raised when the bounded queue has no safely evictable result."""


class HelpRequestRepository(Protocol):
    """Store only bounded result metadata, never the submitted image bytes."""

    def create_or_get(
        self,
        result: HelpRequestResult,
        fingerprint: str,
        expires_at: datetime,
        access_token_digest: str,
        now: datetime,
    ) -> HelpRequestResult:
        """Create a result or return the identical idempotent submission."""

    def get(self, request_id: UUID, now: datetime) -> HelpRequestResult | None:
        """Read one non-expired result."""

    def is_access_authorized(
        self,
        request_id: UUID,
        access_token_digest: str,
        now: datetime,
    ) -> bool:
        """Check an expiring client capability without returning its stored digest."""

    def list(
        self,
        status: HelpRequestProcessingStatus | None,
        now: datetime,
    ) -> tuple[HelpRequestResult, ...]:
        """List non-expired results, newest first."""

    def save(
        self,
        result: HelpRequestResult,
        expected_version: int,
        now: datetime,
    ) -> None:
        """Persist one transition only when the stored version still matches."""
