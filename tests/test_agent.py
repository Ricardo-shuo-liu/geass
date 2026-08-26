from __future__ import annotations

import asyncio
import json

import pytest
from PIL import Image

from geass.agent import TEXT_ONLY_TOOLS, Agent, AgentError
from geass.config import AgentConfig
from geass.memory import Memory
from geass.ocr import OCRBox, OCRResult
from geass.scheduler import ScheduleStore

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


def test_plan_tool_records_plan_and_injects_reminder():
    script = [
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall(
                        "call_1",
                        "plan",
                        json.dumps(
                            {
                                "difficulty": "hard",
                                "goal": "打开浏览器并新建页面",
                                "steps": ["启动浏览器", "新建标签页", "验证"],
                            }
                        ),
                    )
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
    agent, _, client = build(script)
    events = []

    async def callback(message):
        events.append(message)

    agent.status_cb = callback
    result = asyncio.run(agent.run("打开浏览器，然后新建一个页面"))

    assert result["state"] == "done"
    assert agent.plan is not None
    assert agent.plan.difficulty == "hard"
    assert len(agent.plan.steps) == 3
    assert any(
        event.get("state") == "planned" and event.get("plan")
        for event in events
    )
    second_request_contents = [
        message["content"]
        for message in client.requests[1]["messages"]
        if isinstance(message["content"], str)
    ]
    assert any(
        "任务计划（困难任务）" in content for content in second_request_contents
    )


def test_plan_tool_resets_between_runs():
    agent, _, client = build(
        [
            FakeResponse(
                message=FakeMessage(
                    tool_calls=[
                        FakeToolCall(
                            "call_1",
                            "plan",
                            '{"difficulty": "easy", "goal": "g", "steps": ["a"]}',
                        )
                    ]
                )
            ),
            FakeResponse(
                message=FakeMessage(
                    tool_calls=[
                        FakeToolCall("call_2", "finish", '{"summary": "done"}'),
                    ]
                )
            ),
        ]
    )
    asyncio.run(agent.run("任务一"))
    assert agent.plan is not None

    client.script = [
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall("call_1", "finish", '{"summary": "done"}'),
                ]
            )
        )
    ]
    asyncio.run(agent.run("任务二"))
    assert agent.plan is None


def test_browser_tool_calls_browser_module(monkeypatch):
    captured = {}

    def fake_open_page(action, url):
        captured["action"] = action
        captured["url"] = url
        return {"ok": True, "message": "opened", "action": action, "url": url}

    monkeypatch.setattr("geass.agent.browser.open_page", fake_open_page)
    script = [
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall(
                        "call_1",
                        "browser",
                        '{"action": "new_tab", "url": "https://example.com"}',
                    )
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
    agent, _, _ = build(script)
    result = asyncio.run(agent.run("新建一个页面"))

    assert result["state"] == "done"
    assert captured == {
        "action": "new_tab",
        "url": "https://example.com",
    }


def test_memory_tools_read_write(tmp_path):
    memory = Memory(tmp_path / ".memory")
    script = [
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall(
                        "call_1",
                        "remember",
                        '{"key": "默认浏览器", "value": "firefox"}',
                    )
                ]
            )
        ),
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall(
                        "call_2",
                        "recall",
                        '{"query": "浏览器", "limit": 3}',
                    )
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
    agent, _, _ = build(script)
    agent.memory = memory

    result = asyncio.run(agent.run("记住默认浏览器"))

    assert result["state"] == "done"
    assert memory.recall("浏览器")[0]["value"] == "firefox"


def test_memory_tools_hidden_when_disabled():
    agent, _, client = build(
        [
            FakeResponse(
                message=FakeMessage(
                    tool_calls=[
                        FakeToolCall("call_1", "finish", '{"summary": "done"}'),
                    ]
                )
            )
        ]
    )
    agent.memory = None
    asyncio.run(agent.run("任务"))
    names = {
        tool["function"]["name"] for tool in client.requests[0]["tools"]
    }
    assert "remember" not in names
    assert "plan" in names
    assert "browser" in names


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


def test_screen_change_detection_warns_when_nothing_changed():
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
    agent, _, client = build(script)

    result = asyncio.run(agent.run("点击屏幕中央"))

    assert result["state"] == "done"
    tool_results = [
        json.loads(message["content"])
        for message in client.requests[0]["messages"]
        if message.get("role") == "tool"
    ]
    click_result = next(
        result_ for result_ in tool_results if "单击" in str(result_.get("message"))
    )
    assert click_result["screen_changed"] is False
    assert "屏幕未检测到变化" in click_result["message"]


def test_screen_change_detection_reports_change():
    class ChangingCapture(FakeCapture):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def capture_image(self, max_edge: int | None = None):
            self.calls += 1
            color = 0 if self.calls % 2 else 255
            return Image.new("RGB", (100, 80), (color, color, color))

    script = [
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall("call_1", "key_press", '{"combo": "enter"}'),
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
    agent, _, client = build(script)
    agent.capture = ChangingCapture()

    result = asyncio.run(agent.run("按回车"))

    assert result["state"] == "done"
    tool_results = [
        json.loads(message["content"])
        for message in client.requests[0]["messages"]
        if message.get("role") == "tool"
    ]
    key_result = next(
        result_ for result_ in tool_results if "已按键" in str(result_.get("message"))
    )
    assert key_result["screen_changed"] is True


def test_window_info_tool_reports_active_window(monkeypatch):
    def fake_list_windows(limit: int = 20):
        return [
            {
                "name": "Firefox — 新标签页",
                "role": "frame",
                "x": 0,
                "y": 0,
                "w": 1920,
                "h": 1080,
                "active": True,
                "visible": True,
            },
            {
                "name": "Files",
                "role": "frame",
                "x": 10,
                "y": 10,
                "w": 800,
                "h": 600,
                "active": False,
                "visible": True,
            },
        ]

    monkeypatch.setattr("geass.io.accessibility.list_windows", fake_list_windows)
    script = [
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall("call_1", "window_info", '{"limit": 10}'),
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
    agent, _, client = build(script)

    result = asyncio.run(agent.run("检查活动窗口"))

    assert result["state"] == "done"
    tool_results = [
        json.loads(message["content"])
        for message in client.requests[0]["messages"]
        if message.get("role") == "tool"
    ]
    window_result = next(
        result_ for result_ in tool_results if "active_window" in result_
    )
    assert window_result["active_window"]["name"] == "Firefox — 新标签页"
    assert window_result["count"] == 2


def test_hard_browser_task_plans_launches_and_verifies(monkeypatch):
    launched: list[tuple[str, str]] = []

    def fake_open_page(action: str, url: str):
        launched.append((action, url))
        return {
            "ok": True,
            "message": f"已启动 {action}",
            "action": action,
            "url": url or "about:blank",
        }

    def fake_list_windows(limit: int = 20):
        return [
            {
                "name": "Firefox — 新标签页",
                "role": "frame",
                "x": 0,
                "y": 0,
                "w": 1920,
                "h": 1080,
                "active": True,
                "visible": True,
            }
        ]

    monkeypatch.setattr("geass.agent.browser.open_page", fake_open_page)
    monkeypatch.setattr("geass.io.accessibility.list_windows", fake_list_windows)
    script = [
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall(
                        "call_1",
                        "plan",
                        json.dumps(
                            {
                                "difficulty": "hard",
                                "goal": "打开浏览器并新建一个页面",
                                "steps": ["启动浏览器", "新建标签页", "验证页面"],
                            }
                        ),
                    )
                ]
            )
        ),
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall("call_2", "browser", '{"action": "new_tab"}'),
                ]
            )
        ),
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall("call_3", "window_info", '{"limit": 10}'),
                ]
            )
        ),
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall("call_4", "finish", '{"summary": "新页面已打开"}'),
                ]
            )
        ),
    ]
    agent, _, client = build(script)
    events = []

    async def callback(message):
        events.append(message)

    agent.status_cb = callback
    result = asyncio.run(agent.run("打开浏览器，然后新建一个页面"))

    assert result["state"] == "done"
    assert launched == [("new_tab", "")]
    assert agent.plan is not None
    assert agent.plan.difficulty == "hard"
    assert any(
        event.get("state") == "planned" and event.get("plan")
        for event in events
    )
    tool_results = [
        json.loads(message["content"])
        for message in client.requests[0]["messages"]
        if message.get("role") == "tool"
    ]
    verified = next(
        result_ for result_ in tool_results if "active_window" in result_
    )
    assert verified["active_window"]["name"] == "Firefox — 新标签页"


def test_schedule_tool_directly_creates_temp_job(tmp_path):
    store = ScheduleStore(tmp_path / ".schedule")
    agent, _, _ = build([])
    agent.schedule_store = store

    result = asyncio.run(
        agent._execute(
            "schedule",
            {"command": "打开终端", "run_at": "2099-01-01T12:00:00"},
        )
    )

    assert result["ok"] is True
    assert result["job"]["persistent"] is False
    assert store.list()[0].command == "打开终端"


def test_schedule_tool_persist_requires_confirmation_then_confirm(tmp_path):
    store = ScheduleStore(tmp_path / ".schedule")
    agent, _, _ = build([])
    agent.schedule_store = store

    first = asyncio.run(
        agent._execute(
            "schedule",
            {
                "command": "打开终端",
                "run_at": "2099-01-01T12:00:00",
                "persist": True,
            },
        )
    )
    assert first["ok"] is True
    assert first["status"] == "awaiting_confirmation"
    assert store.list() == []

    wrong = asyncio.run(
        agent._execute(
            "schedule",
            {
                "command": "其他命令",
                "run_at": "2099-01-01T12:00:00",
                "persist": True,
                "confirm": True,
            },
        )
    )
    assert wrong["ok"] is False

    confirmed = asyncio.run(
        agent._execute(
            "schedule",
            {
                "command": "打开终端",
                "run_at": "2099-01-01T12:00:00",
                "persist": True,
                "confirm": True,
            },
        )
    )
    assert confirmed["ok"] is True
    assert confirmed["job"]["persistent"] is True
    assert store.list()[0].status == "pending"
