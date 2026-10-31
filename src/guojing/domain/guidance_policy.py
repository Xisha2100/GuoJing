"""Pure acceptance rules for an immutable candidate and its bound review."""

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from hashlib import sha256

from guojing.domain.agent_guidance import GuidanceDecision, GuidanceStatus
from guojing.domain.guidance_language import enforce_guidance_language


class GuidanceRisk(StrEnum):
    ORDINARY = "ordinary"
    FINANCIAL = "financial"
    IRREVERSIBLE = "irreversible"
    UNKNOWN = "unknown"


class ReviewIssue(StrEnum):
    NONE = "none"
    WORDING = "wording"
    VISUAL = "visual"
    COMPLETION = "completion"
    RISK = "risk"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class GuidanceCandidate:
    decision: GuidanceDecision
    target_description: str
    evidence: str
    risk: GuidanceRisk

    @property
    def digest(self) -> str:
        payload = json.dumps(
            asdict(self), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return sha256(payload.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class GuidanceReview:
    candidate_digest: str
    approved: bool
    issue: ReviewIssue
    risk: GuidanceRisk
    target_supported: bool
    completion_supported: bool
    feedback: str


def cannot_determine() -> GuidanceDecision:
    return GuidanceDecision(
        GuidanceStatus.CANNOT_DETERMINE,
        "当前界面还不能可靠确定下一步,请保持页面稳定后重新识别。",
        None,
        0.0,
    )


def prevent_unsupported_repeat(
    decision: GuidanceDecision,
    previous: GuidanceDecision,
    *,
    same_image: bool,
) -> GuidanceDecision:
    """Identical pixels and the same proposed action provide no evidence of progress."""
    if (
        same_image
        and decision.status is GuidanceStatus.CONTINUE
        and previous.status is GuidanceStatus.CONTINUE
        and decision.instruction == previous.instruction
        and decision.target == previous.target
    ):
        return cannot_determine()
    return decision


def candidate_is_safe(candidate: GuidanceCandidate, *, threshold: float) -> bool:
    """Conservative checks supplement, rather than replace, visual risk review."""
    decision = candidate.decision
    if decision.status is GuidanceStatus.CANNOT_DETERMINE:
        return False
    if candidate.risk is not GuidanceRisk.ORDINARY or decision.confidence < threshold:
        return False
    if not candidate.evidence.strip():
        return False
    if decision.status is GuidanceStatus.CONTINUE and not candidate.target_description.strip():
        return False
    text = (decision.instruction or "") + candidate.target_description
    blocked = ("支付", "付款", "转账", "汇款", "删除", "注销", "恢复出厂", "授权", "验证码")
    return not any(word in text for word in blocked)


def can_revise(candidate: GuidanceCandidate, review: GuidanceReview, *, threshold: float) -> bool:
    return (
        candidate_is_safe(candidate, threshold=threshold)
        and review.candidate_digest == candidate.digest
        and not review.approved
        and review.issue is ReviewIssue.WORDING
        and review.risk is GuidanceRisk.ORDINARY
        and (
            review.target_supported
            if candidate.decision.status is GuidanceStatus.CONTINUE
            else review.completion_supported
        )
    )


def accept_reviewed_candidate(
    goal: str,
    candidate: GuidanceCandidate,
    review: GuidanceReview,
    *,
    threshold: float,
) -> GuidanceDecision:
    if (
        not candidate_is_safe(candidate, threshold=threshold)
        or review.candidate_digest != candidate.digest
        or not review.approved
        or review.issue is not ReviewIssue.NONE
        or review.risk is not GuidanceRisk.ORDINARY
        or (
            not review.target_supported
            if candidate.decision.status is GuidanceStatus.CONTINUE
            else not review.completion_supported
        )
    ):
        return cannot_determine()
    return enforce_guidance_language(goal, candidate.decision)
