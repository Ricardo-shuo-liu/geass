"""定时系统：用户在指定时间执行指定命令。

任务保存在 ``~/.geass/.schedule/jobs.json``，由服务端后台轮询触发；到期后
复用与手动命令相同的 Agent 启动流程。若当时已有任务在运行，则该定时任务
延迟几秒重试，而不是直接失败。
"""
# 包化后的对外入口：保持 from geass.scheduler import Scheduler 等兼容。
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

POLL_INTERVAL = 1.0
BUSY_RETRY_SECONDS = 5.0

StatusCallback = Callable[[dict[str, Any]], Awaitable[None]]
RunCallback = Callable[[str], Awaitable[dict[str, Any]]]


def default_schedule_path() -> Path:
    home = Path(os.environ.get("GEASS_HOME", str(Path.home())))
    return home / ".geass" / ".schedule"


@dataclass
class ScheduledJob:
    id: str
    command: str
    run_at: float
    created_at: float
    persistent: bool = False
    status: str = "pending"
    retry_at: float = 0.0
    message: str = ""
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScheduleStore:
    """定时任务的 JSON 持久化存储，目录下单个 ``jobs.json``。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self.dir = Path(path) if path else default_schedule_path()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "jobs.json"
        self._lock = threading.RLock()
        self._jobs: dict[str, ScheduledJob] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("定时任务读取失败，使用空列表：%s", exc)
            return
        raw = data.get("jobs") if isinstance(data, dict) else data
        if not isinstance(raw, list):
            return
        for item in raw:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            job = ScheduledJob(
                id=str(item["id"]),
                command=str(item.get("command") or ""),
                run_at=float(item.get("run_at") or 0),
                created_at=float(item.get("created_at") or time.time()),
                # 旧版本写入的任务默认视为长期任务，继续保留跨重启行为
                persistent=bool(item.get("persistent", True)),
                status=str(item.get("status") or "pending"),
                retry_at=float(item.get("retry_at") or 0),
                message=str(item.get("message") or ""),
                updated_at=float(item.get("updated_at") or time.time()),
            )
            self._jobs[job.id] = job

    def _save(self) -> None:
        payload = {
            "version": 1,
            "jobs": [
                job.to_dict()
                for job in self._sorted()
                if job.persistent
            ],
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    def _sorted(self) -> list[ScheduledJob]:
        return sorted(
            self._jobs.values(),
            key=lambda job: (job.run_at, job.created_at),
        )

    def add(
        self,
        command: str,
        run_at: float,
        persistent: bool = False,
    ) -> ScheduledJob:
        command = str(command or "").strip()
        if not command:
            raise ValueError("定时命令不能为空")
        run_at = float(run_at)
        if run_at <= time.time():
            raise ValueError("执行时间必须晚于当前时间")
        now = time.time()
        job = ScheduledJob(
            id=uuid.uuid4().hex,
            command=command[:2000],
            run_at=run_at,
            created_at=now,
            persistent=bool(persistent),
        )
        with self._lock:
            self._jobs[job.id] = job
            self._save()
        return job

    def get(self, job_id: str) -> ScheduledJob | None:
        with self._lock:
            return self._jobs.get(str(job_id))

    def list(self, include_done: bool = True) -> list[ScheduledJob]:
        with self._lock:
            jobs = self._sorted()
        if include_done:
            return jobs
        return [job for job in jobs if job.status == "pending"]

    def remove(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.pop(str(job_id), None)
            if job is None:
                return False
            self._save()
        return True

    def update(
        self,
        job: ScheduledJob,
        *,
        status: str | None = None,
        retry_at: float | None = None,
        message: str | None = None,
    ) -> None:
        with self._lock:
            if status is not None:
                job.status = status
            if retry_at is not None:
                job.retry_at = retry_at
            if message is not None:
                job.message = message
            job.updated_at = time.time()
            self._save()


class Scheduler:
    """后台轮询到期的定时任务并交给 ``run_job`` 执行。"""

    def __init__(
        self,
        store: ScheduleStore,
        run_job: RunCallback,
        status_cb: StatusCallback | None = None,
    ) -> None:
        self.store = store
        self.run_job = run_job
        self.status_cb = status_cb
        self._running: set[str] = set()

    async def _emit(self, message: dict[str, Any]) -> None:
        if self.status_cb is not None:
            try:
                await self.status_cb(message)
            except Exception:
                logger.warning("定时状态广播失败", exc_info=True)

    async def run(self, cancel: asyncio.Event | None = None) -> None:
        cancel = cancel or asyncio.Event()
        while True:
            try:
                await asyncio.wait_for(cancel.wait(), timeout=POLL_INTERVAL)
                return
            except asyncio.TimeoutError:
                pass

            now = time.time()
            for job in self.store.list(include_done=False):
                if job.id in self._running:
                    continue
                if job.retry_at and job.retry_at > now:
                    continue
                if job.run_at > now:
                    continue
                try:
                    await self._execute(job)
                except Exception:
                    logger.exception("定时任务处理失败：%s", job.id)

    async def _execute(self, job: ScheduledJob) -> None:
        self._running.add(job.id)
        self.store.update(job, status="running", message="")
        await self._emit(
            {
                "type": "schedule_status",
                "job": job.to_dict(),
                "message": f"定时任务开始执行：{job.command}",
            }
        )
        try:
            result = await self.run_job(job.command)
        except Exception as exc:
            self.store.update(job, status="error", message=str(exc))
            await self._emit(
                {
                    "type": "schedule_status",
                    "job": job.to_dict(),
                    "message": f"定时任务失败：{exc}",
                }
            )
            return
        finally:
            self._running.discard(job.id)

        if result.get("busy"):
            self.store.update(
                job,
                status="pending",
                retry_at=time.time() + BUSY_RETRY_SECONDS,
                message="已有任务在运行，稍后重试",
            )
            await self._emit(
                {
                    "type": "schedule_status",
                    "job": job.to_dict(),
                    "message": f"定时任务延迟重试：{job.command}",
                }
            )
            return

        if result.get("ok") is False:
            self.store.update(
                job,
                status="error",
                message=str(result.get("error") or "执行失败"),
            )
        else:
            self.store.update(
                job,
                status="done",
                message=str(result.get("message") or "完成"),
            )
        await self._emit(
            {
                "type": "schedule_status",
                "job": job.to_dict(),
                "message": f"定时任务{job.status}：{job.command}",
            }
        )
