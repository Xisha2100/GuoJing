"""Deterministic lifecycle rules for screenshot help results."""

from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

import pytest

from guojing.application.help_requests.dto import HelpRequestRequest
from guojing.application.help_requests.service import HelpRequestNotFound, HelpRequestService
from guojing.domain.help_requests import (
    HelpRequestGuidance,
    HelpRequestGuidanceStep,
    HelpRequestProcessingStatus,
)


def _request() -> HelpRequestRequest:
    return HelpRequestRequest(
        client_request_id=uuid4(),
        intent="general_guidance",
        question="这个页面下一步怎么做?",
        image_media_type="image/jpeg",
        image_width=720,
        image_height=1_440,
        redaction_count=0,
        no_sensitive_content_confirmed=True,
        sanitized_sha256=sha256(b"\xff\xd8\xff\xd9").hexdigest(),
        send_consent=True,
        sanitized_image_base64="/9j/2Q==",
    )


def test_result_moves_forward_and_publishes_only_manual_guidance() -> None:
    start = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    service = HelpRequestService(clock=lambda: start)
    receipt = service.accept(_request())

    assert receipt.processing_status is HelpRequestProcessingStatus.RECEIVED
    processing = service.mark_processing(receipt.request_id)
    assert processing.processing_status is HelpRequestProcessingStatus.PROCESSING

    review = service.mark_needs_human_review(
        receipt.request_id,
        "页面包含支付确认, 不能自动给出下一步操作.",
    )
    assert review.processing_status is HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW
    assert review.human_review_reason is not None

    guidance = HelpRequestGuidance(
        title="先确认页面信息",
        steps=(
            HelpRequestGuidanceStep(
                step_id="check-title",
                title="看清页面标题",
                instruction="请先读一读页面顶部的标题, 再决定是否继续.",
            ),
        ),
    )
    ready = service.publish_guidance(receipt.request_id, guidance)
    assert ready.processing_status is HelpRequestProcessingStatus.GUIDANCE_READY
    assert ready.guidance == guidance
    assert ready.human_review_reason is None


def test_result_transitions_are_forward_only() -> None:
    service = HelpRequestService(clock=lambda: datetime.now(UTC))
    receipt = service.accept(_request())

    with pytest.raises(ValueError, match="cannot transition"):
        service.publish_guidance(
            receipt.request_id,
            HelpRequestGuidance(
                title="基础指引",
                steps=(
                    HelpRequestGuidanceStep(
                        step_id="one",
                        title="第一步",
                        instruction="请由你自己点击页面上的按钮。",
                    ),
                ),
            ),
        )

    service.mark_processing(receipt.request_id)
    with pytest.raises(ValueError, match="cannot transition"):
        service.mark_processing(receipt.request_id)


def test_guidance_ready_requires_manual_action_steps() -> None:
    with pytest.raises(ValueError, match="manual user action"):
        HelpRequestGuidanceStep(
            step_id="auto",
            title="自动点击",
            instruction="替用户点击支付按钮。",
            requires_manual_action=False,
        )


def test_guidance_rejects_financial_and_irreversible_instructions() -> None:
    with pytest.raises(ValueError, match="blocked irreversible"):
        HelpRequestGuidanceStep(
            step_id="pay",
            title="下一步",
            instruction="请点击支付并输入密码。",
        )


def test_unknown_result_is_not_exposed() -> None:
    service = HelpRequestService()

    with pytest.raises(HelpRequestNotFound):
        service.get_result(uuid4())


def test_in_memory_results_are_bounded() -> None:
    service = HelpRequestService(max_results=1)
    first = service.accept(_request())
    second = service.accept(_request())

    with pytest.raises(HelpRequestNotFound):
        service.get_result(first.request_id)
    assert service.get_result(second.request_id).request_id == second.request_id
