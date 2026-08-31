"""A narrow port for a future LangChain Deep Agent integration."""

from collections.abc import Callable, Mapping
from datetime import datetime
from inspect import signature
from typing import Protocol, cast

from guojing.application.help_requests.model_adapter import GuidanceModel, ModelGuidanceContext


class DeepAgentInvoker(Protocol):
    """The only Deep Agent capability needed by this bounded guidance adapter."""

    def invoke(self, payload: Mapping[str, object]) -> Mapping[str, object]: ...


class DeepAgentGuidanceModel(GuidanceModel):
    """Pass metadata-only context to an agent; device tools are intentionally absent."""

    def __init__(self, invoker: DeepAgentInvoker) -> None:
        self._invoker = invoker

    def generate(
        self,
        context: ModelGuidanceContext,
        *,
        deadline: datetime,
    ) -> Mapping[str, object]:
        payload = {
            "task": context.task,
            "safety_rules": list(context.safety_rules),
            "output_schema": {"action_ids": "1-20 approved action identifiers"},
        }
        if context.question is not None:
            payload["question"] = context.question
        # Keep compatibility with older local adapters while ensuring new
        # adapters receive the actual deadline instead of silently ignoring it.
        if "deadline" in signature(self._invoker.invoke).parameters:
            invoke_with_deadline = cast(Callable[..., Mapping[str, object]], self._invoker.invoke)
            return invoke_with_deadline(payload, deadline=deadline)
        return self._invoker.invoke(payload)
