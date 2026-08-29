"""Deterministic processor tests for modules 17 and 18."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from guojing.application.help_requests.basic_guidance import (
    DefaultGuidanceCatalog,
    DeterministicHelpRequestProcessor,
)
from guojing.application.help_requests.dto import HelpRequestRequest
from guojing.application.help_requests.processor import HelpRequestProcessorOutcome
from guojing.application.help_requests.service import HelpRequestService
from guojing.domain.help_requests import (
    HelpRequestIntent,
    HelpRequestProcessingRoute,
    HelpRequestProcessingStatus,
    HelpRequestResult,
)


def _result(route: HelpRequestProcessingRoute) -> HelpRequestResult:
    now = datetime.now(UTC)
    return HelpRequestResult(
        request_id=uuid4(),
        client_request_id=uuid4(),
        intent=(
            HelpRequestIntent.RECORDED_TUTORIAL
            if route is HelpRequestProcessingRoute.TUTORIAL_MATCH
            else HelpRequestIntent.GENERAL_GUIDANCE
        ),
        processing_route=route,
        processing_status=HelpRequestProcessingStatus.PROCESSING,
        received_at=now,
        updated_at=now,
    )


def test_general_guidance_is_reviewed_manual_content() -> None:
    outcome = DeterministicHelpRequestProcessor().process(
        _result(HelpRequestProcessingRoute.GENERAL_GUIDANCE),
    )

    assert outcome.status is HelpRequestProcessingStatus.GUIDANCE_READY
    assert outcome.guidance is not None
    assert len(outcome.guidance.steps) == 3
    assert all(step.requires_manual_action for step in outcome.guidance.steps)


def test_recorded_tutorial_waits_for_page_evidence() -> None:
    outcome = DeterministicHelpRequestProcessor().process(
        _result(HelpRequestProcessingRoute.TUTORIAL_MATCH),
    )

    assert outcome.status is HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW
    assert outcome.guidance is None
    assert outcome.review_reason is not None


def test_processor_outcome_rejects_incomplete_terminal_shapes() -> None:
    with pytest.raises(ValueError):
        HelpRequestProcessorOutcome(HelpRequestProcessingStatus.GUIDANCE_READY)

    with pytest.raises(ValueError):
        HelpRequestProcessorOutcome(HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW)


def test_catalog_does_not_include_dangerous_operations() -> None:
    guidance = DefaultGuidanceCatalog().general_guidance()

    assert all("转账" not in step.instruction for step in guidance.steps)
    assert all("支付" not in step.instruction for step in guidance.steps)


def test_service_process_applies_a_general_guidance_outcome() -> None:
    from hashlib import sha256

    request = HelpRequestRequest(
        client_request_id=uuid4(),
        intent="general_guidance",
        question="怎么继续?",
        image_media_type="image/jpeg",
        image_width=720,
        image_height=1440,
        redaction_count=0,
        no_sensitive_content_confirmed=True,
        sanitized_sha256=sha256(b"\xff\xd8\xff\xd9").hexdigest(),
        send_consent=True,
        sanitized_image_base64="/9j/2Q==",
    )
    service = HelpRequestService()
    receipt = service.accept(request)

    result = service.process(receipt.request_id, DeterministicHelpRequestProcessor())

    assert result.processing_status is HelpRequestProcessingStatus.GUIDANCE_READY
    assert result.guidance is not None
