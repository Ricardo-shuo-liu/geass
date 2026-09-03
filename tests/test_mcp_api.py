from __future__ import annotations

import asyncio

import httpx

from geass.mcp.manager import MCPManager
from geass.server.app import create_app

from .conftest import make_state
from .test_mcp_registry import connector_for, sample_tools


def build(tmp_path, fail=None):
    state = make_state()
    state.mcp = MCPManager(
        tmp_path / ".mcp" / "servers.json",
        connector=connector_for(sample_tools(), fail),
    )
    return state, create_app(state)


def test_mcp_resource_api(tmp_path):
    async def run():
        fail = {"broken": True}
        state, app = build(tmp_path, fail=fail)
        transport = httpx.ASGITransport(app=app)
        headers = {"X-GEASS-Token": "test-token"}
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            created = await client.post(
                "/api/resources/mcp",
                json={
                    "name": "demo",
                    "transport": "stdio",
                    "command": "echo",
                    "env": {"TOKEN": "secret"},
                },
                headers=headers,
            )
            assert created.status_code == 200
            record = created.json()["record"]
            assert record["verified"] is True
            assert record["tools"][0]["name"] == "add"
            assert "secret" not in str(record)
            assert record["env_keys"] == ["TOKEN"]

            duplicate = await client.post(
                "/api/resources/mcp",
                json={"name": "demo", "transport": "stdio", "command": "echo"},
                headers=headers,
            )
            assert duplicate.status_code == 400

            broken = await client.post(
                "/api/resources/mcp",
                json={"name": "broken", "transport": "stdio", "command": "bad"},
                headers=headers,
            )
            assert broken.status_code == 200
            assert broken.json()["record"]["verified"] is False

            enable_broken = await client.post(
                "/api/resources/mcp/broken/enabled",
                json={"enabled": True},
                headers=headers,
            )
            assert enable_broken.status_code == 409

            fail["broken"] = False
            retested = await client.post(
                "/api/resources/mcp/broken/test",
                headers=headers,
            )
            assert retested.status_code == 200
            assert retested.json()["record"]["verified"] is True

            summary = await client.get("/api/resources", headers=headers)
            names = {item["name"] for item in summary.json()["mcp"]["servers"]}
            assert names == {"demo", "broken"}

            tool_off = await client.post(
                "/api/resources/mcp/demo/tools/add/enabled",
                json={"enabled": False},
                headers=headers,
            )
            assert tool_off.status_code == 200
            assert "mcp__demo__add" not in [item["name"] for item in state.mcp.schemas()]

            disabled = await client.post(
                "/api/resources/mcp/demo/enabled",
                json={"enabled": False},
                headers=headers,
            )
            assert disabled.status_code == 200

            removed = await client.delete(
                "/api/resources/mcp/demo",
                headers=headers,
            )
            assert removed.status_code == 200
            assert state.mcp.get("demo") is None

    asyncio.run(run())
