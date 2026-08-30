from __future__ import annotations

import asyncio
import time

import httpx

from geass.scheduler import ScheduleStore
from geass.server.app import create_app

from .conftest import make_config, make_state


def test_schedule_crud_endpoints(tmp_path):
    async def run():
        config = make_config()
        config.server.token = "test-token"
        state = make_state(config=config)
        state.schedule_store = ScheduleStore(tmp_path / ".schedule")
        app = create_app(state)
        transport = httpx.ASGITransport(app=app)
        headers = {"X-GEASS-Token": "test-token"}

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            created = await client.post(
                "/api/schedule",
                json={"command": "打开浏览器", "run_at": time.time() + 60},
                headers=headers,
            )
            assert created.status_code == 200
            job = created.json()["job"]

            listed = await client.get("/api/schedule", headers=headers)
            assert listed.status_code == 200
            assert [item["id"] for item in listed.json()["jobs"]] == [job["id"]]

            cancelled = await client.delete(f"/api/schedule/{job['id']}", headers=headers)
            assert cancelled.status_code == 200

            missing = await client.delete(f"/api/schedule/{job['id']}", headers=headers)
            assert missing.status_code == 404

            past = await client.post(
                "/api/schedule",
                json={"command": "命令", "run_at": time.time() - 1},
                headers=headers,
            )
            assert past.status_code == 400

    asyncio.run(run())
