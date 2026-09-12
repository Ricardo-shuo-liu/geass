from __future__ import annotations

import asyncio

import httpx

from geass.server.app import create_app
from geass.server.pairing import PairingManager

from .conftest import make_config, make_state


def build_app(pairing: PairingManager | None = None):
    config = make_config()
    config.server.token = "test-token"
    state = make_state(config=config)
    state.pairing = pairing or PairingManager()
    return state, create_app(state)


def test_pair_returns_server_token():
    async def run():
        state, app = build_app()
        entry = state.pairing.create()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post("/api/pair", json={"code": entry.code})

        assert response.status_code == 200
        assert response.json() == {"token": "test-token"}

    asyncio.run(run())


def test_pair_rejects_invalid_and_reused_code():
    async def run():
        state, app = build_app()
        entry = state.pairing.create()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            invalid = await client.post("/api/pair", json={"code": "wrong"})
            first = await client.post("/api/pair", json={"code": entry.code})
            reused = await client.post("/api/pair", json={"code": entry.code})

        assert invalid.status_code == 401
        assert first.status_code == 200
        assert reused.status_code == 410

    asyncio.run(run())


def test_pair_rejects_expired_code():
    async def run():
        state, app = build_app()
        entry = state.pairing.create()
        entry.expires_at = 0
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post("/api/pair", json={"code": entry.code})

        assert response.status_code == 410
        assert "过期" in response.json()["detail"]

    asyncio.run(run())


def test_pair_rate_limit_returns_retry_after():
    async def run():
        _state, app = build_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            for _ in range(10):
                response = await client.post("/api/pair", json={"code": "bad"})
                assert response.status_code == 401
            blocked = await client.post("/api/pair", json={"code": "bad"})

        assert blocked.status_code == 429
        assert blocked.headers["Retry-After"] == "60"

    asyncio.run(run())


def test_pair_does_not_weaken_token_auth():
    async def run():
        _state, app = build_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            unauthorized = await client.get("/api/info")
            authorized = await client.get("/api/info", headers={"X-GEASS-Token": "test-token"})

        assert unauthorized.status_code == 401
        assert authorized.status_code == 200

    asyncio.run(run())
