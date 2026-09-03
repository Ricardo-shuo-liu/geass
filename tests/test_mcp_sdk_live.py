from __future__ import annotations

import asyncio
import sys

import geass.mcp.manager as manager_module
from geass.mcp.manager import MCPManager, function_name

SERVER_SCRIPT = r'''
import asyncio

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("Demo", log_level="ERROR")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


async def main():
    async def beat():
        try:
            while True:
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass

    task = asyncio.create_task(beat())
    try:
        await mcp.run_stdio_async()
    finally:
        task.cancel()


asyncio.run(main())
'''


def test_real_stdio_server_import_test_and_call(tmp_path, monkeypatch):
    monkeypatch.setattr(manager_module, "CALL_TIMEOUT", 8)
    script = tmp_path / "server.py"
    script.write_text(SERVER_SCRIPT, encoding="utf-8")

    async def run():
        manager = MCPManager(tmp_path / ".mcp" / "servers.json")
        try:
            record = await manager.add_and_test(
                "demo",
                "stdio",
                command=sys.executable,
                args=[str(script)],
                cwd=str(tmp_path),
            )
            assert record.verified is True
            assert record.enabled is True
            assert [tool.name for tool in record.tools] == ["add"]

            result = await manager.call(function_name("demo", "add"), {"a": 2, "b": 3})
            assert result is not None
            assert result["ok"] is True
            assert "5" in str(result)
        finally:
            await manager.aclose()

    asyncio.run(run())
