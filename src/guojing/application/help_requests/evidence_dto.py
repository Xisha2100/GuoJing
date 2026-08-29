"""Strict API contract for sanitized semantic evidence."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from guojing.domain.evidence import (
    EvidenceAnchor,
    EvidenceBounds,
    EvidenceEnvelope,
    EvidenceSharingPolicy,
    EvidenceSource,
)


class EvidenceApiModel(BaseModel):
    """Evidence models reject unknown fields and never expose raw OCR text."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvidenceBoundsRequest(EvidenceApiModel):
    """Optional normalized rectangle used by the overlay planner."""

    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    right: float = Field(ge=0, le=1)
    bottom: float = Field(ge=0, le=1)

    def to_domain(self) -> EvidenceBounds:
        return EvidenceBounds(
            left=self.left,
            top=self.top,
            right=self.right,
            bottom=self.bottom,
        )


class EvidenceAnchorRequest(EvidenceApiModel):
    """Anchor ID and confidence only; raw recognized strings are not accepted."""

    anchor_id: str = Field(min_length=1, max_length=120)
    confidence: float = Field(ge=0, le=1)
    normalized_bounds: EvidenceBoundsRequest | None = None

    def to_domain(self) -> EvidenceAnchor:
        return EvidenceAnchor(
            anchor_id=self.anchor_id,
            confidence=self.confidence,
            normalized_bounds=(
                self.normalized_bounds.to_domain() if self.normalized_bounds is not None else None
            ),
        )


class HelpRequestEvidenceRequest(EvidenceApiModel):
    """Wire envelope for one explicit, sanitized evidence submission."""

    schema_version: Literal["1.0"] = "1.0"
    evidence_id: UUID
    package_name: str = Field(min_length=1, max_length=255)
    version_name: str = Field(min_length=1, max_length=120)
    version_code: int = Field(ge=1)
    source: EvidenceSource
    sharing_policy: EvidenceSharingPolicy
    structure_score: float = Field(ge=0, le=1)
    captured_at: datetime
    expires_at: datetime
    anchors: list[EvidenceAnchorRequest] = Field(max_length=64)
    sanitized_screenshot_sha256: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_timestamps(self) -> Self:
        if self.captured_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("evidence timestamps must include a timezone")
        if self.expires_at <= self.captured_at:
            raise ValueError("evidence expires_at must be after captured_at")
        return self

    def to_domain(self, request_id: UUID) -> EvidenceEnvelope:
        return EvidenceEnvelope(
            evidence_id=self.evidence_id,
            request_id=request_id,
            package_name=self.package_name,
            version_name=self.version_name,
            version_code=self.version_code,
            source=self.source,
            sharing_policy=self.sharing_policy,
            structure_score=self.structure_score,
            captured_at=self.captured_at,
            expires_at=self.expires_at,
            anchors=tuple(anchor.to_domain() for anchor in self.anchors),
            sanitized_screenshot_sha256=self.sanitized_screenshot_sha256,
        )
