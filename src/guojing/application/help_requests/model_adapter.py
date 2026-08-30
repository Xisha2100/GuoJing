"""Structured model boundary with deterministic safety fallbacks."""

from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import BoundedSemaphore
from typing import Final, Protocol
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
DEFAULT_MODEL_TIMEOUT: Final = timedelta(seconds=10)
GENERAL_GUIDANCE_TASK: Final = "为不熟悉智能手机的用户提供安全、通用的手动操作说明"
GENERAL_GUIDANCE_RULES: Final = (
    "只能解释用户本人可见的界面, 不得执行或模拟点击。",
    "不得指导支付、转账、收红包、下单、删除、密码或验证码操作。",
    "每一步都必须要求用户本人确认页面并亲自操作。",
)


@dataclass(frozen=True, slots=True)
class ModelGuidanceContext:
    """Metadata safe to pass to a model adapter after the image is discarded."""

    request_id: UUID
    intent: HelpRequestIntent
    processing_route: HelpRequestProcessingRoute
    task: str
    safety_rules: tuple[str, ...]
    deadline_at: datetime

    def __post_init__(self) -> None:
        if not self.task.strip():
            raise ValueError("model task must be non-empty")
        if not self.safety_rules or any(not rule.strip() for rule in self.safety_rules):
            raise ValueError("model safety_rules must be non-empty")
        if self.deadline_at.tzinfo is None:
            raise ValueError("model deadline_at must be timezone-aware")


class GuidanceModel(Protocol):
    """Minimal adapter implemented by LangGraph, Deep Agent or an HTTP client."""

    def generate(
        self,
        context: ModelGuidanceContext,
        *,
        deadline: datetime,
    ) -> Mapping[str, object]:
        """Return JSON before deadline; never mutate request state or operate a device."""


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
        clock: Callable[[], datetime] | None = None,
        model_timeout: timedelta = DEFAULT_MODEL_TIMEOUT,
    ) -> None:
        if model_timeout <= timedelta(0):
            raise ValueError("model_timeout must be positive")
        self._model = model
        self._parser = parser or StructuredGuidanceParser()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._model_timeout = model_timeout
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="guidance-model")
        self._call_slot = BoundedSemaphore(value=1)

    def process(self, request: HelpRequestResult) -> HelpRequestProcessorOutcome:
        """Generate guidance only for the general route and only after validation."""
        if request.processing_route is not HelpRequestProcessingRoute.GENERAL_GUIDANCE:
            return HelpRequestProcessorOutcome(
                status=HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW,
                review_reason="教程请求必须先通过页面匹配, 模型不能绕过证据门槛.",
            )
        now = self._clock().astimezone(UTC)
        context = ModelGuidanceContext(
            request_id=request.request_id,
            intent=request.intent,
            processing_route=request.processing_route,
            task=GENERAL_GUIDANCE_TASK,
            safety_rules=GENERAL_GUIDANCE_RULES,
            deadline_at=now + self._model_timeout,
        )
        if not self._call_slot.acquire(blocking=False):
            return _review_outcome("模型仍在处理上一项请求, 已转人工复核.")
        future: Future[Mapping[str, object]] | None = None
        try:
            future = self._executor.submit(
                self._model.generate,
                context,
                deadline=context.deadline_at,
            )
            payload = future.result(timeout=self._model_timeout.total_seconds())
        except TimeoutError:
            assert future is not None
            future.cancel()
            future.add_done_callback(lambda _completed: self._call_slot.release())
            return _review_outcome("模型处理超时, 已转人工复核.")
        except Exception:
            self._call_slot.release()
            return _review_outcome("模型调用失败, 已转人工复核.")
        self._call_slot.release()
        try:
            guidance = self._parser.parse(payload)
        except Exception:
            return _review_outcome("模型输出未通过结构化安全校验, 需要人工复核.")
        return HelpRequestProcessorOutcome(
            status=HelpRequestProcessingStatus.GUIDANCE_READY,
            guidance=guidance,
        )

    def shutdown(self) -> None:
        """Release executor resources during application shutdown or isolated tests."""
        self._executor.shutdown(wait=False, cancel_futures=True)


def _review_outcome(reason: str) -> HelpRequestProcessorOutcome:
    return HelpRequestProcessorOutcome(
        status=HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW,
        review_reason=reason,
    )


def _required_string(payload: Mapping[str, object], key: str, *, max_length: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ModelOutputValidationError(
            f"model field {key!r} must be a non-empty string of at most {max_length} characters",
        )
    return value
