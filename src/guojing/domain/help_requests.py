"""Privacy-bound value objects for screenshot help requests."""

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

MAX_SCREENSHOT_DIMENSION = 1_440
MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024
MAX_QUESTION_LENGTH = 300
MAX_REDACTIONS = 20


class HelpRequestIntent(StrEnum):
    """The deterministic route requested after the screenshot is received."""

    RECORDED_TUTORIAL = "recorded_tutorial"
    GENERAL_GUIDANCE = "general_guidance"


class HelpRequestProcessingRoute(StrEnum):
    """The next processing branch, without claiming that a model ran."""

    TUTORIAL_MATCH = "tutorial_match"
    GENERAL_GUIDANCE = "general_guidance"


@dataclass(frozen=True, slots=True)
class HelpRequestCommand:
    """Metadata accepted after the client has locally sanitized an image."""

    client_request_id: UUID
    intent: HelpRequestIntent
    question: str
    image_media_type: str
    image_width: int
    image_height: int
    redaction_count: int
    no_sensitive_content_confirmed: bool
    sanitized_sha256: str
    send_consent: bool

    def __post_init__(self) -> None:
        if not self.question.strip() or len(self.question) > MAX_QUESTION_LENGTH:
            raise ValueError("question must contain 1 to 300 characters")
        if self.image_media_type != "image/jpeg":
            raise ValueError("only sanitized image/jpeg screenshots are accepted")
        if not 1 <= self.image_width <= MAX_SCREENSHOT_DIMENSION:
            raise ValueError("image_width is outside the allowed range")
        if not 1 <= self.image_height <= MAX_SCREENSHOT_DIMENSION:
            raise ValueError("image_height is outside the allowed range")
        if not 0 <= self.redaction_count <= MAX_REDACTIONS:
            raise ValueError("redaction_count is outside the allowed range")
        if self.redaction_count == 0 and not self.no_sensitive_content_confirmed:
            raise ValueError("a zero-mask request needs an explicit privacy confirmation")
        if self.redaction_count > 0 and self.no_sensitive_content_confirmed:
            raise ValueError("redactions and no-sensitive confirmation are mutually exclusive")
        if len(self.sanitized_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sanitized_sha256
        ):
            raise ValueError("sanitized_sha256 must be a lowercase SHA-256 digest")
        if not self.send_consent:
            raise ValueError("explicit send consent is required")


def verify_sanitized_image(image: bytes | bytearray, expected_sha256: str) -> None:
    """Verify size and digest without retaining the image in a domain object."""
    if not 1 <= len(image) <= MAX_SCREENSHOT_BYTES:
        raise ValueError("sanitized image size is outside the allowed range")
    if len(image) < 4 or image[:2] != b"\xff\xd8" or image[-2:] != b"\xff\xd9":
        raise ValueError("sanitized image is not a JPEG byte stream")
    actual_sha256 = sha256(image).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError("sanitized image digest does not match the request metadata")
