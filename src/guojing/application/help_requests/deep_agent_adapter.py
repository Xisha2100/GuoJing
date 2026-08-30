"""A narrow port for a future LangChain Deep Agent integration."""

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

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
        del deadline
        return self._invoker.invoke(
            {
                "task": context.task,
                "safety_rules": list(context.safety_rules),
                "output_schema": {"action_ids": "1-20 approved action identifiers"},
            },
        )
