"""Structured model boundary with deterministic safety fallbacks."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from guojing.application.help_requests.processor import HelpRequestProcessorOutcome
from guojing.domain.help_requests import (
    HelpRequestGuidance,
    HelpRequestGuidanceStep,
    HelpRequestIntent,
    HelpRequestProcessingRoute,
    HelpRequestProcessingStatus,
    HelpRequestResult,
)

MAX_MODEL_OUTPUT_KEYS = frozenset({"title", "steps"})
MAX_MODEL_STEP_KEYS = frozenset({"step_id", "title", "instruction", "requires_manual_action"})


@dataclass(frozen=True, slots=True)
class ModelGuidanceContext:
    """Metadata safe to pass to a model adapter after the image is discarded."""

    request_id: UUID
    intent: HelpRequestIntent
    processing_route: HelpRequestProcessingRoute


class GuidanceModel(Protocol):
    """Minimal adapter implemented by LangGraph, Deep Agent or an HTTP client."""

    def generate(self, context: ModelGuidanceContext) -> Mapping[str, object]:
        """Return a JSON-like object, never mutate request state or operate a device."""


class ModelOutputValidationError(ValueError):
    """Raised when model output is not an allowed manual guidance shape."""


class StructuredGuidanceParser:
    """Fail-closed parser for model-produced human instructions."""

    def parse(self, payload: Mapping[str, object]) -> HelpRequestGuidance:
        """Convert a mapping into domain guidance while rejecting unknown fields."""
        if set(payload) != MAX_MODEL_OUTPUT_KEYS:
            raise ModelOutputValidationError("model output must contain only title and steps")
        title = _required_string(payload, "title", max_length=160)
        raw_steps = payload["steps"]
        if not isinstance(raw_steps, list) or not 1 <= len(raw_steps) <= 20:
            raise ModelOutputValidationError("model steps must contain 1 to 20 items")
        steps = tuple(self._parse_step(index, raw_step) for index, raw_step in enumerate(raw_steps))
        try:
            return HelpRequestGuidance(title=title, steps=steps)
        except ValueError as error:
            raise ModelOutputValidationError(str(error)) from error

    def _parse_step(self, index: int, raw_step: object) -> HelpRequestGuidanceStep:
        if not isinstance(raw_step, dict) or set(raw_step) != MAX_MODEL_STEP_KEYS:
            raise ModelOutputValidationError(f"model step {index} has an invalid shape")
        manual = raw_step["requires_manual_action"]
        if manual is not True:
            raise ModelOutputValidationError(
                f"model step {index} must require manual user action",
            )
        try:
            return HelpRequestGuidanceStep(
                step_id=_required_string(raw_step, "step_id", max_length=64),
                title=_required_string(raw_step, "title", max_length=120),
                instruction=_required_string(raw_step, "instruction", max_length=500),
                requires_manual_action=True,
            )
        except ValueError as error:
            raise ModelOutputValidationError(str(error)) from error


class SafeGuidanceModelProcessor:
    """Wrap one model call and turn every failure into a review outcome."""

    def __init__(
        self,
        model: GuidanceModel,
        *,
        parser: StructuredGuidanceParser | None = None,
    ) -> None:
        self._model = model
        self._parser = parser or StructuredGuidanceParser()

    def process(self, request: HelpRequestResult) -> HelpRequestProcessorOutcome:
        """Generate guidance only for the general route and only after validation."""
        if request.processing_route is not HelpRequestProcessingRoute.GENERAL_GUIDANCE:
            return HelpRequestProcessorOutcome(
                status=HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW,
                review_reason="教程请求必须先通过页面匹配, 模型不能绕过证据门槛.",
            )
        context = ModelGuidanceContext(
            request_id=request.request_id,
            intent=request.intent,
            processing_route=request.processing_route,
        )
        try:
            guidance = self._parser.parse(self._model.generate(context))
        except Exception:
            return HelpRequestProcessorOutcome(
                status=HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW,
                review_reason="模型输出未通过结构化安全校验, 需要人工复核.",
            )
        return HelpRequestProcessorOutcome(
            status=HelpRequestProcessingStatus.GUIDANCE_READY,
            guidance=guidance,
        )


def _required_string(payload: Mapping[str, object], key: str, *, max_length: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ModelOutputValidationError(
            f"model field {key!r} must be a non-empty string of at most {max_length} characters",
        )
    return value
