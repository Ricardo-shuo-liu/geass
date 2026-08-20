"""不依赖默认线程池的阻塞任务桥接。"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Awaitable, Callable


def run_in_thread(func: Callable[..., Any], *args: Any) -> Awaitable[Any]:
    """在线程中运行阻塞函数，并把结果送回当前事件循环。

    与 `asyncio.to_thread` 功能相同，但使用守护线程，避免部分环境下
    `asyncio.run()` 关闭默认 executor 时长时间等待。
    """
    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()

    def _runner() -> None:
        try:
            result = func(*args)
        except BaseException as exc:
            try:
                loop.call_soon_threadsafe(future.set_exception, exc)
            except RuntimeError:
                pass
        else:
            try:
                loop.call_soon_threadsafe(future.set_result, result)
            except RuntimeError:
                pass

    thread = threading.Thread(
        target=_runner, name="geass-blocking", daemon=True
    )
    thread.start()
    return future
