"""Framework-independent state and validation for visual guidance sessions."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class AgentSessionStatus(StrEnum):
    """Lifecycle of one user goal across several screenshots."""

    ACTIVE = "active"
    COMPLETED = "completed"
    CLOSED = "closed"


class AgentRunStatus(StrEnum):
    """Lifecycle of one asynchronous screenshot analysis."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GuidanceStatus(StrEnum):
    """Allowed outcomes from the visual guidance agent."""

    CONTINUE = "continue"
    COMPLETED = "completed"
    CANNOT_DETERMINE = "cannot_determine"


@dataclass(frozen=True, slots=True)
class NormalizedTarget:
    """A target rectangle relative to the submitted screenshot."""

    left: float
    top: float
    right: float
    bottom: float

    def __post_init__(self) -> None:
        values = (self.left, self.top, self.right, self.bottom)
        if any(not 0.0 <= value <= 1.0 for value in values):
            raise ValueError("target coordinates must be between zero and one")
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("target coordinates must describe a positive rectangle")


@dataclass(frozen=True, slots=True)
class GuidanceDecision:
    """One validated next step, never an executable device action."""

    status: GuidanceStatus
    instruction: str | None
    target: NormalizedTarget | None
    confidence: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between zero and one")
        if self.status is GuidanceStatus.CONTINUE:
            if self.instruction is None or not self.instruction.strip():
                raise ValueError("continue guidance requires an instruction")
            if len(self.instruction) > 300:
                raise ValueError("instruction must contain at most 300 characters")
            if self.target is None:
                raise ValueError("continue guidance requires a target")
        elif self.target is not None:
            raise ValueError("terminal guidance must not contain a target")
        elif self.instruction is not None and len(self.instruction) > 300:
            raise ValueError("instruction must contain at most 300 characters")


@dataclass(frozen=True, slots=True)
class AgentSession:
    session_id: UUID
    client_session_id: UUID
    access_token_digest: str
    goal: str
    target_package: str
    status: AgentSessionStatus
    current_step: int
    sandbox_id: str | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AgentRun:
    run_id: UUID
    session_id: UUID
    client_turn_id: UUID
    status: AgentRunStatus
    image_sha256: str
    image_media_type: str
    screen_width: int
    screen_height: int
    result: GuidanceDecision | None
    error_code: str | None
    retryable: bool
    model_name: str
    duration_ms: int | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class GuidanceStep:
    session_id: UUID
    run_id: UUID
    step_number: int
    decision: GuidanceDecision
    created_at: datetime
