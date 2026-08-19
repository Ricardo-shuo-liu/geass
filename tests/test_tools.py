from __future__ import annotations

import asyncio

from geass.agent import Agent
from geass.config import AgentConfig

from .conftest import FakeBackend, FakeCapture


def build_agent(backend: FakeBackend) -> Agent:
    return Agent(
        client=None,
        backend=backend,
        capture=FakeCapture(),
        config=AgentConfig(model="x"),
    )


def test_click_maps_and_records():
    backend = FakeBackend(size=(1920, 1080))
    result = asyncio.run(
        build_agent(backend)._execute(
            "click", {"x": 0.5, "y": 0.5, "button": "right"}
        )
    )
    assert result["ok"] is True
    assert backend.calls == [("click", (960, 540, "right"), {})]


def test_drag_maps_both_points():
    backend = FakeBackend(size=(100, 100))
    asyncio.run(
        build_agent(backend)._execute(
            "drag", {"x1": 0.1, "y1": 0.2, "x2": 0.9, "y2": 0.8}
        )
    )
    assert backend.calls == [("drag", (10, 20, 90, 80), {})]


def test_key_press_passthrough():
    backend = FakeBackend()
    asyncio.run(build_agent(backend)._execute("key_press", {"combo": "ctrl+c"}))
    assert backend.calls == [("key_press", ("ctrl+c",), {})]


def test_unknown_tool_returns_error():
    result = asyncio.run(build_agent(FakeBackend())._execute("rm_rf", {}))
    assert result["ok"] is False
    assert "未知工具" in result["error"]


def test_wait_and_screenshot_ok():
    agent = build_agent(FakeBackend())
    assert asyncio.run(agent._execute("wait", {"seconds": 0.01}))["ok"] is True
    assert asyncio.run(agent._execute("screenshot", {}))["ok"] is True
