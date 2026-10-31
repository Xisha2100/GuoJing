"""Bounded context made only from issued guidance, never assumed phone actions."""

import json
from collections.abc import Sequence

from guojing.domain.agent_guidance import AgentSession, GuidanceStep


def history_context(
    history: Sequence[GuidanceStep], *, maximum_steps: int = 6, maximum_characters: int = 4000
) -> list[dict[str, str | int | None]]:
    if maximum_steps < 1 or maximum_characters < 1:
        raise ValueError("history limits must be positive")
    selected: list[dict[str, str | int | None]] = []
    for step in reversed(sorted(history, key=lambda item: item.step_number)[-maximum_steps:]):
        item: dict[str, str | int | None] = {
            "step": step.step_number,
            "status": step.decision.status.value,
            "instruction": step.decision.instruction,
        }
        if len(json.dumps([item, *selected], ensure_ascii=False)) > maximum_characters:
            break
        selected.insert(0, item)
    return selected


def run_context(session: AgentSession, history: Sequence[GuidanceStep]) -> str:
    return json.dumps(
        {
            "goal": session.goal,
            "target_package": session.target_package,
            "previous_issued_guidance": history_context(history),
        },
        ensure_ascii=False,
    )
