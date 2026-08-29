"""Privacy-safe evidence envelopes shared by Android and backend workers."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from uuid import UUID

MAX_EVIDENCE_ANCHORS = 64
MAX_EVIDENCE_ID_LENGTH = 120
MAX_PACKAGE_NAME_LENGTH = 255
MAX_VERSION_NAME_LENGTH = 120


class EvidenceSource(StrEnum):
    """Producer of semantic evidence, never a source of raw screen text."""

    ACCESSIBILITY = "accessibility"
    OCR = "ocr"


class EvidenceSharingPolicy(StrEnum):
    """Whether an envelope may cross the device/network boundary."""

    SANITIZED_NETWORK_ALLOWED = "sanitized_network_allowed"
    LOCAL_ONLY = "local_only"


@dataclass(frozen=True, slots=True)
class EvidenceBounds:
    """Normalized rectangle retained only to position a future explanation."""

    left: float
    top: float
    right: float
    bottom: float

    def __post_init__(self) -> None:
        values = (self.left, self.top, self.right, self.bottom)
        if any(not isfinite(value) or value < 0 or value > 1 for value in values):
            raise ValueError("evidence bounds must be finite and between 0 and 1")
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("evidence bounds must have positive width and height")


@dataclass(frozen=True, slots=True)
class EvidenceAnchor:
    """One bounded anchor match; deliberately has no OCR or accessibility text."""

    anchor_id: str
    confidence: float
    normalized_bounds: EvidenceBounds | None = None

    def __post_init__(self) -> None:
        if not self.anchor_id.strip() or len(self.anchor_id) > MAX_EVIDENCE_ID_LENGTH:
            raise ValueError("evidence anchor_id must contain 1 to 120 characters")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("evidence confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class EvidenceEnvelope:
    """An expiring, network-safe observation summary.

    The type system has no raw text or image-byte field by design. Callers must
    explicitly choose the network policy before an envelope can be submitted.
    """

    evidence_id: UUID
    request_id: UUID
    package_name: str
    version_name: str
    version_code: int
    source: EvidenceSource
    sharing_policy: EvidenceSharingPolicy
    structure_score: float
    captured_at: datetime
    expires_at: datetime
    anchors: tuple[EvidenceAnchor, ...]
    sanitized_screenshot_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.package_name.strip() or len(self.package_name) > MAX_PACKAGE_NAME_LENGTH:
            raise ValueError("package_name must contain 1 to 255 characters")
        if not self.version_name.strip() or len(self.version_name) > MAX_VERSION_NAME_LENGTH:
            raise ValueError("version_name must contain 1 to 120 characters")
        if self.version_code < 1:
            raise ValueError("version_code must be positive")
        if not isfinite(self.structure_score) or not 0 <= self.structure_score <= 1:
            raise ValueError("structure_score must be between 0 and 1")
        if self.captured_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("evidence timestamps must include a timezone")
        if self.expires_at <= self.captured_at:
            raise ValueError("evidence expires_at must be after captured_at")
        if len(self.anchors) > MAX_EVIDENCE_ANCHORS:
            raise ValueError("evidence cannot contain more than 64 anchors")
        anchor_ids = [anchor.anchor_id for anchor in self.anchors]
        if len(anchor_ids) != len(set(anchor_ids)):
            raise ValueError("evidence anchor_id values must be unique")
        if self.sanitized_screenshot_sha256 is not None:
            digest = self.sanitized_screenshot_sha256
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise ValueError("sanitized_screenshot_sha256 must be a lowercase SHA-256 digest")

    def is_expired(self, now: datetime) -> bool:
        """Return whether this short-lived envelope must no longer be used."""
        return self.expires_at <= _as_utc(now)

    def require_network_allowed(self, now: datetime) -> None:
        """Fail closed before a local-only or expired envelope reaches a server."""
        if self.sharing_policy is not EvidenceSharingPolicy.SANITIZED_NETWORK_ALLOWED:
            raise ValueError("local_only evidence must remain on the device")
        if self.is_expired(now):
            raise ValueError("evidence envelope has expired")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(UTC)
