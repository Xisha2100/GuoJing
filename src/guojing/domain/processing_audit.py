"""Privacy-safe audit payloads for background help-request processing."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProcessingAuditEvent:
    """An event deliberately limited to identifiers and stable operational facts."""

    request_id: UUID
    worker_id: str
    action: str
    occurred_at: datetime
    attempt_number: int

    def __post_init__(self) -> None:
        if not self.worker_id.strip() or len(self.worker_id) > 120:
            raise ValueError("worker_id must contain 1 to 120 characters")
        valid_action = self.action.replace("_", "").isalnum()
        if not self.action.strip() or len(self.action) > 80 or not valid_action:
            raise ValueError("action must be a short identifier")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        if self.attempt_number < 1:
            raise ValueError("attempt_number must be positive")
