"""后台任务管理器：独立 Agent 并发执行，键鼠动作通过全局输入锁串行。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TASK_RECORD_LIMIT = 200


def default_tasks_path() -> Path:
    home = Path(os.environ.get("GEASS_HOME", str(Path.home())))
    return home / ".geass" / ".tasks"


@dataclass
class BackgroundTask:
    id: str
    command: str
    created_at: float
    started_at: float = 0.0
    finished_at: float = 0.0
    status: str = "pending"
    message: str = ""
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BackgroundTaskManager:
    def __init__(
        self,
        state: Any,
        agent_factory: Callable[[], Any] | None = None,
        max_tasks: int = 10,
        path: str | Path | None = None,
        enabled: bool = True,
    ) -> None:
        self.state = state
        self.agent_factory = agent_factory
        self.max_tasks = max(1, int(max_tasks))
        self.enabled = enabled
        self.dir = Path(path) if path else default_tasks_path()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "tasks.jsonl"
        self._lock = threading.RLock()
        self._tasks: dict[str, BackgroundTask] = {}
        self._agents: dict[str, Any] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        changed = False
        for line in lines:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict) or not item.get("id"):
                continue
            task = BackgroundTask(
                id=str(item["id"]),
                command=str(item.get("command") or ""),
                created_at=float(item.get("created_at") or time.time()),
                started_at=float(item.get("started_at") or 0),
                finished_at=float(item.get("finished_at") or 0),
                status=str(item.get("status") or "pending"),
                message=str(item.get("message") or ""),
                result=item.get("result"),
            )
            if task.status in ("pending", "running"):
                task.status = "interrupted"
                task.message = "服务重启中断"
                changed = True
            self._tasks[task.id] = task
        if changed:
            self._save()

    def _save(self) -> None:
        records = sorted(self._tasks.values(), key=lambda task: task.created_at, reverse=True)[
            :TASK_RECORD_LIMIT
        ]
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            "\n".join(json.dumps(task.to_dict(), ensure_ascii=False) for task in records)
            + ("\n" if records else ""),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    def active_count(self) -> int:
        with self._lock:
            return sum(
                1
                for task in self._tasks.values()
                if task.status in ("pending", "running", "cancelling")
            )

    def tasks_active(self) -> bool:
        return self.active_count() > 0

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            tasks = sorted(
                self._tasks.values(),
                key=lambda task: task.created_at,
                reverse=True,
            )
        return [task.to_dict() for task in tasks]

    def start(self, command: str) -> dict[str, Any]:
        command = str(command or "").strip()
        if not command:
            return {"ok": False, "error": "后台任务命令不能为空"}
        if not self.enabled:
            return {"ok": False, "error": "后台任务未启用"}
        if self.active_count() >= self.max_tasks:
            return {"ok": False, "error": "后台任务并发已达上限"}

        task = BackgroundTask(
            id=uuid.uuid4().hex,
            command=command,
            created_at=time.time(),
        )
        with self._lock:
            self._tasks[task.id] = task
            self._save()

        status_cb = self._make_status_cb(task.id)
        if getattr(self.state, "trust", None) is not None:
            self.state.trust.begin_task()
        agent = (
            self.agent_factory()
            if self.agent_factory is not None
            else self.state.make_agent(status_cb=status_cb)
        )
        self._agents[task.id] = agent
        self._cancel_events[task.id] = asyncio.Event()
        self._running_tasks[task.id] = asyncio.create_task(self._run(task.id, agent, command))
        return {"ok": True, "task_id": task.id, "status": task.status}

    def _make_status_cb(self, task_id: str):
        from .state import broadcast_control

        async def callback(message: dict[str, Any]) -> None:
            payload = dict(message)
            payload["task_id"] = task_id
            await broadcast_control(self.state, payload)

        return callback

    async def _run(self, task_id: str, agent: Any, command: str) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        cancel = self._cancel_events.get(task_id)
        task.started_at = time.time()
        task.status = "running"
        self._save()
        await self._make_status_cb(task_id)(
            {
                "type": "agent_status",
                "state": "accepted",
                "step": 0,
                "tool": None,
                "message": f"后台任务已开始：{command}",
            }
        )
        try:
            result = await agent.run(command, cancel=cancel)
        except Exception as exc:
            logger.exception("后台任务失败")
            result = {"state": "error", "message": str(exc)}

        task.result = result
        task.status = str(result.get("state") or "done")
        task.message = str(result.get("message") or "")
        task.finished_at = time.time()
        self._save()

        if self.state.evolution is not None and getattr(agent, "last_trace", None) is not None:
            self.state.evolution.record_trace(agent.last_trace)

        await self._make_status_cb(task_id)({"type": "agent_result", "task_id": task_id, **result})
        self._cancel_events.pop(task_id, None)
        self._running_tasks.pop(task_id, None)
        self._agents.pop(task_id, None)

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(str(task_id))
            if task is None or task.status not in (
                "pending",
                "running",
                "cancelling",
            ):
                return False
            task.status = "cancelling"
            task.message = "取消中"
            self._save()
        event = self._cancel_events.get(str(task_id))
        if event is not None:
            event.set()
        return True

    def remove(self, task_id: str) -> bool:
        self.cancel(str(task_id))
        with self._lock:
            task = self._tasks.pop(str(task_id), None)
            if task is None:
                return False
            self._save()
        return True
