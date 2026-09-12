import pytest

from guojing.domain.agent_guidance import GuidanceDecision, GuidanceStatus, NormalizedTarget
from guojing.domain.guidance_language import allows_english, enforce_guidance_language


@pytest.mark.parametrize(
    ("goal", "expected"),
    [("找到搜索框123", False), ("搜索 OpenAI", True), ("打开Ｃｈｒｏｍｅ", True)],
)
def test_only_user_goal_letters_enable_english(goal: str, expected: bool) -> None:
    assert allows_english(goal) is expected


@pytest.mark.parametrize("status", list(GuidanceStatus))
@pytest.mark.parametrize("instruction", ["Click Search", "点击 Search", "点击Ｓｅａｒｃｈ"])
def test_english_is_blocked_in_every_status(status: GuidanceStatus, instruction: str) -> None:
    decision = GuidanceDecision(
        status=status,
        instruction=instruction,
        target=NormalizedTarget(0.1, 0.1, 0.2, 0.2) if status is GuidanceStatus.CONTINUE else None,
        confidence=0.95,
    )
    result = enforce_guidance_language("找到搜索框", decision)
    assert result.status is GuidanceStatus.CANNOT_DETERMINE
    assert result.target is None
    assert result.instruction == "本次指引未能生成中文说明,请重新识别。"


@pytest.mark.parametrize("instruction", [None, "目标已完成", "点击右侧第2个按钮"])
def test_chinese_and_absent_instructions_are_preserved(instruction: str | None) -> None:
    decision = GuidanceDecision(GuidanceStatus.COMPLETED, instruction, None, 0.9)
    assert enforce_guidance_language("找到搜索框", decision) is decision
