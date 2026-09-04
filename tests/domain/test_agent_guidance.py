import pytest

from guojing.domain.agent_guidance import (
    GuidanceDecision,
    GuidanceStatus,
    NormalizedTarget,
)


def test_continue_requires_a_target() -> None:
    with pytest.raises(ValueError, match="requires a target"):
        GuidanceDecision(
            status=GuidanceStatus.CONTINUE,
            instruction="点击按钮",
            target=None,
            confidence=0.9,
        )


def test_target_rejects_inverted_coordinates() -> None:
    with pytest.raises(ValueError, match="positive rectangle"):
        NormalizedTarget(left=0.8, top=0.1, right=0.2, bottom=0.3)


def test_completed_result_rejects_target() -> None:
    with pytest.raises(ValueError, match="must not contain"):
        GuidanceDecision(
            status=GuidanceStatus.COMPLETED,
            instruction="已经完成",
            target=NormalizedTarget(left=0.1, top=0.1, right=0.2, bottom=0.2),
            confidence=1.0,
        )


@pytest.mark.parametrize(
    "status",
    [GuidanceStatus.COMPLETED, GuidanceStatus.CANNOT_DETERMINE],
)
def test_terminal_results_are_valid_without_target(status: GuidanceStatus) -> None:
    result = GuidanceDecision(
        status=status,
        instruction="已经完成" if status is GuidanceStatus.COMPLETED else "请保持页面稳定后重试",
        target=None,
        confidence=0.8,
    )

    assert result.status is status
    assert result.target is None
