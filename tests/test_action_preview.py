from __future__ import annotations

import asyncio

from geass.agent import Agent
from geass.config import AgentConfig, SecurityConfig
from geass.server.approval import ApprovalManager, PendingAction
from geass.server.state import make_agent as build_server_agent
from geass.server.trust import TrustManager
from geass.tools import build_preview

from .conftest import FakeBackend, FakeCapture, make_state


class FakeGateway:
    def __init__(self, decision: dict) -> None:
        self.default_timeout = 30.0
        self.decision = decision
        self.proposals: list[PendingAction] = []
        self.command_reviews: list[str] = []

    async def request_action(self, proposal: PendingAction) -> dict:
        self.proposals.append(proposal)
        return dict(self.decision)

    async def request(self, command: str, reason: str = "") -> dict:
        self.command_reviews.append(command)
        return {"approved": False, "reason": "不应走到二次审核"}


def make_agent(tmp_path, gateway) -> tuple[Agent, FakeBackend, TrustManager]:
    backend = FakeBackend(size=(1000, 500))
    trust = TrustManager(tmp_path / ".trust.json")
    trust.update(visual_delay_ms=0)
    agent = Agent(
        client=None,
        backend=backend,
        capture=FakeCapture(),  # type: ignore[arg-type]
        config=AgentConfig(model="test"),
        security=SecurityConfig(enabled=True),
        approval_gateway=gateway,
        trust=trust,
    )
    return agent, backend, trust


# ---------- ApprovalManager: 动作预览 ----------


def test_move_is_previewable_as_point():
    preview = build_preview("move", {"x": 0.1, "y": 0.2})

    assert preview is not None
    assert preview["kind"] == "point"
    assert preview["target"] == {"x": 0.1, "y": 0.2}
    assert "0.10" in preview["summary"]


def test_action_auto_executes_after_delay():
    async def run():
        messages: list[dict] = []

        async def broadcast(message: dict) -> None:
            messages.append(message)

        manager = ApprovalManager(broadcast=broadcast, has_clients=lambda: True)
        action = PendingAction(
            id="a1",
            tool="click",
            kind="point",
            target={"x": 0.5, "y": 0.5},
            summary="单击 (0.50, 0.50)",
        )

        decision = await manager.request_action(action)

        assert decision["approved"] is True
        assert decision["auto"] is True
        assert messages[0]["type"] == "action_proposal"
        assert messages[0]["decision_required"] is False
        assert messages[1]["type"] == "action_resolved"
        assert messages[1]["auto"] is True

    asyncio.run(run())


def test_action_delay_can_be_vetoed():
    async def run():
        manager = ApprovalManager(has_clients=lambda: True)
        action = PendingAction(
            id="a2",
            tool="click",
            kind="point",
            target={"x": 0.5, "y": 0.5},
            summary="单击",
            delay_ms=500,
        )
        task = asyncio.create_task(manager.request_action(action))
        await asyncio.sleep(0)

        assert await manager.resolve_action("a2", False) is True
        decision = await task

        assert decision["approved"] is False
        assert decision["auto"] is False

    asyncio.run(run())


def test_action_confirmation_returns_adjusted_target():
    async def run():
        manager = ApprovalManager(has_clients=lambda: True)
        action = PendingAction(
            id="a3",
            tool="click",
            kind="point",
            target={"x": 0.2, "y": 0.2},
            summary="单击",
            decision_required=True,
        )
        task = asyncio.create_task(manager.request_action(action))
        await asyncio.sleep(0)

        assert await manager.resolve_action("a3", True, {"x": 0.8, "y": 0.9}) is True
        decision = await task

        assert decision["approved"] is True
        assert decision["target"] == {"x": 0.8, "y": 0.9}

    asyncio.run(run())


def test_action_without_clients_is_rejected():
    async def run():
        manager = ApprovalManager(has_clients=lambda: False)
        action = PendingAction(
            id="a4",
            tool="open_terminal",
            kind="command",
            target={"command": "echo hi"},
            summary="终端命令",
            decision_required=True,
        )

        decision = await manager.request_action(action)

        assert decision["approved"] is False
        assert "无手机端在线" in decision["reason"]

    asyncio.run(run())


def test_action_confirmation_timeout():
    async def run():
        manager = ApprovalManager(has_clients=lambda: True)
        action = PendingAction(
            id="a5",
            tool="terminal_close",
            kind="terminal",
            target={"session_id": "s1"},
            summary="关闭终端",
            decision_required=True,
            expires_in=0.01,
        )

        decision = await manager.request_action(action)

        assert decision["approved"] is False
        assert "超时" in decision["reason"]
        assert manager.pending_actions == []

    asyncio.run(run())


def test_reject_all_covers_actions():
    async def run():
        manager = ApprovalManager(has_clients=lambda: True)
        action = PendingAction(
            id="a6",
            tool="terminal_close",
            kind="terminal",
            target={},
            summary="关闭终端",
            decision_required=True,
        )
        task = asyncio.create_task(manager.request_action(action))
        await asyncio.sleep(0)

        await manager.reject_all("任务已停止")
        decision = await task

        assert decision["approved"] is False
        assert decision["reason"] == "任务已停止"

    asyncio.run(run())


# ---------- Agent 集成 ----------


def test_smart_mode_auto_executes_gui_action(tmp_path):
    gateway = FakeGateway({"approved": True, "auto": True, "target": None, "reason": ""})
    agent, backend, _trust = make_agent(tmp_path, gateway)

    result, _change = asyncio.run(agent._guarded_action("click", {"x": 0.25, "y": 0.5}))

    assert result["ok"] is True
    assert backend.calls == [("click", (250, 250, "left"), {})]
    assert gateway.proposals[0].decision_required is False
    assert agent.last_action_meta["proposal_id"] == gateway.proposals[0].id


def test_confirm_mode_uses_adjusted_target(tmp_path):
    gateway = FakeGateway(
        {"approved": True, "auto": False, "target": {"x": 0.9, "y": 0.1}, "reason": ""}
    )
    agent, backend, trust = make_agent(tmp_path, gateway)
    trust.update(mode="confirm")

    result, _change = asyncio.run(agent._guarded_action("click", {"x": 0.1, "y": 0.1}))

    assert result["ok"] is True
    assert backend.calls == [("click", (900, 50, "left"), {})]
    assert gateway.proposals[0].decision_required is True


def test_confirm_mode_previews_move(tmp_path):
    gateway = FakeGateway(
        {"approved": True, "auto": False, "target": {"x": 0.05, "y": 0.05}, "reason": ""}
    )
    agent, backend, trust = make_agent(tmp_path, gateway)
    trust.update(mode="confirm")

    result, _change = asyncio.run(agent._guarded_action("move", {"x": 0.5, "y": 0.5}))

    assert result["ok"] is True
    assert gateway.proposals[0].kind == "point"
    assert gateway.proposals[0].decision_required is True
    assert backend.calls == [("move", (50, 25), {})]


def test_smart_mode_move_runs_after_visual_delay(tmp_path):
    gateway = FakeGateway({"approved": True, "auto": True, "target": None, "reason": ""})
    agent, backend, _trust = make_agent(tmp_path, gateway)

    result, _change = asyncio.run(agent._guarded_action("move", {"x": 0.4, "y": 0.4}))

    assert result["ok"] is True
    assert gateway.proposals[0].decision_required is False
    assert backend.calls == [("move", (400, 200), {})]


def test_rejected_preview_does_not_execute(tmp_path):
    gateway = FakeGateway({"approved": False, "auto": False, "target": None, "reason": "用户拒绝"})
    agent, backend, trust = make_agent(tmp_path, gateway)
    trust.update(mode="confirm")

    result, _change = asyncio.run(agent._guarded_action("click", {"x": 0.3, "y": 0.3}))

    assert result["ok"] is False
    assert "动作预览被拒绝" in result["error"]
    assert backend.calls == []


def test_off_mode_skips_preview(tmp_path):
    gateway = FakeGateway({"approved": True, "auto": True, "target": None, "reason": ""})
    agent, backend, trust = make_agent(tmp_path, gateway)
    trust.update(mode="off")

    result, _change = asyncio.run(agent._guarded_action("click", {"x": 0.3, "y": 0.3}))

    assert result["ok"] is True
    assert gateway.proposals == []
    assert backend.calls


def test_terminal_preview_replaces_second_review(tmp_path, monkeypatch):
    import geass.tools as tools_module

    monkeypatch.setattr(tools_module, "open_terminal", lambda command="": {"ok": True})
    gateway = FakeGateway({"approved": True, "auto": False, "target": None, "reason": ""})
    agent, _backend, _trust = make_agent(tmp_path, gateway)

    result, _change = asyncio.run(
        agent._guarded_action("open_terminal", {"command": "rm -rf /tmp/geass-test"})
    )

    assert result["ok"] is True
    assert len(gateway.proposals) == 1
    assert gateway.proposals[0].decision_required is True
    assert "递归" in gateway.proposals[0].security_reason
    assert gateway.command_reviews == []


def test_mcp_tool_uses_generic_preview(tmp_path):
    class FakeMCP:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        async def call(self, name: str, args: dict) -> dict:
            self.calls.append((name, args))
            return {"ok": True, "result": "done"}

    gateway = FakeGateway({"approved": True, "auto": False, "target": None, "reason": ""})
    agent, _backend, _trust = make_agent(tmp_path, gateway)
    fake_mcp = FakeMCP()
    agent.mcp = fake_mcp  # type: ignore[assignment]

    result, _change = asyncio.run(agent._guarded_action("mcp__demo__add", {"a": 1}))

    assert result["ok"] is True
    assert fake_mcp.calls == [("mcp__demo__add", {"a": 1})]
    assert gateway.proposals[0].kind == "generic"
    assert gateway.proposals[0].decision_required is True


def test_smart_mode_without_clients(tmp_path, monkeypatch):
    import geass.tools as tools_module

    monkeypatch.setattr(tools_module, "open_terminal", lambda command="": {"ok": True})
    backend = FakeBackend(size=(1000, 500))
    trust = TrustManager(tmp_path / ".trust.json")
    trust.update(visual_delay_ms=0)
    manager = ApprovalManager(has_clients=lambda: False)
    agent = Agent(
        client=None,
        backend=backend,
        capture=FakeCapture(),  # type: ignore[arg-type]
        config=AgentConfig(model="test"),
        security=SecurityConfig(enabled=True),
        approval_gateway=manager,
        trust=trust,
    )

    click_result, _change = asyncio.run(agent._guarded_action("click", {"x": 0.5, "y": 0.5}))
    terminal_result, _change = asyncio.run(
        agent._guarded_action("open_terminal", {"command": "echo hi"})
    )

    assert click_result["ok"] is True
    assert backend.calls
    assert terminal_result["ok"] is False
    assert "无手机端在线" in terminal_result["error"]


def test_make_agent_wires_manager_objects():
    state = make_state()

    agent = build_server_agent(state)

    assert agent.trust is state.trust
    assert agent.approval_gateway is state.approval_manager


def test_confirmation_roundtrip_with_real_manager(tmp_path):
    async def run():
        manager = ApprovalManager(has_clients=lambda: True)
        backend = FakeBackend(size=(1000, 500))
        trust = TrustManager(tmp_path / ".trust.json")
        trust.update(mode="confirm")
        agent = Agent(
            client=None,
            backend=backend,
            capture=FakeCapture(),  # type: ignore[arg-type]
            config=AgentConfig(model="test"),
            approval_gateway=manager,
            trust=trust,
        )

        task = asyncio.create_task(agent._guarded_action("move", {"x": 0.2, "y": 0.2}))
        for _ in range(50):
            if manager.pending_actions:
                break
            await asyncio.sleep(0)
        proposals = manager.pending_actions
        assert proposals and proposals[0].kind == "point"
        await manager.resolve_action(proposals[0].id, True, {"x": 0.05, "y": 0.05})
        result, _change = await task

        assert result["ok"] is True
        assert backend.calls == [("move", (50, 25), {})]

    asyncio.run(run())


def test_state_agent_preview_roundtrip():
    """回归：线上装配（approval_gateway 必须是管理器对象）能完成预览确认。"""

    async def run():
        state = make_state()
        agent = build_server_agent(state)
        state.trust.update(mode="confirm")
        state.approval_manager.has_clients = lambda: True

        task = asyncio.create_task(agent._guarded_action("move", {"x": 0.3, "y": 0.3}))
        for _ in range(50):
            if state.approval_manager.pending_actions:
                break
            await asyncio.sleep(0)
        proposals = state.approval_manager.pending_actions
        assert proposals and proposals[0].decision_required is True
        await state.approval_manager.resolve_action(proposals[0].id, True, {"x": 0.1, "y": 0.1})
        result, _change = await task

        assert result["ok"] is True
        assert state.backend.calls == [("move", (192, 108), {})]

    asyncio.run(run())
