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
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            denied = await client.get("/api/info")
            allowed = await client.get("/api/info", headers={"X-GEASS-Token": TOKEN})
            return denied.status_code, allowed.status_code, allowed.json()

    denied_code, allowed_code, body = asyncio.run(run())
    assert denied_code == 401
    assert allowed_code == 200
    assert body["api_configured"] is False


def test_health_is_public():
    app = build_app()

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/health")
            return response.status_code, response.json()

    status_code, body = asyncio.run(run())
    assert status_code == 200
    assert body["ok"] is True


def test_stop_agent_requires_token():
    app = build_app()

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            denied = await client.post("/api/agent/stop")
            allowed = await client.post("/api/agent/stop", headers={"X-GEASS-Token": TOKEN})
            return denied.status_code, allowed.status_code, allowed.json()

    denied_code, allowed_code, body = asyncio.run(run())
    assert denied_code == 401
    assert allowed_code == 200
    assert body["ok"] is True


def test_transcribe_without_api_key_returns_503():
    app = build_app()

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
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
            app,
            "/ws/control",
            headers=[(b"sec-websocket-protocol", f"geass, {TOKEN}".encode())],
        ) as ws:
            await ws.send_json({"type": "ping"})
            assert await ws.receive_json() == {"type": "pong"}

    asyncio.run(run())


def test_screen_ws_accepts_and_closes():
    app = build_app()

    async def run():
        async with WSClient(
            app,
            "/ws/screen",
            headers=[(b"sec-websocket-protocol", f"geass, {TOKEN}".encode())],
        ):
            pass

    asyncio.run(run())


def test_config_endpoint_updates_and_persists(monkeypatch, tmp_path):
    monkeypatch.setenv("GEASS_HOME", str(tmp_path / "home"))
    app = build_app()

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            headers = {"X-GEASS-Token": TOKEN}
            before = await client.get("/api/config", headers=headers)
            response = await client.post(
                "/api/config",
                headers=headers,
                json={
                    "model": "deepseek-chat",
                    "base_url": "https://api.deepseek.com",
                    "api_key": "sk-test",
                    "vision": False,
                },
            )
            return before.json(), response.status_code, response.json()

    before, status, after = asyncio.run(run())
    assert before["model"] == "gpt-test"
    assert status == 200
    assert after["model"] == "deepseek-chat"
    assert after["vision"] is False
    assert after["api_configured"] is True
    assert (tmp_path / "home" / ".geass" / "env.toml").exists()


def test_config_endpoint_updates_security(monkeypatch, tmp_path):
    monkeypatch.setenv("GEASS_HOME", str(tmp_path / "home"))
    app = build_app()

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            headers = {"X-GEASS-Token": TOKEN}
            before = await client.get("/api/config", headers=headers)
            response = await client.post(
                "/api/config",
                headers=headers,
                json={"security_enabled": False, "approval_timeout": 60},
            )
            return before.json(), response.status_code, response.json()

    before, status, after = asyncio.run(run())
    assert before["security_enabled"] is True
    assert before["security_approval_timeout"] == 30.0
    assert before["security_patterns_count"] > 0
    assert status == 200
    assert after["security_enabled"] is False
    assert after["security_approval_timeout"] == 60.0
