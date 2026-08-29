"""Transient screenshot help request orchestration."""

import base64
import binascii
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from threading import Lock
from uuid import UUID, uuid4

from guojing.application.help_requests.dto import HelpRequestRequest
from guojing.application.help_requests.models import HelpRequestReceipt
from guojing.application.help_requests.processor import HelpRequestProcessor
from guojing.domain.help_requests import (
    HelpRequestGuidance,
    HelpRequestIntent,
    HelpRequestProcessingRoute,
    HelpRequestProcessingStatus,
    HelpRequestResult,
    verify_sanitized_image,
)


class InvalidHelpRequestPayload(ValueError):
    """Raised when an encoded image cannot satisfy the privacy contract."""


class HelpRequestNotFound(LookupError):
    """Raised when a status query references an unknown or expired request."""


class HelpRequestService:
    """Validate, route and immediately forget one sanitized screenshot."""

    def __init__(
        self,
        clock: Callable[[], datetime] | None = None,
        *,
        max_results: int = 1_000,
    ) -> None:
        if max_results < 1:
            raise ValueError("max_results must be positive")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._max_results = max_results
        self._results: dict[UUID, HelpRequestResult] = {}
        self._request_ids_by_client_id: dict[UUID, UUID] = {}
        self._fingerprints_by_client_id: dict[UUID, tuple[object, ...]] = {}
        self._results_lock = Lock()

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
            fingerprint = (
                command.intent,
                sha256(command.question.encode("utf-8")).hexdigest(),
                command.image_width,
                command.image_height,
                command.redaction_count,
                command.no_sensitive_content_confirmed,
                command.sanitized_sha256,
            )
            request_id = uuid4()
            received_at = self._clock()
            result = HelpRequestResult(
                request_id=request_id,
                client_request_id=command.client_request_id,
                intent=command.intent,
                processing_route=route,
                processing_status=HelpRequestProcessingStatus.RECEIVED,
                received_at=received_at,
                updated_at=received_at,
            )
            with self._results_lock:
                previous_request_id = self._request_ids_by_client_id.get(command.client_request_id)
                if previous_request_id is not None:
                    previous = self._results.get(previous_request_id)
                    if previous is not None:
                        if (
                            self._fingerprints_by_client_id.get(command.client_request_id)
                            != fingerprint
                        ):
                            raise InvalidHelpRequestPayload(
                                "client_request_id cannot be reused for different request data",
                            )
                        return self._receipt(previous)
                if len(self._results) >= self._max_results:
                    oldest_request_id = min(
                        self._results,
                        key=lambda candidate: self._results[candidate].updated_at,
                    )
                    oldest = self._results[oldest_request_id]
                    del self._results[oldest_request_id]
                    self._request_ids_by_client_id.pop(
                        oldest.client_request_id,
                        None,
                    )
                    self._fingerprints_by_client_id.pop(oldest.client_request_id, None)
                self._results[request_id] = result
                self._request_ids_by_client_id[command.client_request_id] = request_id
                self._fingerprints_by_client_id[command.client_request_id] = fingerprint
            return self._receipt(result)
        finally:
            image[:] = b"\x00" * len(image)

    def get_result(self, request_id: UUID) -> HelpRequestResult:
        """Return status metadata without retaining or re-reading the image."""
        with self._results_lock:
            result = self._results.get(request_id)
        if result is None:
            raise HelpRequestNotFound(str(request_id))
        return result

    def list_results(
        self,
        *,
        status: HelpRequestProcessingStatus | None = None,
    ) -> tuple[HelpRequestResult, ...]:
        """Return metadata snapshots for an internal reviewer or worker."""
        with self._results_lock:
            values = tuple(self._results.values())
        if status is not None:
            values = tuple(value for value in values if value.processing_status is status)
        return tuple(sorted(values, key=lambda value: value.updated_at, reverse=True))

    def process(
        self,
        request_id: UUID,
        processor: HelpRequestProcessor,
    ) -> HelpRequestResult:
        """Run one metadata-only processor and apply its bounded outcome."""
        current = self.mark_processing(request_id)
        outcome = processor.process(current)
        if outcome.status is HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW:
            if outcome.review_reason is None:
                raise ValueError("review outcome needs a reason")
            return self.mark_needs_human_review(request_id, outcome.review_reason)
        if outcome.status is HelpRequestProcessingStatus.GUIDANCE_READY:
            if outcome.guidance is None:
                raise ValueError("guidance outcome needs guidance")
            return self.publish_guidance(request_id, outcome.guidance)
        raise ValueError(f"processor returned unsupported terminal status {outcome.status}")

    def mark_processing(self, request_id: UUID) -> HelpRequestResult:
        """Move a received request into the worker-processing state."""
        return self._transition(request_id, HelpRequestProcessingStatus.PROCESSING)

    def mark_needs_human_review(
        self,
        request_id: UUID,
        reason: str,
    ) -> HelpRequestResult:
        """Pause automation when deterministic safety review is required."""
        return self._transition(
            request_id,
            HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW,
            human_review_reason=reason,
        )

    def publish_guidance(
        self,
        request_id: UUID,
        guidance: HelpRequestGuidance,
    ) -> HelpRequestResult:
        """Publish explanatory steps without creating executable actions."""
        return self._transition(
            request_id,
            HelpRequestProcessingStatus.GUIDANCE_READY,
            guidance=guidance,
        )

    def _transition(
        self,
        request_id: UUID,
        status: HelpRequestProcessingStatus,
        *,
        guidance: HelpRequestGuidance | None = None,
        human_review_reason: str | None = None,
    ) -> HelpRequestResult:
        with self._results_lock:
            result = self._results.get(request_id)
            if result is None:
                raise HelpRequestNotFound(str(request_id))
            updated = result.transition(
                status,
                self._clock(),
                guidance=guidance,
                human_review_reason=human_review_reason,
            )
            self._results[request_id] = updated
        return updated

    @staticmethod
    def _receipt(result: HelpRequestResult) -> HelpRequestReceipt:
        return HelpRequestReceipt(
            request_id=result.request_id,
            client_request_id=result.client_request_id,
            intent=result.intent,
            processing_route=result.processing_route,
            received_at=result.received_at,
            processing_status=result.processing_status,
        )
