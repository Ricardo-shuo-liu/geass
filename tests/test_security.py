from __future__ import annotations

import asyncio

from geass.agent import Agent
from geass.config import AgentConfig, SecurityConfig

from .conftest import (
    FakeBackend,
    FakeCapture,
    FakeMessage,
    FakeOpenAI,
    FakeResponse,
    FakeToolCall,
)


class FakeGateway:
    def __init__(self, decisions: list[dict]) -> None:
        self.decisions = list(decisions)
        self.calls: list[tuple[str, str]] = []

    async def request(self, command: str, reason: str) -> dict:
        self.calls.append((command, reason))
        return self.decisions.pop(0)


def build_agent(
    gateway: FakeGateway | None = None,
    security: SecurityConfig | None = None,
    client=None,
):
    return Agent(
        client=client,
        backend=FakeBackend(),
        capture=FakeCapture(),
        config=AgentConfig(model="gpt-test", max_steps=5, image_max_edge=100),
        security=security,
        approval_gateway=gateway,
    )


def test_approved_dangerous_command_executes(monkeypatch):
    executed: list[str] = []
    monkeypatch.setattr(
        "geass.tools.open_terminal",
        lambda command: executed.append(command) or {"ok": True, "message": "已执行"},
    )
    gateway = FakeGateway([{"approved": True, "reason": "审核通过"}])
    agent = build_agent(gateway, SecurityConfig(enabled=True))

    result = asyncio.run(agent._execute("open_terminal", {"command": "sudo ls"}))

    assert result["ok"] is True
    assert gateway.calls == [("sudo ls", "使用了 sudo 提权")]
    assert executed == ["sudo ls"]


def test_denied_dangerous_command_is_not_executed(monkeypatch):
    executed: list[str] = []
    monkeypatch.setattr(
        "geass.tools.open_terminal",
        lambda command: executed.append(command) or {"ok": True, "message": "已执行"},
    )
    gateway = FakeGateway([{"approved": False, "reason": "用户拒绝了该命令"}])
    agent = build_agent(gateway, SecurityConfig(enabled=True))

    result = asyncio.run(agent._execute("open_terminal", {"command": "sudo ls"}))

    assert result["ok"] is False
    assert "拒绝" in result["error"]
    assert executed == []


def test_empty_command_is_not_reviewed(monkeypatch):
    monkeypatch.setattr(
        "geass.tools.open_terminal", lambda command: {"ok": True, "message": "已打开"}
    )
    gateway = FakeGateway([])
    agent = build_agent(gateway, SecurityConfig(enabled=True))

    result = asyncio.run(agent._execute("open_terminal", {"command": ""}))

    assert result["ok"] is True
    assert gateway.calls == []


def test_disabled_security_never_reviews(monkeypatch):
    monkeypatch.setattr(
        "geass.tools.open_terminal", lambda command: {"ok": True, "message": "已执行"}
    )
    gateway = FakeGateway([])
    agent = build_agent(gateway, SecurityConfig(enabled=False))

    result = asyncio.run(agent._execute("open_terminal", {"command": "sudo ls"}))

    assert result["ok"] is True
    assert gateway.calls == []


def test_blocked_command_without_gateway_fails_safe(monkeypatch):
    executed: list[str] = []
    monkeypatch.setattr(
        "geass.tools.open_terminal",
        lambda command: executed.append(command) or {"ok": True, "message": "已执行"},
    )
    agent = build_agent(gateway=None, security=SecurityConfig(enabled=True))

    result = asyncio.run(agent._execute("open_terminal", {"command": "sudo ls"}))

    assert result["ok"] is False
    assert "审核通道不可用" in result["error"]
    assert executed == []


def test_loop_continues_after_denial(monkeypatch):
    monkeypatch.setattr(
        "geass.tools.open_terminal",
        lambda command: {"ok": True, "message": "已执行"},
    )
    script = [
        FakeResponse(
            message=FakeMessage(
                tool_calls=[FakeToolCall("call_1", "open_terminal", '{"command": "sudo rm -rf /"}')]
            )
        ),
        FakeResponse(
            message=FakeMessage(
                tool_calls=[FakeToolCall("call_2", "finish", '{"summary": "已改用其他方式"}')]
            )
        ),
    ]
    gateway = FakeGateway([{"approved": False, "reason": "用户拒绝了该命令"}])
    agent = build_agent(
        gateway,
        SecurityConfig(enabled=True),
        client=FakeOpenAI(script),
    )

    result = asyncio.run(agent.run("删除临时目录"))

    assert result == {"state": "done", "message": "已改用其他方式"}
    assert gateway.calls


class FakeTerminalSession:
    def __init__(self):
        self.id = "s-1"
        self.writes: list[tuple[str, bool]] = []

    def write(self, text, interval=0.0, press_enter=False):
        self.writes.append((text, press_enter))
        return len(text)


class FakeTerminalManager:
    def __init__(self, session):
        self.session = session

    def get(self, session_id=None):
        return self.session


def build_terminal_agent(gateway, security):
    return Agent(
        client=None,
        backend=FakeBackend(),
        capture=FakeCapture(),
        config=AgentConfig(model="gpt-test", max_steps=5, image_max_edge=100),
        security=security,
        approval_gateway=gateway,
        terminal=FakeTerminalManager(FakeTerminalSession()),
    )


def test_terminal_type_dangerous_enter_is_reviewed():
    gateway = FakeGateway([{"approved": False, "reason": "用户拒绝"}])
    agent = build_terminal_agent(gateway, SecurityConfig(enabled=True))

    result = asyncio.run(
        agent._execute("terminal_type", {"text": "sudo rm -rf /", "press_enter": True})
    )

    assert result["ok"] is False
    assert "拒绝" in result["error"]
    assert gateway.calls == [("sudo rm -rf /", "使用了 sudo 提权")]
    assert agent.terminal.session.writes == []


def test_terminal_type_approved_dangerous_enter_writes():
    gateway = FakeGateway([{"approved": True, "reason": "通过"}])
    agent = build_terminal_agent(gateway, SecurityConfig(enabled=True))

    result = asyncio.run(agent._execute("terminal_type", {"text": "sudo ls", "press_enter": True}))

    assert result["ok"] is True
    assert agent.terminal.session.writes == [("sudo ls", True)]


def test_terminal_type_plain_typing_is_not_reviewed():
    gateway = FakeGateway([])
    agent = build_terminal_agent(gateway, SecurityConfig(enabled=True))

    result = asyncio.run(agent._execute("terminal_type", {"text": "hello"}))

    assert result["ok"] is True
    assert gateway.calls == []
    assert agent.terminal.session.writes == [("hello", False)]


def test_terminal_type_dangerous_text_without_enter_is_reviewed():
    gateway = FakeGateway([{"approved": False, "reason": "用户拒绝"}])
    agent = build_terminal_agent(gateway, SecurityConfig(enabled=True))

    result = asyncio.run(agent._execute("terminal_type", {"text": "rm -rf /home/x"}))

    assert result["ok"] is False
    assert gateway.calls
    assert agent.terminal.session.writes == []
