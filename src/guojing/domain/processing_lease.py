"""Deterministic ownership rules for resumable background processing."""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class ProcessingLease:
    """A short-lived worker claim that may be safely taken over after expiry."""

    worker_id: str
    acquired_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if not self.worker_id.strip() or len(self.worker_id) > 120:
            raise ValueError("worker_id must contain 1 to 120 characters")
        if self.acquired_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("lease timestamps must be timezone-aware")
        if self.expires_at <= self.acquired_at:
            raise ValueError("lease expiry must be after acquisition")

    def is_active_at(self, now: datetime) -> bool:
        """Treat the exact expiry instant as available for recovery."""
        return now < self.expires_at

    def can_be_taken_over_at(self, now: datetime) -> bool:
        return not self.is_active_at(now)

    def renew(self, now: datetime, duration: timedelta) -> "ProcessingLease":
        """Renew only by the owning worker while its current lease is active."""
        if now.tzinfo is None or duration <= timedelta(0):
            raise ValueError("renewal needs a timezone-aware time and positive duration")
        if not self.is_active_at(now):
            raise ValueError("an expired lease cannot be renewed")
        return ProcessingLease(self.worker_id, now, now + duration)
