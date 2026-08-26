"""Transient screenshot help request orchestration."""

import base64
import binascii
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from guojing.application.help_requests.dto import HelpRequestRequest
from guojing.application.help_requests.models import HelpRequestReceipt
from guojing.domain.help_requests import (
    HelpRequestIntent,
    HelpRequestProcessingRoute,
    verify_sanitized_image,
)


class InvalidHelpRequestPayload(ValueError):
    """Raised when an encoded image cannot satisfy the privacy contract."""


class HelpRequestService:
    """Validate, route and immediately forget one sanitized screenshot."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))

    def accept(self, request: HelpRequestRequest) -> HelpRequestReceipt:
        """Validate the image transiently and return a non-AI processing receipt."""
        command = request.to_command()
        image = bytearray()
        try:
            try:
                image.extend(base64.b64decode(request.sanitized_image_base64, validate=True))
            except (ValueError, binascii.Error) as error:
                raise InvalidHelpRequestPayload(
                    "sanitized_image_base64 must be valid standard Base64",
                ) from error
            try:
                verify_sanitized_image(image, command.sanitized_sha256)
            except ValueError as error:
                raise InvalidHelpRequestPayload(str(error)) from error
            route = (
                HelpRequestProcessingRoute.TUTORIAL_MATCH
                if command.intent is HelpRequestIntent.RECORDED_TUTORIAL
                else HelpRequestProcessingRoute.GENERAL_GUIDANCE
            )
            return HelpRequestReceipt(
                request_id=uuid4(),
                client_request_id=command.client_request_id,
                intent=command.intent,
                processing_route=route,
                received_at=self._clock(),
            )
        finally:
            image[:] = b"\x00" * len(image)
