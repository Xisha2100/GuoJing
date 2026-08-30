"""Catalog resolution for approved guidance references."""

from collections.abc import Iterable

from guojing.domain.guidance_actions import (
    ApprovedGuidanceAction,
    GuidanceAuthorization,
    authorize_guidance_action,
)
from guojing.domain.help_requests import HelpRequestGuidance, HelpRequestGuidanceStep
from guojing.domain.tutorials.models import RiskLevel


class UnknownGuidanceAction(ValueError):
    """Raised when a model or caller references an action outside the catalog."""


class GuidanceActionCatalog:
    """Resolve reviewed action IDs into manual text after deterministic authorization."""

    def __init__(self, actions: Iterable[ApprovedGuidanceAction]) -> None:
        values = tuple(actions)
        indexed = {action.action_id: action for action in values}
        if not indexed:
            raise ValueError("guidance action catalog must not be empty")
        if len(indexed) != len(values):
            raise ValueError("guidance action ids must be unique")
        self._actions = indexed

    def resolve(self, action_ids: tuple[str, ...]) -> HelpRequestGuidance:
        """Return only low-risk catalog actions; all other references fail closed."""
        if not 1 <= len(action_ids) <= 20:
            raise UnknownGuidanceAction("guidance must reference 1 to 20 approved actions")
        actions = tuple(self._resolve_one(action_id) for action_id in action_ids)
        return HelpRequestGuidance(
            title="安全操作说明",
            steps=tuple(
                HelpRequestGuidanceStep(
                    step_id=action.action_id,
                    title=action.title,
                    instruction=action.instruction,
                )
                for action in actions
            ),
        )

    def _resolve_one(self, action_id: str) -> ApprovedGuidanceAction:
        action = self._actions.get(action_id)
        if action is None:
            raise UnknownGuidanceAction("guidance references an unknown approved action")
        authorization = authorize_guidance_action(action.risk_level)
        if authorization is not GuidanceAuthorization.ALLOW:
            raise UnknownGuidanceAction(
                f"guidance action requires {authorization.value}",
            )
        return action


def default_guidance_action_catalog() -> GuidanceActionCatalog:
    """Small reviewed fallback catalog for general, non-financial help."""
    return GuidanceActionCatalog(
        (
            ApprovedGuidanceAction(
                action_id="general.observe_page",
                title="先看清页面",
                instruction="请先观察屏幕顶部的应用名称和页面标题, 再决定是否继续。",
                risk_level=RiskLevel.LOW,
            ),
            ApprovedGuidanceAction(
                action_id="general.stop_for_sensitive_prompt",
                title="遇到敏感提示先停下",
                instruction=(
                    "如果页面出现密码、验证码、余额或账户操作提示, 请先停止操作并联系家人确认。"
                ),
                risk_level=RiskLevel.LOW,
            ),
            ApprovedGuidanceAction(
                action_id="general.describe_goal",
                title="重新说明目标",
                instruction="回到老牌子, 用一句话描述你想完成的事情, 我们再给出下一步说明。",
                risk_level=RiskLevel.LOW,
            ),
        ),
    )
