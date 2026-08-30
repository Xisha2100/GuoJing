"""Model boundary tests: valid output publishes, everything else reviews."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import uuid4

import pytest

from guojing.application.help_requests.model_adapter import (
    ModelGuidanceContext,
    ModelOutputValidationError,
    SafeGuidanceModelProcessor,
    StructuredGuidanceParser,
)
from guojing.domain.help_requests import (
    HelpRequestIntent,
    HelpRequestProcessingRoute,
    HelpRequestProcessingStatus,
    HelpRequestResult,
)


def _payload() -> dict[str, object]:
    return {
        "title": "确认当前页面",
        "steps": [
            {
                "step_id": "look",
                "title": "看标题",
                "instruction": "请你亲自确认页面顶部的标题。",
                "requires_manual_action": True,
            },
        ],
    }


def _result(
    route: HelpRequestProcessingRoute = HelpRequestProcessingRoute.GENERAL_GUIDANCE,
) -> HelpRequestResult:
    now = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    return HelpRequestResult(
        request_id=uuid4(),
        client_request_id=uuid4(),
        intent=(
            HelpRequestIntent.GENERAL_GUIDANCE
            if route is HelpRequestProcessingRoute.GENERAL_GUIDANCE
            else HelpRequestIntent.RECORDED_TUTORIAL
        ),
        processing_route=route,
        processing_status=HelpRequestProcessingStatus.PROCESSING,
        received_at=now,
        updated_at=now,
    )


class StaticModel:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self.payload = payload

    def generate(
        self,
        context: ModelGuidanceContext,
        *,
        deadline: datetime,
    ) -> Mapping[str, object]:  # pragma: no cover - context is asserted below
        assert context.request_id
        assert context.task
        assert context.safety_rules
        assert deadline == context.deadline_at
        return self.payload


def test_parser_accepts_only_manual_guidance() -> None:
    guidance = StructuredGuidanceParser().parse(_payload())

    assert guidance.title == "确认当前页面"
    assert guidance.steps[0].requires_manual_action is True


def test_parser_rejects_unknown_fields() -> None:
    payload = _payload()
    payload["raw_ocr"] = "微信"

    with pytest.raises(ModelOutputValidationError, match="only title and steps"):
        StructuredGuidanceParser().parse(payload)


def test_parser_rejects_automatic_step() -> None:
    payload = _payload()
    step = {
        "step_id": "look",
        "title": "看标题",
        "instruction": "请你亲自确认页面顶部的标题。",
        "requires_manual_action": False,
    }
    payload["steps"] = [
        step,
    ]

    with pytest.raises(ModelOutputValidationError, match="manual"):
        StructuredGuidanceParser().parse(payload)


def test_parser_rejects_irreversible_instruction() -> None:
    payload = _payload()
    step = {
        "step_id": "buy",
        "title": "购买",
        "instruction": "请确认购买并立即下单。",
        "requires_manual_action": True,
    }
    payload["steps"] = [
        step,
    ]

    with pytest.raises(ModelOutputValidationError, match="blocked"):
        StructuredGuidanceParser().parse(payload)


def test_processor_publishes_valid_model_output() -> None:
    result = SafeGuidanceModelProcessor(StaticModel(_payload())).process(_result())

    assert result.status is HelpRequestProcessingStatus.GUIDANCE_READY
    assert result.guidance is not None


def test_processor_converts_model_failure_to_review() -> None:
    result = SafeGuidanceModelProcessor(StaticModel({"unexpected": True})).process(_result())

    assert result.status is HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW
    assert result.review_reason is not None


def test_processor_does_not_allow_model_on_tutorial_route() -> None:
    result = SafeGuidanceModelProcessor(StaticModel(_payload())).process(
        _result(HelpRequestProcessingRoute.TUTORIAL_MATCH),
    )

    assert result.status is HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW


def test_processor_times_out_and_keeps_a_blocking_model_from_accepting_more_work() -> None:
    release = Event()

    class BlockingModel:
        def generate(
            self,
            _context: ModelGuidanceContext,
            *,
            deadline: datetime,
        ) -> Mapping[str, object]:
            assert deadline.tzinfo is not None
            release.wait()
            return _payload()

    processor = SafeGuidanceModelProcessor(
        BlockingModel(),
        model_timeout=timedelta(milliseconds=10),
    )
    first = processor.process(_result())
    second = processor.process(_result())
    release.set()
    processor.shutdown()

    assert first.status is HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW
    assert "超时" in (first.review_reason or "")
    assert second.status is HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW
    assert "上一项" in (second.review_reason or "")
