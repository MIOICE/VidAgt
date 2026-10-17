import asyncio

from app.core.async_runner import run_async


def test_run_async_reuses_worker_event_loop() -> None:
    async def current_loop() -> asyncio.AbstractEventLoop:
        return asyncio.get_running_loop()

    first = run_async(current_loop())
    second = run_async(current_loop())

    assert first is second
    assert not first.is_closed()
