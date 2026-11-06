"""Bound blocking use cases without abandoning an in-flight transaction on cancellation."""

import asyncio
from collections.abc import Callable
from functools import partial
from weakref import WeakKeyDictionary

_limits: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = WeakKeyDictionary()


async def run_db[**P, T](function: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    loop = asyncio.get_running_loop()
    limit = _limits.setdefault(loop, asyncio.Semaphore(4))
    async with limit:
        task = asyncio.create_task(asyncio.to_thread(partial(function, *args, **kwargs)))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Keep ownership until the database operation has finished.
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            # A transaction failure must not replace the caller's cancellation.
            try:
                task.result()
            except Exception:
                pass
            raise
