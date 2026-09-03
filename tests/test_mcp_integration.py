from __future__ import annotations

import asyncio

from geass.agent import Agent
from geass.cli.session import CILSession
from geass.config import AgentConfig
from geass.mcp.manager import MCPManager, function_name

from .conftest import FakeBackend, FakeCapture, FakeMessage, FakeOpenAI, FakeResponse
from .test_mcp_registry import connector_for, sample_tools


def make_mcp(tmp_path):
    manager = MCPManager(tmp_path / ".mcp", connector=connector_for(sample_tools()))
    return asyncio.run(manager.add_and_test("demo", "stdio", command="echo")), manager


def test_agent_exposes_and_routes_mcp_tools(tmp_path):
    _, manager = make_mcp(tmp_path)
    config = AgentConfig(model="test", vision=False)
    agent = Agent(
        client=None,
        backend=FakeBackend(),
        capture=FakeCapture(),
        config=config,
        mcp=manager,
    )

    names = [item["function"]["name"] for item in agent._tools()]
    expected = function_name("demo", "add")
    assert expected in names

    result = asyncio.run(agent._execute(expected, {"a": 1, "b": 2}))
    assert result["ok"] is True

    manager.set_tool_enabled("demo", "add", False)
    assert expected not in [item["function"]["name"] for item in agent._tools()]
    result = asyncio.run(agent._execute(expected, {"a": 1}))
    assert result["ok"] is False


def test_cil_exposes_and_routes_mcp_tools(tmp_path):
    _, manager = make_mcp(tmp_path)
    client = FakeOpenAI([FakeResponse(message=FakeMessage(content="完成"))])
    session = CILSession(
        client=client,
        config=AgentConfig(model="test"),
        mcp=manager,
    )

    asyncio.run(session._chat("用工具", tool_use=True))
    tool_names = {item["function"]["name"] for item in client.requests[0]["tools"]}
    expected = function_name("demo", "add")
    assert expected in tool_names

    result = asyncio.run(session._execute_tool(expected, {"a": 1, "b": 2}))
    assert result["ok"] is True
