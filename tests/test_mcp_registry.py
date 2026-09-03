from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from typing import Any

from geass.mcp.manager import MCPManager, function_name, sanitize_parameters


class FakeStack:
    closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeClient:
    def __init__(self, tools: list[dict[str, Any]], calls: list[tuple[str, Any]]) -> None:
        self.tools = tools
        self.calls = calls

    async def list_tools(self, cursor: str | None = None):
        return SimpleNamespace(tools=[SimpleNamespace(**tool) for tool in self.tools])

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        self.calls.append((name, arguments))
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            structured_content=None,
            is_error=False,
        )


def connector_for(tools: list[dict[str, Any]], fail: dict[str, bool] | None = None):
    calls: list[tuple[str, Any]] = []

    async def connector(record):
        if fail is not None and fail.get(record.name):
            raise ConnectionError("连接失败")
        return FakeClient(tools, calls), FakeStack()

    connector.calls = calls  # type: ignore[attr-defined]
    return connector


def sample_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "add",
            "description": "相加",
            "title": None,
            "input_schema": {
                "type": "object",
                "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                "required": ["a", "b"],
                "$schema": "http://json-schema.org/draft-07/schema#",
            },
        }
    ]


def test_add_and_test_persists_success(tmp_path):
    async def run():
        path = tmp_path / ".mcp" / "servers.json"
        manager = MCPManager(path, connector=connector_for(sample_tools()))
        record = await manager.add_and_test(
            "demo", "stdio", command="echo", args=["a"], env={"TOKEN": "secret"}
        )

        assert record.verified is True
        assert record.enabled is True
        assert len(record.tools) == 1
        assert record.tools[0].name == "add"
        assert path.exists()
        assert os.stat(path).st_mode & 0o777 == 0o600

        loaded = MCPManager(path)
        again = loaded.get("demo")
        assert again is not None
        assert again.verified is True
        assert loaded.schemas()[0]["name"] == function_name("demo", "add")
        assert loaded.schemas()[0]["parameters"] == {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        }

    asyncio.run(run())


def test_failed_test_keeps_disabled_record_and_can_retest(tmp_path):
    async def run():
        fail = {"bad": True}
        manager = MCPManager(
            tmp_path / ".mcp" / "servers.json", connector=connector_for(sample_tools(), fail)
        )
        record = await manager.add_and_test("bad", "stdio", command="nope")

        assert record.verified is False
        assert record.enabled is False
        assert record.last_error
        assert manager.schemas() == []

        fail["bad"] = False
        record = await manager.test("bad")
        assert record.verified is True
        assert record.enabled is True
        assert record.last_error is None

    asyncio.run(run())


def test_server_and_tool_level_switches(tmp_path):
    async def run():
        manager = MCPManager(tmp_path / ".mcp", connector=connector_for(sample_tools()))
        await manager.add_and_test("demo", "stdio", command="echo")

        assert len(manager.schemas()) == 1
        assert manager.set_tool_enabled("demo", "add", False)
        assert manager.schemas() == []
        assert manager.set_tool_enabled("demo", "add", True)
        assert len(manager.schemas()) == 1

        assert manager.set_enabled("demo", False)
        assert manager.schemas() == []
        assert manager.set_enabled("demo", True)
        assert len(manager.schemas()) == 1

    asyncio.run(run())


def test_unverified_server_cannot_be_enabled_and_duplicates_rejected(tmp_path):
    async def run():
        manager = MCPManager(
            tmp_path / ".mcp", connector=connector_for(sample_tools(), fail={"x": True})
        )
        await manager.add_and_test("x", "http", url="http://localhost/mcp")
        assert manager.set_enabled("x", True) is False

        try:
            manager.add("x", "stdio", command="echo")
        except ValueError:
            pass
        else:
            raise AssertionError("重复名称应当被拒绝")

    asyncio.run(run())


def test_call_routes_and_renders_text_result(tmp_path):
    async def run():
        connector = connector_for(sample_tools())
        manager = MCPManager(tmp_path / ".mcp", connector=connector)
        await manager.add_and_test("demo", "stdio", command="echo")

        result = await manager.call(function_name("demo", "add"), {"a": 1, "b": 2})
        assert result is not None
        assert result["ok"] is True
        assert result["result"] == "ok"
        assert connector.calls == [("add", {"a": 1, "b": 2})]

        assert await manager.call("no_such_tool", {}) is None

    asyncio.run(run())


def test_function_names_are_sanitized_stable_and_bounded():
    assert function_name("My Server", "do thing") == "mcp__My_Server__do_thing"
    long_name = function_name("x" * 100, "y" * 100)
    assert len(long_name) <= 64
    assert function_name("x" * 100, "y" * 100) == long_name


def test_function_name_collisions_are_disambiguated(tmp_path):
    async def run():
        manager = MCPManager(tmp_path / ".mcp", connector=connector_for(sample_tools()))
        await manager.add_and_test("Foo Bar", "stdio", command="echo")
        await manager.add_and_test("Foo_Bar", "stdio", command="echo")

        names = [item["name"] for item in manager.schemas()]
        assert len(names) == 2
        assert len(set(names)) == 2
        for name in names:
            result = await manager.call(name, {"a": 1, "b": 2})
            assert result is not None
            assert result["ok"] is True
        await manager.aclose()

    asyncio.run(run())


def test_sanitize_parameters_removes_unknown_keys():
    cleaned = sanitize_parameters(
        {
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "args",
        }
    )
    assert cleaned == {"type": "object", "properties": {"q": {"type": "string"}}}
    assert sanitize_parameters({"type": "string"}) is None


def test_delete_removes_record_and_file_updates(tmp_path):
    async def run():
        manager = MCPManager(tmp_path / ".mcp", connector=connector_for(sample_tools()))
        await manager.add_and_test("demo", "stdio", command="echo")
        assert manager.remove("demo") is True
        assert manager.get("demo") is None
        assert MCPManager(tmp_path / ".mcp").get("demo") is None

    asyncio.run(run())
