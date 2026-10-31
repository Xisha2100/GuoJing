from typing import Any

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from guojing.infrastructure.agents.validation import require_fixed_subagents

ANALYSIS = '{"current_page":"首页","visible_controls":[],"likely_target":null,"summary":"说明"}'
REVIEW = (
    '{"candidate_digest":"' + "a" * 64 + '","approved":true,"issue":"none",'
    '"risk":"ordinary","target_supported":true,"completion_supported":false,"feedback":"可用"}'
)


def call(name: str, call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "task", "args": {"subagent_type": name}, "id": call_id}],
    )


def valid_messages() -> list[Any]:
    return [
        call("ui-analyst", "one"),
        ToolMessage(content=ANALYSIS, tool_call_id="one"),
        call("guidance-reviewer", "two"),
        ToolMessage(content=REVIEW, tool_call_id="two"),
    ]


def test_requires_completed_structured_subagent_results() -> None:
    require_fixed_subagents({"messages": valid_messages()})


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [call("ui-analyst", "one"), call("guidance-reviewer", "two")],
        valid_messages()[:3],
        [call("guidance-reviewer", "one")],
        [call("general-purpose", "one")],
        [*valid_messages(), call("ui-analyst", "three")],
        [valid_messages()[0], valid_messages()[2], valid_messages()[1], valid_messages()[3]],
        [valid_messages()[0], ToolMessage(content=ANALYSIS, tool_call_id="wrong")],
        [valid_messages()[0], ToolMessage(content=ANALYSIS, tool_call_id="one", status="error")],
        [valid_messages()[0], ToolMessage(content="not JSON", tool_call_id="one")],
        [valid_messages()[0], ToolMessage(content=REVIEW, tool_call_id="one")],
        [*valid_messages(), valid_messages()[3]],
        [*valid_messages()[:2], call("guidance-reviewer", "one")],
    ],
)
def test_rejects_incomplete_failed_repeated_or_out_of_order_calls(messages: list[Any]) -> None:
    with pytest.raises(ValueError):
        require_fixed_subagents({"messages": messages})
