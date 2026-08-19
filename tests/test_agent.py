from __future__ import annotations

import asyncio

import pytest

from geass.agent import Agent, AgentError
from geass.config import AgentConfig

from .conftest import (
    FakeBackend,
    FakeCapture,
    FakeMessage,
    FakeOpenAI,
    FakeResponse,
    FakeToolCall,
)


def build(script: list[FakeResponse], backend: FakeBackend | None = None):
    backend = backend or FakeBackend(size=(1920, 1080))
    client = FakeOpenAI(script)
    agent = Agent(
        client=client,
        backend=backend,
        capture=FakeCapture(),
        config=AgentConfig(model="gpt-test", max_steps=5, image_max_edge=100),
    )
    return agent, backend, client


def test_loop_executes_tools_then_finishes():
    script = [
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall("call_1", "click", '{"x": 0.5, "y": 0.5}'),
                    FakeToolCall("call_2", "type_text", '{"text": "hi"}'),
                ]
            )
        ),
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall("call_3", "finish", '{"summary": "完成"}'),
                ]
            )
        ),
    ]
    agent, backend, client = build(script)

    result = asyncio.run(agent.run("点击屏幕中央"))

    assert result["state"] == "done"
    assert result["message"] == "完成"
    assert ("click", (960, 540, "left"), {}) in backend.calls
    assert ("type_text", ("hi",), {}) in backend.calls
    assert client.requests
    assert client.requests[0]["model"] == "gpt-test"
    assert client.requests[0]["tools"]
    assert client.requests[0]["messages"][0]["role"] == "system"


def test_loop_cancelled_before_start():
    agent, _, _ = build([])
    cancel = asyncio.Event()
    cancel.set()
    result = asyncio.run(agent.run("任务", cancel=cancel))
    assert result["state"] == "cancelled"


def test_missing_client_raises():
    agent = Agent(
        client=None,
        backend=FakeBackend(),
        capture=FakeCapture(),
        config=AgentConfig(model="x"),
    )
    with pytest.raises(AgentError):
        asyncio.run(agent.run("任务"))


def test_status_events_emitted():
    script = [
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall("call_1", "finish", '{"summary": "ok"}'),
                ]
            )
        )
    ]
    agent, _, _ = build(script)
    events = []

    async def callback(message):
        events.append(message)

    agent.status_cb = callback
    asyncio.run(agent.run("任务"))

    states = [event["state"] for event in events]
    assert "thinking" in states
    assert events[-1]["state"] == "done"
