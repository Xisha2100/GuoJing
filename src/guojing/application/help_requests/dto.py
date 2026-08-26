"""Strict JSON contract for a locally sanitized screenshot submission."""

from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from guojing.domain.help_requests import (
    MAX_REDACTIONS,
    MAX_SCREENSHOT_BYTES,
    MAX_SCREENSHOT_DIMENSION,
    HelpRequestCommand,
    HelpRequestIntent,
)

MAX_BASE64_LENGTH = ((MAX_SCREENSHOT_BYTES + 2) // 3) * 4


class HelpRequestApiModel(BaseModel):
    """Base model that rejects unknown fields at the API boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class HelpRequestRequest(HelpRequestApiModel):
    """Wire payload for one explicit send action."""

    schema_version: Literal["1.0"] = "1.0"
    client_request_id: UUID
    intent: HelpRequestIntent
    question: str = Field(min_length=1, max_length=300)
    image_media_type: Literal["image/jpeg"]
    image_width: int = Field(ge=1, le=MAX_SCREENSHOT_DIMENSION)
    image_height: int = Field(ge=1, le=MAX_SCREENSHOT_DIMENSION)
    redaction_count: int = Field(ge=0, le=MAX_REDACTIONS)
    no_sensitive_content_confirmed: bool
    sanitized_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    send_consent: Literal[True]
    sanitized_image_base64: str = Field(min_length=1, max_length=MAX_BASE64_LENGTH)

    @model_validator(mode="after")
    def validate_privacy_metadata(self) -> Self:
        if max(self.image_width, self.image_height) > MAX_SCREENSHOT_DIMENSION:
            raise ValueError("the longest image dimension must not exceed 1440 pixels")
        if self.redaction_count == 0 and not self.no_sensitive_content_confirmed:
            raise ValueError("a zero-mask request needs an explicit privacy confirmation")
        if self.redaction_count > 0 and self.no_sensitive_content_confirmed:
            raise ValueError("redactions and no-sensitive confirmation are mutually exclusive")
        return self

    def to_command(self) -> HelpRequestCommand:
        """Map only non-image metadata into the framework-independent domain."""
        return HelpRequestCommand(
            client_request_id=self.client_request_id,
            intent=self.intent,
            question=self.question,
            image_media_type=self.image_media_type,
            image_width=self.image_width,
            image_height=self.image_height,
            redaction_count=self.redaction_count,
            no_sensitive_content_confirmed=self.no_sensitive_content_confirmed,
            sanitized_sha256=self.sanitized_sha256,
            send_consent=self.send_consent,
        )
