"""Public Deep Agents configuration with a deny-by-default execution boundary."""

from collections.abc import Awaitable, Callable
from functools import cache
from time import monotonic
from typing import Any

from deepagents import (
    FilesystemMiddleware,
    FilesystemPermission,
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    register_harness_profile,
)
from deepagents.backends.protocol import BackendProtocol
from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from guojing.application.agent.usage import ModelUsage


class GuidanceRejected(ValueError):
    """An untrusted model result violated the bounded guidance protocol."""


@cache
def register_guidance_profile(model_name: str) -> None:
    """Register once at construction, never mutate profiles while a run is executing."""
    register_harness_profile(
        f"openai:{model_name}",
        HarnessProfile(
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
            excluded_tools=frozenset(
                {"ls", "read_file", "write_file", "edit_file", "delete", "glob", "grep", "execute"}
            ),
            excluded_middleware=frozenset({"SummarizationMiddleware"}),
        ),
    )


class GuidanceToolGuard(AgentMiddleware[Any, None, Any]):
    """Allow only one typed result per stage; reject invented tools before execution."""

    def __init__(
        self,
        output_name: str,
        *,
        model_calls: int = 1,
        usage: ModelUsage | None = None,
        stage: str = "output",
    ) -> None:
        self.output_name = output_name
        self.maximum_calls = model_calls
        self.calls = 0
        self.usage = usage
        self.stage = stage

    @property
    def name(self) -> str:
        # A fork must replace its parent's guard, not inherit its task permissions.
        return "GuidanceToolGuard"

    def allowed_tools(self) -> set[str]:
        return {self.output_name}

    async def awrap_model_call(
        self,
        request: ModelRequest[None],
        handler: Callable[[ModelRequest[None]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        if self.calls >= self.maximum_calls:
            raise GuidanceRejected("stage_call_limit")
        self.calls += 1
        allowed = self.allowed_tools()
        tools = [
            tool
            for tool in request.tools
            if (tool.get("name") if isinstance(tool, dict) else tool.name) in allowed
        ]
        started = monotonic()
        usage = self.usage
        previous_calls = usage.calls if usage else 0
        input_tokens = usage.input_tokens if usage else 0
        output_tokens = usage.output_tokens if usage else 0
        try:
            response = await handler(request.override(tools=tools))
        finally:
            if usage is not None:
                usage.stages.append(
                    {
                        "stage": self.stage,
                        "model_calls": usage.calls - previous_calls,
                        "input_tokens": usage.input_tokens - input_tokens,
                        "output_tokens": usage.output_tokens - output_tokens,
                        "duration_ms": round((monotonic() - started) * 1000),
                    }
                )
        calls = [
            call for msg in response.result if isinstance(msg, AIMessage) for call in msg.tool_calls
        ]
        if len(calls) != 1 or calls[0]["name"] not in allowed:
            raise GuidanceRejected("unexpected_model_tool")
        if any(isinstance(msg, AIMessage) and msg.invalid_tool_calls for msg in response.result):
            raise GuidanceRejected("invalid_model_tool")
        return response

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        # Structured-output tools are consumed by LangChain's model handler, not
        # executed here. Every other tool is denied, including new upstream tools.
        raise GuidanceRejected("tool_execution_denied")


def file_permissions() -> list[FilesystemPermission]:
    return [FilesystemPermission(operations=["read", "write"], paths=["/**"], mode="deny")]


def file_middleware(backend: BackendProtocol) -> AgentMiddleware[Any, None, Any]:
    # The upstream allowlist requires read_file even when the model cannot use
    # files. The profile hides it and the guard denies execution. Offload is off.
    return FilesystemMiddleware(
        backend=backend,
        tools=["read_file"],
        permissions=file_permissions(),
        tool_token_limit_before_evict=None,
        human_message_token_limit_before_evict=None,
        offload_binary_content=False,
    )
