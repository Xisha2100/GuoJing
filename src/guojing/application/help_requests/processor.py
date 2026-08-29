"""Ports and deterministic processor outcomes for screenshot help requests.

This module deliberately receives only the result metadata retained after the
sanitized image has been discarded. A future OCR or Agent adapter must first
produce a bounded, reviewable outcome rather than receiving a raw screenshot.
"""

from dataclasses import dataclass
from typing import Protocol

from guojing.domain.help_requests import (
    HelpRequestGuidance,
    HelpRequestProcessingStatus,
    HelpRequestResult,
)


@dataclass(frozen=True, slots=True)
class HelpRequestProcessorOutcome:
    """One safe terminal decision produced by a processor."""

    status: HelpRequestProcessingStatus
    guidance: HelpRequestGuidance | None = None
    review_reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {
            HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW,
            HelpRequestProcessingStatus.GUIDANCE_READY,
        }:
            raise ValueError("processor outcomes must be review or guidance ready")
        if self.status is HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW:
            if not self.review_reason or not self.review_reason.strip():
                raise ValueError("review outcomes need a non-empty reason")
            if self.guidance is not None:
                raise ValueError("review outcomes cannot include guidance")
        if self.status is HelpRequestProcessingStatus.GUIDANCE_READY:
            if self.guidance is None:
                raise ValueError("guidance outcomes need guidance")
            if self.review_reason is not None:
                raise ValueError("guidance outcomes cannot include a review reason")


class HelpRequestProcessor(Protocol):
    """Metadata-only port implemented by a local worker or future Agent adapter."""

    def process(self, request: HelpRequestResult) -> HelpRequestProcessorOutcome:
        """Return a bounded decision without mutating the request itself."""
