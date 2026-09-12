from __future__ import annotations

import asyncio

import httpx

import geass.server.api as api_module
from geass.server.app import create_app
from geass.server.approval import PendingAction
from geass.server.state import broadcast_control, make_agent

from .conftest import make_config, make_state
from .ws_harness import WSClient

TOKEN = "test-token"


def build(tmp_path):
    config = make_config()
    config.server.token = TOKEN
    state = make_state(config=config)
    state.trust.path = tmp_path / ".trust.json"
    state.masks.path = tmp_path / ".masks.json"
    state.approval_manager.broadcast = lambda message: broadcast_control(state, message)
    state.approval_manager.has_clients = lambda: bool(state.control_clients)
    return state, create_app(state)


def headers():
    return {"X-GEASS-Token": TOKEN}


def test_trust_rest_roundtrip(tmp_path):
    async def run():
        state, app = build(tmp_path)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            unauthorized = await client.get("/api/trust")
            current = await client.get("/api/trust", headers=headers())
            updated = await client.post(
                "/api/trust",
                json={"mode": "confirm", "visual_delay_ms": 1200},
                headers=headers(),
            )

        assert unauthorized.status_code == 401
        assert current.json()["mode"] == "smart"
        assert updated.status_code == 200
        assert updated.json()["mode"] == "confirm"
        assert state.trust.mode == "confirm"
        assert state.trust.visual_delay_ms == 1200

    asyncio.run(run())


def test_trust_rejects_invalid_mode(tmp_path):
    async def run():
        _state, app = build(tmp_path)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post("/api/trust", json={"mode": "nope"}, headers=headers())

        assert response.status_code == 400

    asyncio.run(run())


def test_privacy_masks_rest(tmp_path):
    async def run():
        state, app = build(tmp_path)
        mask = state.masks.add({"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2})
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get("/api/privacy/masks", headers=headers())

        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is True
        assert body["masks"][0]["id"] == mask["id"]

    asyncio.run(run())


def test_privacy_detect_rest(tmp_path, monkeypatch):
    async def run():
        _state, app = build(tmp_path)
        monkeypatch.setattr(
            api_module,
            "detect_sensitive_regions",
            lambda *_args, **_kwargs: {
                "regions": [
                    {
                        "x": 0.1,
                        "y": 0.2,
                        "w": 0.3,
                        "h": 0.1,
                        "source": "password",
                        "label": "密码框",
                    }
                ],
                "sources": {"password_fields": 1, "keyword_matches": 0},
                "keywords": ["密码"],
            },
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            unauthorized = await client.post("/api/privacy/detect")
            response = await client.post("/api/privacy/detect", headers=headers())

        assert unauthorized.status_code == 401
        assert response.status_code == 200
        assert response.json()["sources"]["password_fields"] == 1

    asyncio.run(run())


def test_control_socket_snapshots_and_privacy_updates(tmp_path):
    async def run():
        state, app = build(tmp_path)
        async with WSClient(
            app, "/ws/control", headers=[(b"sec-websocket-protocol", f"geass, {TOKEN}".encode())]
        ) as ws:
            masks = await ws.receive_json(skip_types=set())
            trust = await ws.receive_json(skip_types=set())
            assert masks["type"] == "privacy_masks_changed"
            assert masks["enabled"] is False
            assert trust["type"] == "trust_changed"
            assert trust["mode"] == "smart"

            await ws.send_json(
                {
                    "type": "privacy_mask",
                    "action": "add",
                    "rect": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2},
                }
            )
            changed = await ws.receive_json(skip_types=set())

        assert changed["type"] == "privacy_masks_changed"
        assert changed["enabled"] is True
        assert len(changed["masks"]) == 1

    asyncio.run(run())


def test_control_socket_resolves_pending_action(tmp_path):
    async def run():
        state, app = build(tmp_path)
        # 模拟“有控制端在线”后发起预览，用于验证重连补发
        state.approval_manager.has_clients = lambda: True
        action = PendingAction(
            id="act1",
            tool="click",
            kind="point",
            target={"x": 0.5, "y": 0.5},
            summary="单击",
            decision_required=True,
        )
        task = asyncio.create_task(state.approval_manager.request_action(action))
        await asyncio.sleep(0)

        async with WSClient(
            app, "/ws/control", headers=[(b"sec-websocket-protocol", f"geass, {TOKEN}".encode())]
        ) as ws:
            proposal = await ws.receive_json(skip_types=set())
            masks = await ws.receive_json(skip_types=set())
            trust = await ws.receive_json(skip_types=set())
            assert proposal["type"] == "action_proposal"
            assert trust["type"] == "trust_changed"
            assert masks["type"] == "privacy_masks_changed"
            await ws.send_json(
                {
                    "type": "action_decision",
                    "id": proposal["id"],
                    "approved": True,
                    "target": {"x": 0.9, "y": 0.9},
                }
            )
            resolved = await ws.receive_json(skip_types=set())

        assert resolved["type"] == "action_resolved"
        decision = await task
        assert decision["approved"] is True
        assert decision["target"] == {"x": 0.9, "y": 0.9}

    asyncio.run(run())


def test_ws_action_preview_end_to_end(tmp_path):
    """回归：真实 WS 链路要能收到 action_proposal 并批准执行。"""

    async def run():
        state, app = build(tmp_path)
        state.trust.update(mode="confirm")
        agent = make_agent(state)
        async with WSClient(
            app, "/ws/control", headers=[(b"sec-websocket-protocol", f"geass, {TOKEN}".encode())]
        ) as ws:
            # 连接时自动推送的遮罩/信任快照
            await ws.receive_json(skip_types=set())
            await ws.receive_json(skip_types=set())

            task = asyncio.create_task(agent._guarded_action("move", {"x": 0.2, "y": 0.2}))
            pending_status = await ws.receive_json(skip_types=set())
            assert pending_status["type"] == "agent_status"
            assert pending_status["state"] == "awaiting_action"
            proposal = await ws.receive_json(skip_types={"privacy_masks_changed", "trust_changed"})
            assert proposal["type"] == "action_proposal"
            assert proposal["decision_required"] is True
            assert proposal["kind"] == "point"

            await ws.send_json(
                {
                    "type": "action_decision",
                    "id": proposal["id"],
                    "approved": True,
                    "target": {"x": 0.1, "y": 0.1},
                }
            )
            resolved = await ws.receive_json(skip_types={"privacy_masks_changed", "trust_changed"})
            assert resolved["type"] == "action_resolved"
            assert resolved["approved"] is True

        result, _change = await task
        assert result["ok"] is True
        assert state.backend.calls == [("move", (192, 108), {})]

    asyncio.run(run())
