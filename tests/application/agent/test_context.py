from datetime import UTC, datetime
from uuid import uuid4

import pytest

from guojing.application.agent.context import history_context, run_context
from guojing.domain.agent_guidance import GuidanceDecision, GuidanceStatus, GuidanceStep
from tests.infrastructure.agents.test_deepagents_compatibility import session


def steps() -> list[GuidanceStep]:
    return [
        GuidanceStep(
            uuid4(),
            uuid4(),
            i,
            GuidanceDecision(
                GuidanceStatus.CANNOT_DETERMINE,
                "完整说明" * 30,
                None,
                0.0,
            ),
            datetime.now(UTC),
        )
        for i in range(10)
    ]


def test_history_retains_only_recent_complete_issued_instructions() -> None:
    selected = history_context(steps())
    assert [item["step"] for item in selected] == [4, 5, 6, 7, 8, 9]
    assert all(item["instruction"] == "完整说明" * 30 for item in selected)
    limited = history_context(steps(), maximum_characters=250)
    assert len(limited) == 1 and limited[0]["step"] == 9


def test_context_distinguishes_issued_guidance_from_actions_and_preserves_goal() -> None:
    context = run_context(session("找到蓝牙"), steps())
    assert "previous_issued_guidance" in context
    assert "validated" not in context
    assert "找到蓝牙" in context


def test_invalid_history_budget_is_rejected() -> None:
    with pytest.raises(ValueError):
        history_context([], maximum_steps=0)
