"""A no-model processor used to exercise the request lifecycle safely."""

from dataclasses import dataclass
from typing import Protocol

from guojing.application.help_requests.processor import HelpRequestProcessorOutcome
from guojing.domain.help_requests import (
    HelpRequestGuidance,
    HelpRequestGuidanceStep,
    HelpRequestProcessingRoute,
    HelpRequestProcessingStatus,
    HelpRequestResult,
)


class GuidanceCatalog(Protocol):
    """Source of reviewed, non-executable fallback instructions."""

    def general_guidance(self) -> HelpRequestGuidance:
        """Return the currently published generic help sequence."""


@dataclass(frozen=True, slots=True)
class DefaultGuidanceCatalog:
    """Small reviewed fallback catalog for screenshots without a tutorial match."""

    def general_guidance(self) -> HelpRequestGuidance:
        return HelpRequestGuidance(
            title="先确认当前页面",
            steps=(
                HelpRequestGuidanceStep(
                    step_id="identify-screen",
                    title="看清当前页面",
                    instruction="请你先观察屏幕顶部的应用名称和页面标题、再决定是否继续。",
                ),
                HelpRequestGuidanceStep(
                    step_id="pause-sensitive",
                    title="遇到敏感页面先暂停",
                    instruction="如果页面出现密码、验证码、余额或账户操作提示、请先停止操作并联系家人确认。",
                ),
                HelpRequestGuidanceStep(
                    step_id="describe-next-action",
                    title="描述想完成的事情",
                    instruction="回到老牌子、用一句话描述你想完成的事情、我们再给出下一步说明。",
                ),
            ),
        )


class DeterministicHelpRequestProcessor:
    """Route requests without a model, screenshot, or hidden side effect.

    Recorded-tutorial requests intentionally stop for review because the image
    is not retained by the upload contract. General guidance can use the small
    reviewed catalog and is safe to publish as manual explanation only.
    """

    def __init__(self, catalog: GuidanceCatalog | None = None) -> None:
        self._catalog = catalog or DefaultGuidanceCatalog()

    def process(self, request: HelpRequestResult) -> HelpRequestProcessorOutcome:
        if request.processing_route is HelpRequestProcessingRoute.TUTORIAL_MATCH:
            return HelpRequestProcessorOutcome(
                status=HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW,
                review_reason=(
                    "已发布教程匹配需要当前页面证据。上传契约已丢弃图片、暂不能自动匹配。"
                ),
            )
        return HelpRequestProcessorOutcome(
            status=HelpRequestProcessingStatus.GUIDANCE_READY,
            guidance=self._catalog.general_guidance(),
        )
