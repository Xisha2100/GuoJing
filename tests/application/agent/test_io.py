import asyncio
from threading import Event

import pytest

from guojing.application.agent.io import run_db


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_blocking_operation_does_not_block_loop_and_cancellation_waits_for_cleanup(
    fail: bool,
) -> None:
    entered, release = Event(), Event()

    def transaction() -> None:
        entered.set()
        assert release.wait(2)
        if fail:
            raise RuntimeError("transaction failed during cancellation")

    task = asyncio.create_task(run_db(transaction))
    try:
        while not entered.is_set():
            await asyncio.sleep(0.001)
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
