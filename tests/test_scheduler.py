from __future__ import annotations

import asyncio
import time

import pytest

from geass.scheduler import Scheduler, ScheduleStore


def test_store_add_list_remove_and_persist(tmp_path):
    store = ScheduleStore(tmp_path / ".schedule")
    job = store.add("打开浏览器", time.time() + 60, persistent=True)

    assert store.get(job.id).command == "打开浏览器"
    assert store.list() == [job]

    reloaded = ScheduleStore(tmp_path / ".schedule")
    assert reloaded.get(job.id).command == "打开浏览器"
    assert reloaded.remove(job.id) is True
    assert reloaded.remove(job.id) is False


def test_non_persistent_jobs_are_not_saved(tmp_path):
    store = ScheduleStore(tmp_path / ".schedule")
    store.add("临时任务", time.time() + 60)
    store.add("长期任务", time.time() + 60, persistent=True)

    reloaded = ScheduleStore(tmp_path / ".schedule")

    assert [job.command for job in reloaded.list()] == ["长期任务"]


def test_store_rejects_empty_or_past_jobs(tmp_path):
    store = ScheduleStore(tmp_path / ".schedule")

    with pytest.raises(ValueError, match="不能为空"):
        store.add("  ", time.time() + 60)
    with pytest.raises(ValueError, match="晚于"):
        store.add("命令", time.time() - 1)


def test_scheduler_executes_due_job(tmp_path):
    store = ScheduleStore(tmp_path / ".schedule")
    job = store.add("任务", time.time() + 60)
    job.run_at = time.time() - 0.1
    store._save()
    calls = []

    async def run_job(command):
        calls.append(command)
        return {"ok": True, "message": "完成"}

    scheduler = Scheduler(store, run_job)
    run_scheduler_once(scheduler)

    assert calls == ["任务"]
    assert store.get(job.id).status == "done"


def test_scheduler_retries_when_busy(tmp_path):
    store = ScheduleStore(tmp_path / ".schedule")
    job = store.add("任务", time.time() + 60)
    job.run_at = time.time() - 0.1
    store._save()

    async def run_job(command):
        return {"ok": False, "busy": True, "error": "忙"}

    scheduler = Scheduler(store, run_job)
    run_scheduler_once(scheduler)

    assert store.get(job.id).status == "pending"
    assert store.get(job.id).retry_at > time.time()


def run_scheduler_once(scheduler: Scheduler) -> None:
    import geass.scheduler as scheduler_module

    original_interval = scheduler_module.POLL_INTERVAL
    scheduler_module.POLL_INTERVAL = 0.01

    async def main():
        cancel = asyncio.Event()
        task = asyncio.create_task(scheduler.run(cancel))
        await asyncio.sleep(0.08)
        cancel.set()
        await task

    try:
        asyncio.run(main())
    finally:
        scheduler_module.POLL_INTERVAL = original_interval
