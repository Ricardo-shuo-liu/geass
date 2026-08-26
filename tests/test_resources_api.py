from __future__ import annotations

import asyncio

import httpx

from geass.evolution import POTStore
from geass.memory import Memory
from geass.rag import RAGManager
from geass.scheduler import ScheduleStore
from geass.server.app import create_app
from geass.server.task_manager import BackgroundTaskManager

from .conftest import make_config, make_state


def build_state_and_app(tmp_path):
    config = make_config()
    config.server.token = "test-token"
    state = make_state(config=config)
    state.memory = Memory(tmp_path / ".memory")
    state.memory.remember("browser", "firefox")
    state.rag = RAGManager(tmp_path / ".rag")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("打开终端的方法", encoding="utf-8")
    state.rag.add_source(docs, name="docs")
    state.pot = POTStore(tmp_path / ".pot")
    state.pot.set_cot("先明确目标")
    state.pot.save_rot("工程师视角", "严谨", "严谨工程师", "先验证")
    state.schedule_store = ScheduleStore(tmp_path / ".schedule")
    return state, create_app(state)


def test_resources_summary_and_actions(tmp_path):
    async def run():
        state, app = build_state_and_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        headers = {"X-GEASS-Token": "test-token"}
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            summary = await client.get("/api/resources", headers=headers)
            assert summary.status_code == 200
            body = summary.json()
            assert body["memory"]["entries"][0]["key"] == "browser"
            assert body["rag"]["sources"][0]["name"] == "docs"
            assert body["pot"]["rots"][0]["name"] == "工程师视角"

            deleted = await client.delete(
                "/api/resources/memory/browser", headers=headers
            )
            assert deleted.status_code == 200
            assert state.memory.recall("browser") == []

            disabled = await client.post(
                "/api/resources/rag/docs/enabled",
                json={"enabled": False},
                headers=headers,
            )
            assert disabled.status_code == 200
            assert state.rag.list_sources()[0]["enabled"] is False

            rot_disabled = await client.post(
                "/api/resources/pot/rot/工程师视角/enabled",
                json={"enabled": False},
                headers=headers,
            )
            assert rot_disabled.status_code == 200
            assert state.pot.get_rot("工程师视角").enabled is False

            removed = await client.delete(
                "/api/resources/rag/docs", headers=headers
            )
            assert removed.status_code == 200
            assert state.rag.list_sources() == []

    asyncio.run(run())


def test_background_tasks_api(tmp_path):
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

    async def run():
        state, app = build_state_and_app(tmp_path)
        state.task_manager = BackgroundTaskManager(
            state,
            agent_factory=FakeAgent,
            max_tasks=2,
            path=tmp_path / ".tasks",
        )
        transport = httpx.ASGITransport(app=app)
        headers = {"X-GEASS-Token": "test-token"}
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            created = await client.post(
                "/api/tasks", json={"command": "后台命令"}, headers=headers
            )
            assert created.status_code == 200
            task_id = created.json()["task_id"]

            listed = await client.get("/api/tasks", headers=headers)
            assert any(item["id"] == task_id for item in listed.json()["tasks"])

            summary = await client.get("/api/resources", headers=headers)
            assert summary.json()["background"]["tasks"][0]["id"] == task_id

            cancelled = await client.post(
                f"/api/tasks/{task_id}/cancel", headers=headers
            )
            assert cancelled.status_code == 200

    asyncio.run(run())
