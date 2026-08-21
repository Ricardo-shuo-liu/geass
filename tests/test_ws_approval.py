from __future__ import annotations

import asyncio

from geass.server.app import create_app
from geass.server.state import broadcast_control

from .conftest import make_config, make_state
from .ws_harness import WSClient

TOKEN = "test-token"


def build():
    config = make_config()
    config.server.token = TOKEN
    state = make_state(config=config)
    state.approval_manager.broadcast = lambda message: broadcast_control(
        state, message
    )
    return create_app(state), state


def headers():
    return [(b"sec-websocket-protocol", f"geass, {TOKEN}".encode())]


def test_pending_request_resent_on_connect_and_resolved():
    async def run():
        app, state = build()
        task = asyncio.create_task(
            state.approval_manager.request("sudo ls", "提权")
        )
        await asyncio.sleep(0)
        async with WSClient(app, "/ws/control", headers=headers()) as ws:
            request = await ws.receive_json()
            assert request["type"] == "approval_request"
            assert request["command"] == "sudo ls"
            assert request["reason"] == "提权"
            await ws.send_json(
                {"type": "approval", "id": request["id"], "approved": True}
            )
            resolved = await ws.receive_json()
            assert resolved == {
                "type": "approval_resolved",
                "id": request["id"],
                "approved": True,
            }
        assert await task == {"approved": True, "reason": "审核通过"}

    asyncio.run(run())


def test_stop_rejects_pending_approval():
    async def run():
        app, state = build()
        task = asyncio.create_task(state.approval_manager.request("reboot", "重启"))
        await asyncio.sleep(0)
        async with WSClient(app, "/ws/control", headers=headers()) as ws:
            await ws.receive_json()  # 重发的 approval_request
            await ws.send_json({"type": "stop"})
            messages = [await ws.receive_json(), await ws.receive_json()]
        resolved = next(
            message
            for message in messages
            if message["type"] == "approval_resolved"
        )
        assert resolved["approved"] is False
        assert (await task)["approved"] is False

    asyncio.run(run())


def test_unknown_approval_id_returns_error():
    async def run():
        app, _ = build()
        async with WSClient(app, "/ws/control", headers=headers()) as ws:
            await ws.send_json(
                {"type": "approval", "id": "nope", "approved": True}
            )
            assert await ws.receive_json() == {
                "type": "error",
                "message": "审核请求不存在或已处理",
            }

    asyncio.run(run())
