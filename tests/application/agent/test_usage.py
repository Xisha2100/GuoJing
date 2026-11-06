import asyncio

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from guojing.application.agent.usage import ModelCallLimit, ModelUsage
from guojing.infrastructure.agents.usage_callback import UsageCallback


@pytest.mark.asyncio
async def test_models_share_twelve_call_budget_and_admit_only_once() -> None:
    admitted = []
    usage = ModelUsage(lambda: admitted.append(True))
    callback = UsageCallback(usage)
    # Independent main/subagent model instances inherit the same callback object.
    models = [FakeListChatModel(responses=["ok"]) for _ in range(3)]
    await asyncio.gather(
        *[
            models[index % 3].ainvoke("synthetic", config={"callbacks": [callback]})
            for index in range(12)
        ]
    )
    with pytest.raises(ModelCallLimit):
        await models[0].ainvoke("synthetic", config={"callbacks": [callback]})
    assert usage.calls == 12 and admitted == [True]


def test_late_model_call_cannot_start_after_run_has_finished() -> None:
    usage = ModelUsage(lambda: None)
    usage.closed = True
    with pytest.raises(ModelCallLimit):
        usage.begin_call()
    assert usage.calls == 0


@pytest.mark.asyncio
async def test_concurrent_model_callbacks_do_not_repeat_slow_first_admission() -> None:
    from threading import Event

    entered, release = Event(), Event()
    admitted: list[bool] = []

    def admit() -> None:
        admitted.append(True)
        entered.set()
        assert release.wait(2)

    usage = ModelUsage(admit)
    callback = UsageCallback(usage)
    tasks = [asyncio.create_task(callback.on_chat_model_start()) for _ in range(14)]
    try:
        while not entered.is_set():
            await asyncio.sleep(0.001)
        await asyncio.sleep(0.01)
        assert admitted == [True]
    finally:
        release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
    assert usage.calls == 12
    assert sum(isinstance(result, ModelCallLimit) for result in results) == 2
