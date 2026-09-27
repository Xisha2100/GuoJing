"""In-memory, numeric-only accounting; never exports model messages."""

from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from guojing.application.agent.usage import ModelUsage


class UsageCallback(AsyncCallbackHandler):
    raise_error = True

    def __init__(self, usage: ModelUsage) -> None:
        self.usage = usage

    async def on_chat_model_start(self, *args: Any, **kwargs: Any) -> None:
        self.usage.begin_call()

    async def on_llm_start(self, *args: Any, **kwargs: Any) -> None:
        self.usage.begin_call()

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        tokens = (response.llm_output or {}).get("token_usage", {})
        input_tokens = int(tokens.get("prompt_tokens", 0))
        output_tokens = int(tokens.get("completion_tokens", 0))
        if not input_tokens and not output_tokens:
            for group in response.generations:
                for generation in group:
                    metadata = getattr(getattr(generation, "message", None), "usage_metadata", None)
                    if isinstance(metadata, dict):
                        input_tokens += int(metadata.get("input_tokens", 0))
                        output_tokens += int(metadata.get("output_tokens", 0))
        self.usage.input_tokens += input_tokens
        self.usage.output_tokens += output_tokens
