from __future__ import annotations

import asyncio
from types import SimpleNamespace

from geass.server.task_manager import BackgroundTaskManager


class FakeAgent:
    def __init__(self) -> None:
        self.last_trace = {"command": "x", "result": "ok"}

    async def run(self, command, cancel=None):
        cancel = cancel or asyncio.Event()
        for _ in range(50):
            if cancel.is_set():
                return {"state": "cancelled", "message": "已取消"}
            await asyncio.sleep(0.01)
        return {"state": "done", "message": "完成"}


def make_state():
    return SimpleNamespace(control_clients=set(), evolution=None)


def test_task_manager_start_list_and_finish(tmp_path):
    async def main():
        manager = BackgroundTaskManager(
            make_state(),
            agent_factory=FakeAgent,
            max_tasks=2,
            path=tmp_path / ".tasks",
        )
        result = manager.start("后台任务")
        assert result["ok"] is True
        task_id = result["task_id"]

        for _ in range(100):
            task = next(
                item for item in manager.list() if item["id"] == task_id
            )
            if task["status"] == "done":
                assert task["result"]["message"] == "完成"
                assert manager.tasks_active() is False
                return
            await asyncio.sleep(0.02)
        raise AssertionError("后台任务未完成")

    asyncio.run(main())


def test_task_manager_cancel(tmp_path):
    async def main():
        manager = BackgroundTaskManager(
            make_state(),
            agent_factory=FakeAgent,
            max_tasks=2,
            path=tmp_path / ".tasks",
        )
        result = manager.start("可取消任务")
        task_id = result["task_id"]
        assert manager.tasks_active() is True
        assert manager.cancel(task_id) is True

        for _ in range(100):
            task = next(
                item for item in manager.list() if item["id"] == task_id
            )
            if task["status"] == "cancelled":
                return
            await asyncio.sleep(0.02)
        raise AssertionError("后台任务未取消")

    asyncio.run(main())


def test_task_manager_persists_and_interrupts(tmp_path):
    async def main():
        manager = BackgroundTaskManager(
            make_state(),
            agent_factory=FakeAgent,
            max_tasks=2,
            path=tmp_path / ".tasks",
        )
        manager.start("持久任务")

        reloaded = BackgroundTaskManager(
            make_state(),
            agent_factory=FakeAgent,
            max_tasks=2,
            path=tmp_path / ".tasks",
        )
        tasks = reloaded.list()
        assert tasks and tasks[0]["status"] == "interrupted"

    asyncio.run(main())


def test_task_manager_max_tasks(tmp_path):
    async def main():
        manager = BackgroundTaskManager(
            make_state(),
            agent_factory=FakeAgent,
            max_tasks=1,
            path=tmp_path / ".tasks",
        )
        manager.start("任务一")
        second = manager.start("任务二")
        assert second["ok"] is False
        assert "上限" in second["error"]

    asyncio.run(main())
