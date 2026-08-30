"""Transient screenshot help request orchestration."""

import base64
import binascii
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID, uuid4

from guojing.application.help_requests.dto import HelpRequestRequest
from guojing.application.help_requests.in_memory_repository import (
    InMemoryHelpRequestRepository,
)
from guojing.application.help_requests.models import HelpRequestReceipt
from guojing.application.help_requests.ports import (
    ClientRequestConflictError,
    HelpRequestRepository,
)
from guojing.application.help_requests.processor import HelpRequestProcessor
from guojing.domain.help_requests import (
    HelpRequestGuidance,
    HelpRequestIntent,
    HelpRequestProcessingRoute,
    HelpRequestProcessingStatus,
    HelpRequestResult,
    HelpRequestTutorialMatch,
    HelpRequestTutorialPlan,
    verify_sanitized_image,
)


class InvalidHelpRequestPayload(ValueError):
    """Raised when an encoded image cannot satisfy the privacy contract."""


class HelpRequestNotFound(LookupError):
    """Raised when a status query references an unknown or expired request."""


PROCESSOR_FAILURE_REVIEW_REASON = "处理服务暂时不可用, 请由人工复核后重试."


class HelpRequestService:
    """Validate, route and immediately forget one sanitized screenshot."""

    def __init__(
        self,
        clock: Callable[[], datetime] | None = None,
        *,
        repository: HelpRequestRepository | None = None,
        result_ttl: timedelta = timedelta(hours=24),
        max_results: int = 1_000,
    ) -> None:
        if result_ttl <= timedelta(0):
            raise ValueError("result_ttl must be positive")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._result_ttl = result_ttl
        self._repository = repository or InMemoryHelpRequestRepository(max_results=max_results)

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
            fingerprint = sha256(
                "|".join(
                    (
                        command.intent.value,
                        sha256(command.question.encode("utf-8")).hexdigest(),
                        str(command.image_width),
                        str(command.image_height),
                        str(command.redaction_count),
                        str(command.no_sensitive_content_confirmed),
                        command.sanitized_sha256,
                    )
                ).encode("utf-8")
            ).hexdigest()
            now = self._clock()
            access_token = token_urlsafe(32)
            result = HelpRequestResult(
                request_id=uuid4(),
                client_request_id=command.client_request_id,
                intent=command.intent,
                processing_route=route,
                processing_status=HelpRequestProcessingStatus.RECEIVED,
                received_at=now,
                updated_at=now,
            )
            try:
                stored = self._repository.create_or_get(
                    result,
                    fingerprint,
                    now + self._result_ttl,
                    sha256(access_token.encode("utf-8")).hexdigest(),
                    now,
                )
            except ClientRequestConflictError as error:
                raise InvalidHelpRequestPayload(str(error)) from error
            return self._receipt(stored, access_token)
        finally:
            image[:] = b"\x00" * len(image)

    def get_result(self, request_id: UUID) -> HelpRequestResult:
        """Return status metadata without retaining or re-reading the image."""
        result = self._repository.get(request_id, self._clock())
        if result is None:
            raise HelpRequestNotFound(str(request_id))
        return result

    def is_access_authorized(self, request_id: UUID, access_token: str) -> bool:
        """Check the bearer capability issued with one accepted request receipt."""
        if not access_token or len(access_token) > 256:
            return False
        return self._repository.is_access_authorized(
            request_id,
            sha256(access_token.encode("utf-8")).hexdigest(),
            self._clock(),
        )

    def list_results(
        self,
        *,
        status: HelpRequestProcessingStatus | None = None,
    ) -> tuple[HelpRequestResult, ...]:
        """Return metadata snapshots for an internal reviewer or worker."""
        return self._repository.list(status, self._clock())

    def process(
        self,
        request_id: UUID,
        processor: HelpRequestProcessor,
        *,
        workflow_stage: str | None = None,
    ) -> HelpRequestResult:
        """Run one metadata-only processor and apply its bounded outcome."""
        current = self.get_result(request_id)
        if current.processing_status is HelpRequestProcessingStatus.RECEIVED:
            current = self.mark_processing(request_id)
        elif current.processing_status is not HelpRequestProcessingStatus.PROCESSING:
            raise ValueError(
                f"cannot process request in status {current.processing_status}",
            )
        try:
            outcome = processor.process(current)
        except Exception:
            return self.mark_needs_human_review(
                request_id,
                PROCESSOR_FAILURE_REVIEW_REASON,
                workflow_stage=workflow_stage,
            )
        if outcome.status is HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW:
            if outcome.review_reason is None:
                raise ValueError("review outcome needs a reason")
            return self.mark_needs_human_review(
                request_id,
                outcome.review_reason,
                workflow_stage=workflow_stage,
            )
        if outcome.status is HelpRequestProcessingStatus.GUIDANCE_READY:
            if outcome.guidance is None:
                raise ValueError("guidance outcome needs guidance")
            return self.publish_guidance(
                request_id,
                outcome.guidance,
                workflow_stage=workflow_stage,
            )
        raise ValueError(f"processor returned unsupported terminal status {outcome.status}")

    def mark_processing(
        self,
        request_id: UUID,
        *,
        workflow_stage: str | None = None,
    ) -> HelpRequestResult:
        """Move a received request into the worker-processing state."""
        return self._transition(
            request_id,
            HelpRequestProcessingStatus.PROCESSING,
            workflow_stage=workflow_stage,
        )

    def mark_needs_human_review(
        self,
        request_id: UUID,
        reason: str,
        *,
        workflow_stage: str | None = None,
        tutorial_match: HelpRequestTutorialMatch | None = None,
        tutorial_plan: HelpRequestTutorialPlan | None = None,
    ) -> HelpRequestResult:
        """Pause automation when deterministic safety review is required."""
        return self._transition(
            request_id,
            HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW,
            human_review_reason=reason,
            workflow_stage=workflow_stage or "needs_human_review",
            tutorial_match=tutorial_match,
            tutorial_plan=tutorial_plan,
        )

    def publish_guidance(
        self,
        request_id: UUID,
        guidance: HelpRequestGuidance,
        *,
        workflow_stage: str | None = None,
    ) -> HelpRequestResult:
        """Publish explanatory steps without creating executable actions."""
        return self._transition(
            request_id,
            HelpRequestProcessingStatus.GUIDANCE_READY,
            guidance=guidance,
            workflow_stage=workflow_stage or "completed",
        )

    def _transition(
        self,
        request_id: UUID,
        status: HelpRequestProcessingStatus,
        *,
        guidance: HelpRequestGuidance | None = None,
        human_review_reason: str | None = None,
        workflow_stage: str | None = None,
        tutorial_match: HelpRequestTutorialMatch | None = None,
        tutorial_plan: HelpRequestTutorialPlan | None = None,
    ) -> HelpRequestResult:
        now = self._clock()
        result = self._repository.get(request_id, now)
        if result is None:
            raise HelpRequestNotFound(str(request_id))
        updated = result.transition(
            status,
            now,
            guidance=guidance,
            human_review_reason=human_review_reason,
            workflow_stage=workflow_stage,
            tutorial_match=tutorial_match,
            tutorial_plan=tutorial_plan,
        )
        self._repository.save(updated, result.state_version, now)
        return updated

    @staticmethod
    def _receipt(result: HelpRequestResult, access_token: str) -> HelpRequestReceipt:
        return HelpRequestReceipt(
            request_id=result.request_id,
            client_request_id=result.client_request_id,
            intent=result.intent,
            processing_route=result.processing_route,
            received_at=result.received_at,
            access_token=access_token,
            # A POST receipt describes acceptance, not the current worker result.
            # Replays therefore cannot claim guidance_ready without its payload.
            processing_status=HelpRequestProcessingStatus.RECEIVED,
        )
