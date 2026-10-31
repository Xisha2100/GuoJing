"""Validated wire outputs for the visual guidance model and its specialists."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from guojing.domain.agent_guidance import GuidanceDecision, GuidanceStatus, NormalizedTarget
from guojing.domain.guidance_policy import (
    GuidanceCandidate,
    GuidanceReview,
    GuidanceRisk,
    ReviewIssue,
)


class TargetOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, strict=True)

    left: float = Field(ge=0.0, le=1.0)
    top: float = Field(ge=0.0, le=1.0)
    right: float = Field(ge=0.0, le=1.0)
    bottom: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def require_positive_rectangle(self) -> "TargetOutput":
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("target must be a positive rectangle")
        return self


class GuidanceDecisionOutput(BaseModel):
    """Structured response requested from the main Deep Agent."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, strict=True)

    status: Literal["continue", "completed", "cannot_determine"]
    instruction: str | None = Field(default=None, max_length=80)
    target: TargetOutput | None = None
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_shape(self) -> "GuidanceDecisionOutput":
        if self.status == "continue":
            if self.instruction is None or not self.instruction.strip():
                raise ValueError("continue requires an instruction")
            if self.target is None:
                raise ValueError("continue requires a target")
        elif self.target is not None:
            raise ValueError("terminal results cannot contain a target")
        return self

    def to_domain(self) -> GuidanceDecision:
        return GuidanceDecision(
            GuidanceStatus(self.status),
            self.instruction,
            NormalizedTarget(**self.target.model_dump()) if self.target else None,
            self.confidence,
        )


class GuidanceCandidateOutput(GuidanceDecisionOutput):
    target_description: str = Field(max_length=200)
    evidence: str = Field(max_length=500)
    risk: Literal["ordinary", "financial", "irreversible", "unknown"]

    def candidate(self) -> GuidanceCandidate:
        return GuidanceCandidate(
            self.to_domain(), self.target_description, self.evidence, GuidanceRisk(self.risk)
        )


class VisibleControlOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(max_length=120)
    role: str = Field(max_length=80)
    bounds: TargetOutput


class UiAnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_page: str = Field(max_length=200)
    visible_controls: list[VisibleControlOutput] = Field(max_length=20)
    likely_target: TargetOutput | None
    summary: str = Field(max_length=500)


class GuidanceReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    candidate_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved: bool
    issue: Literal["none", "wording", "visual", "completion", "risk", "uncertain"]
    risk: Literal["ordinary", "financial", "irreversible", "unknown"]
    target_supported: bool
    completion_supported: bool
    feedback: str = Field(max_length=500)

    def to_domain(self) -> GuidanceReview:
        return GuidanceReview(
            self.candidate_digest,
            self.approved,
            ReviewIssue(self.issue),
            GuidanceRisk(self.risk),
            self.target_supported,
            self.completion_supported,
            self.feedback,
        )
