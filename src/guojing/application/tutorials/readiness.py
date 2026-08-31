"""Release-readiness checks for the first-party tutorial vertical slice."""

from dataclasses import dataclass

from guojing.domain.tutorials.models import (
    PrivacyMode,
    RiskLevel,
    TutorialGraph,
    VerificationStatus,
)


@dataclass(frozen=True, slots=True)
class TutorialReadiness:
    ready: bool
    reasons: tuple[str, ...]


def assess_readiness(graph: TutorialGraph) -> TutorialReadiness:
    reasons: list[str] = []
    if any(node.verification_status is not VerificationStatus.VERIFIED for node in graph.nodes):
        reasons.append("存在未验证页面")
    if any(node.privacy_mode is not PrivacyMode.LOCAL_ONLY for node in graph.nodes):
        reasons.append("存在非本地隐私节点")
    if any(transition.risk_level is not RiskLevel.LOW for transition in graph.transitions):
        reasons.append("存在非低风险步骤")
    return TutorialReadiness(ready=not reasons, reasons=tuple(reasons))
