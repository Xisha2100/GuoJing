from dataclasses import replace

import pytest

from guojing.domain.agent_guidance import GuidanceDecision, GuidanceStatus, NormalizedTarget
from guojing.domain.guidance_policy import (
    GuidanceCandidate,
    GuidanceReview,
    GuidanceRisk,
    ReviewIssue,
    accept_reviewed_candidate,
    can_revise,
    prevent_unsupported_repeat,
)


def candidate() -> GuidanceCandidate:
    return GuidanceCandidate(
        GuidanceDecision(
            GuidanceStatus.CONTINUE, "点击设置按钮", NormalizedTarget(0.1, 0.2, 0.3, 0.4), 0.9
        ),
        "设置按钮",
        "可见唯一设置按钮",
        GuidanceRisk.ORDINARY,
    )


def review(value: GuidanceCandidate) -> GuidanceReview:
    return GuidanceReview(
        value.digest, True, ReviewIssue.NONE, GuidanceRisk.ORDINARY, True, False, "可用"
    )


def test_returns_the_exact_frozen_candidate_after_review() -> None:
    value = candidate()
    result = accept_reviewed_candidate("打开设置", value, review(value), threshold=0.7)
    assert result is value.decision


@pytest.mark.parametrize(
    "risk", [GuidanceRisk.FINANCIAL, GuidanceRisk.IRREVERSIBLE, GuidanceRisk.UNKNOWN]
)
def test_each_risk_blocks_guidance_and_revision(risk: GuidanceRisk) -> None:
    value = replace(candidate(), risk=risk)
    verdict = replace(review(value), approved=False, issue=ReviewIssue.WORDING)
    assert not can_revise(value, verdict, threshold=0.7)
    assert accept_reviewed_candidate("打开设置", value, review(value), threshold=0.7).target is None


@pytest.mark.parametrize(
    "issue", [ReviewIssue.VISUAL, ReviewIssue.COMPLETION, ReviewIssue.RISK, ReviewIssue.UNCERTAIN]
)
def test_missing_evidence_cannot_be_repaired_by_repeating_model_calls(issue: ReviewIssue) -> None:
    value = candidate()
    assert not can_revise(value, replace(review(value), approved=False, issue=issue), threshold=0.7)


def test_review_does_not_authorize_changed_instruction_or_bounds() -> None:
    value = candidate()
    modified = replace(value, decision=replace(value.decision, instruction="点击其他按钮"))
    assert modified.digest != value.digest
    assert (
        accept_reviewed_candidate("打开设置", modified, review(value), threshold=0.7).target is None
    )


@pytest.mark.parametrize("instruction", ["点击付款", "点击删除", "输入验证码", "点击授权"])
def test_sensitive_instruction_is_rejected_even_when_model_labels_it_ordinary(
    instruction: str,
) -> None:
    value = candidate()
    value = replace(value, decision=replace(value.decision, instruction=instruction))
    assert accept_reviewed_candidate("打开设置", value, review(value), threshold=0.7).target is None


def test_identical_image_and_repeated_action_cannot_claim_progress() -> None:
    decision = candidate().decision
    assert prevent_unsupported_repeat(decision, decision, same_image=True).target is None
    assert prevent_unsupported_repeat(decision, decision, same_image=False) is decision
    other = replace(decision, instruction="点击搜索按钮")
    assert prevent_unsupported_repeat(other, decision, same_image=True) is other
