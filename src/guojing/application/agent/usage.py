"""Per-execution accounting shared by the main model and its subagents."""

from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass


class ModelCallLimit(RuntimeError):
    pass


@dataclass
class ModelUsage:
    before_first_call: Callable[[], None]
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    closed: bool = False

    def begin_call(self) -> None:
        if self.closed or self.calls >= 12:
            raise ModelCallLimit("model_call_limit")
        if self.calls == 0:
            self.before_first_call()
        self.calls += 1


current_usage: ContextVar[ModelUsage | None] = ContextVar("model_usage", default=None)
