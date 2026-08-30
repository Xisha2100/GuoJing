"""Approved guidance actions and deterministic risk authorization."""

from dataclasses import dataclass
from enum import StrEnum

from guojing.domain.tutorials.models import RiskLevel


class GuidanceAuthorization(StrEnum):
    """Whether an action may be explained in an automated guidance response."""

    ALLOW = "allow"
    STOP_AND_CONFIRM = "stop_and_confirm"
    REQUIRE_HUMAN_REVIEW = "require_human_review"


@dataclass(frozen=True, slots=True)
class ApprovedGuidanceAction:
    """A reviewed, non-executable instruction selected by a stable identifier."""

    action_id: str
    title: str
    instruction: str
    risk_level: RiskLevel

    def __post_init__(self) -> None:
        for value, name, maximum in (
            (self.action_id, "action_id", 120),
            (self.title, "title", 120),
            (self.instruction, "instruction", 500),
        ):
            if not value.strip() or len(value) > maximum:
                raise ValueError(f"{name} must contain 1 to {maximum} characters")


def authorize_guidance_action(risk_level: RiskLevel) -> GuidanceAuthorization:
    """Classify guidance using risk metadata, never natural-language keywords."""
    if risk_level is RiskLevel.LOW:
        return GuidanceAuthorization.ALLOW
    if risk_level is RiskLevel.SENSITIVE:
        return GuidanceAuthorization.STOP_AND_CONFIRM
    return GuidanceAuthorization.REQUIRE_HUMAN_REVIEW
