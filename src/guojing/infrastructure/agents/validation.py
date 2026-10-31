"""Fail closed unless both specialists returned valid results in sequence."""

import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from guojing.application.agent.usage import ModelUsage
from guojing.infrastructure.agents.harness import GuidanceRejected, GuidanceToolGuard
from guojing.infrastructure.agents.outputs import (
    GuidanceCandidateOutput,
    GuidanceDecisionOutput,
    GuidanceReviewOutput,
    UiAnalysisOutput,
)


class FixedDelegationGuard(GuidanceToolGuard):
    """Validate each delegation before running it and bind the reviewed candidate."""

    def __init__(self, goal: str, usage: ModelUsage | None = None) -> None:
        super().__init__("GuidanceDecisionOutput", model_calls=3, usage=usage, stage="main")
        self.goal = goal
        self.completed = 0
        self.pending = False
        self.seen_ids: set[str] = set()
        self.analysis: UiAnalysisOutput | None = None
        self.candidate: GuidanceCandidateOutput | None = None
        self.review: GuidanceReviewOutput | None = None

    def allowed_tools(self) -> set[str]:
        return {"task"} if self.completed < 2 else {self.output_name}

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        call = request.tool_call
        call_id = call.get("id")
        arguments = call["args"]
        description = arguments.get("description")
        expected = ("ui-analyst", "guidance-reviewer")
        if (
            call["name"] != "task"
            or self.pending
            or self.completed >= 2
            or arguments.get("subagent_type") != expected[self.completed]
            or set(arguments) != {"subagent_type", "description"}
            or not isinstance(description, str)
            or not description.strip()
            or not call_id
            or call_id in self.seen_ids
        ):
            raise GuidanceRejected("invalid_delegation")
        self.pending = True
        self.seen_ids.add(call_id)
        if self.completed == 1:
            self.candidate = GuidanceCandidateOutput.model_validate_json(description)
            if self.analysis is None:
                raise GuidanceRejected("missing_analysis")
            description = json.dumps(
                {
                    "goal": self.goal,
                    "analysis": self.analysis.model_dump(),
                    "candidate": self.candidate.model_dump(),
                    "candidate_digest": self.candidate.candidate().digest,
                },
                ensure_ascii=False,
            )
            request = request.override(
                tool_call={**call, "args": {**call["args"], "description": description}}
            )
        response = await handler(request)
        message = _tool_result(response, call_id)
        if message.status == "error" or not isinstance(message.content, str):
            raise GuidanceRejected("invalid_subagent_result")
        if self.completed == 0:
            self.analysis = UiAnalysisOutput.model_validate_json(message.content)
        else:
            self.review = GuidanceReviewOutput.model_validate_json(message.content)
            if (
                self.candidate is None
                or self.review.candidate_digest != self.candidate.candidate().digest
            ):
                raise GuidanceRejected("review_candidate_mismatch")
        self.completed += 1
        self.pending = False
        return response

    def require_unchanged_candidate(self, output: GuidanceDecisionOutput) -> None:
        if self.completed != 2 or self.candidate is None or self.review is None:
            raise GuidanceRejected("missing_review")
        if output.to_domain() != self.candidate.to_domain():
            raise GuidanceRejected("candidate_changed_after_review")


def _tool_result(response: ToolMessage | Command[Any], call_id: str) -> ToolMessage:
    if isinstance(response, ToolMessage):
        messages = [response]
    elif isinstance(response.update, dict):
        messages = response.update.get("messages", [])
    else:
        raise GuidanceRejected("missing_tool_result")
    if (
        len(messages) != 1
        or not isinstance(messages[0], ToolMessage)
        or messages[0].tool_call_id != call_id
    ):
        raise GuidanceRejected("invalid_tool_result")
    return messages[0]


def require_fixed_subagents(result: Mapping[str, Any]) -> None:
    expected = ("ui-analyst", "guidance-reviewer")
    completed = 0
    pending: str | None = None
    seen_ids: set[str] = set()
    for message in result.get("messages", []):
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                if call.get("name") != "task":
                    continue
                name = call.get("args", {}).get("subagent_type")
                call_id = call.get("id")
                if (
                    pending is not None
                    or completed >= len(expected)
                    or name != expected[completed]
                    or not call_id
                    or call_id in seen_ids
                ):
                    raise GuidanceRejected("invalid_delegation_order")
                pending = call_id
                seen_ids.add(call_id)
        elif isinstance(message, ToolMessage) and message.tool_call_id in seen_ids:
            if message.tool_call_id != pending or message.status == "error":
                raise GuidanceRejected("invalid_delegation_result")
            if not isinstance(message.content, str):
                raise GuidanceRejected("invalid_delegation_output")
            schema = UiAnalysisOutput if completed == 0 else GuidanceReviewOutput
            schema.model_validate_json(message.content)
            completed += 1
            pending = None
    if completed != len(expected) or pending is not None:
        raise GuidanceRejected("incomplete_delegation")
