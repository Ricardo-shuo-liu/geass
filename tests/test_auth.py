from __future__ import annotations

import asyncio

import httpx
import pytest

from geass.server.app import create_app

from .conftest import make_config, make_state
from .ws_harness import WSClient, WSRejected

TOKEN = "test-token"


def build_app():
    config = make_config()
    config.server.token = TOKEN
    state = make_state(config=config)
    return create_app(state)


def test_info_requires_token():
    app = build_app()

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            denied = await client.get("/api/info")
            allowed = await client.get(
                "/api/info", headers={"X-GEASS-Token": TOKEN}
            )
            return denied.status_code, allowed.status_code, allowed.json()

    denied_code, allowed_code, body = asyncio.run(run())
    assert denied_code == 401
    assert allowed_code == 200
    assert body["openai_configured"] is False


def test_health_is_public():
    app = build_app()

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/api/health")
            return response.status_code, response.json()

    status_code, body = asyncio.run(run())
    assert status_code == 200
    assert body["ok"] is True


def test_stop_agent_requires_token():
    app = build_app()

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            denied = await client.post("/api/agent/stop")
            allowed = await client.post(
                "/api/agent/stop", headers={"X-GEASS-Token": TOKEN}
            )
            return denied.status_code, allowed.status_code, allowed.json()

    denied_code, allowed_code, body = asyncio.run(run())
    assert denied_code == 401
    assert allowed_code == 200
    assert body["ok"] is True


def test_transcribe_without_api_key_returns_503():
    app = build_app()

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/api/transcribe",
                headers={"X-GEASS-Token": TOKEN},
                files={"file": ("audio.webm", b"fake", "audio/webm")},
            )
            return response.status_code

    assert asyncio.run(run()) == 503


def test_control_ws_rejects_bad_token():
    app = build_app()

    async def run():
        with pytest.raises(WSRejected):
            async with WSClient(app, "/ws/control"):
                pass

    asyncio.run(run())


def test_control_ws_ping_pong():
    app = build_app()

    async def run():
        async with WSClient(
            app, "/ws/control", query_string=f"token={TOKEN}".encode()
        ) as ws:
            await ws.send_json({"type": "ping"})
            assert await ws.receive_json() == {"type": "pong"}

    asyncio.run(run())


def test_screen_ws_accepts_and_closes():
    app = build_app()

    async def run():
        async with WSClient(
            app, "/ws/screen", query_string=f"token={TOKEN}".encode()
        ):
            pass

    asyncio.run(run())
