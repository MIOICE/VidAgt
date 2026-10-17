from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any

_event_loop_state = threading.local()


class _LoopRunner:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        self._ready.wait()

    def _serve(self) -> None:
        asyncio.set_event_loop(self.loop)
        self._ready.set()
        self.loop.run_forever()

    def run[T](self, coroutine: Coroutine[Any, Any, T]) -> T:
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result()


def run_async[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Run async work on one persistent background loop per worker thread.

    Celery tasks run synchronously, while SQLAlchemy and HTTP clients may retain
    loop-bound connection pools between tasks. Reusing the worker thread's loop
    prevents those resources from being attached to a closed loop.
    """
    runner = getattr(_event_loop_state, "runner", None)
    if runner is None or runner.loop.is_closed():
        runner = _LoopRunner()
        _event_loop_state.runner = runner
    return runner.run(coroutine)
