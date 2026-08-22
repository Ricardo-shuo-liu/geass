from __future__ import annotations

import asyncio

import pytest

from geass.agent import TEXT_ONLY_TOOLS, Agent, AgentError
from geass.config import AgentConfig
from geass.ocr import OCRBox, OCRResult

from .conftest import (
    FakeBackend,
    FakeCapture,
    FakeMessage,
    FakeOpenAI,
    FakeResponse,
    FakeToolCall,
)


class BadRequestError(Exception):
    """模拟 OpenAI SDK 的 400 错误。"""


class FakeOCR:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    def read(self, image):
        if not self.ok:
            return OCRResult(ok=False, error="fake failure")
        return OCRResult(
            ok=True,
            boxes=[
                OCRBox("hello", 0.99, 0.5, 0.5),
                OCRBox("world", 0.98, 0.55, 0.55),
            ],
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
    assert client.requests[0]["tools"][0]["type"] == "function"
    assert "name" in client.requests[0]["tools"][0]["function"]
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


def test_vision_whitelist_empty_falls_back_to_flag():
    agent, _, _ = build([])
    agent.config.vision_whitelist = ()
    agent.config.vision = False

    assert agent.resolve_vision() is False


def test_vision_whitelist_membership_overrides_flag():
    agent, _, _ = build([])
    agent.config.model = "gpt-5.6-terra"
    agent.config.vision_whitelist = ("sol", "gpt-5.6-terra")
    agent.config.vision = False

    assert agent.resolve_vision() is True


def test_vision_whitelist_non_member_uses_ocr_pairing():
    agent, _, _ = build([])
    agent.config.model = "deepseek-v4-flash"
    agent.config.vision_whitelist = ("gpt-5.6-terra",)
    agent.config.vision = True

    assert agent.resolve_vision() is False


def test_vision_whitelist_is_case_insensitive():
    agent, _, _ = build([])
    agent.config.model = "GPT-5.6-TERRA"
    agent.config.vision_whitelist = ("gpt-5.6-terra",)

    assert agent.resolve_vision() is True


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


def test_vision_fallback_when_model_rejects_images():
    script = [
        BadRequestError(
            "Failed to deserialize: unknown variant `image_url`, expected `text`"
        ),
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall("call_1", "type_text", '{"text": "hi"}'),
                ]
            )
        ),
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall("call_2", "finish", '{"summary": "完成"}'),
                ]
            )
        ),
    ]
    agent, backend, client = build(script)

    result = asyncio.run(agent.run("输入 hi"))

    assert result["state"] == "done"
    assert agent.vision is False
    assert ("type_text", ("hi",), {}) in backend.calls
    # 降级后的请求不应再携带图片，且工具列表只保留键盘类工具
    for request in client.requests[1:]:
        tool_names = {tool["function"]["name"] for tool in request["tools"]}
        assert tool_names <= TEXT_ONLY_TOOLS
        for message in request["messages"]:
            content = message.get("content")
            if isinstance(content, list):
                assert not any(part.get("type") == "image_url" for part in content)


def test_text_mode_with_ocr_keeps_mouse_tools_and_transcript():
    script = [
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall("call_1", "click", '{"x": 0.5, "y": 0.5}'),
                ]
            )
        ),
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall("call_2", "finish", '{"summary": "完成"}'),
                ]
            )
        ),
    ]
    backend = FakeBackend(size=(100, 100))
    client = FakeOpenAI(script)
    agent = Agent(
        client=client,
        backend=backend,
        capture=FakeCapture(),
        config=AgentConfig(model="deepseek-v4-flash", max_steps=5, vision=False),
        ocr=FakeOCR(),
    )

    result = asyncio.run(agent.run("点击 hello"))

    assert result["state"] == "done"
    assert ("click", (50, 50, "left"), {}) in backend.calls
    first_request = client.requests[0]
    tool_names = {tool["function"]["name"] for tool in first_request["tools"]}
    assert "click" in tool_names
    messages_text = " ".join(
        str(message.get("content", "")) for message in first_request["messages"]
    )
    assert "PaddleOCR" in messages_text
    assert "[0.500,0.500] hello" in messages_text
    assert not any(
        isinstance(message.get("content"), list)
        for message in first_request["messages"]
    )


def test_text_mode_without_ocr_stays_keyboard_only():
    agent = Agent(
        client=None,
        backend=FakeBackend(),
        capture=FakeCapture(),
        config=AgentConfig(model="x", vision=False),
        ocr=FakeOCR(ok=False),
    )

    tools = agent._tools()

    assert {tool["function"]["name"] for tool in tools} <= TEXT_ONLY_TOOLS
