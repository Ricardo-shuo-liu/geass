from __future__ import annotations

import asyncio

from geass.cli.session import CILSession
from geass.cli.tui import TUI
from geass.config import AgentConfig
from geass.evolution import POTStore

from .conftest import FakeMessage, FakeOpenAI, FakeResponse


def make_config() -> AgentConfig:
    config = AgentConfig(model="gpt-test")
    config.cli_rounds = 1
    config.cli_subagents = 2
    config.pot_rot_hits = 2
    return config


def test_cil_light_chat(tmp_path):
    client = FakeOpenAI(
        [FakeResponse(message=FakeMessage(content="你好，有什么可以帮你？"))]
    )
    tui = TUI()
    session = CILSession(
        client=client,
        config=make_config(),
        tui=tui,
    )

    answer = asyncio.run(session._chat("你好", tool_use=True))

    assert "有什么可以帮你" in answer
    assert tui.messages[-1][0] == "CIL"


def test_cil_deliberate_debate(tmp_path):
    pot = POTStore(tmp_path / ".pot")
    pot.save_rot("安全视角", "关注安全", "安全工程师", "检查风险")
    pot.save_rot("效率视角", "关注效率", "效率专家", "减少重复")
    client = FakeOpenAI(
        [
            FakeResponse(message=FakeMessage(content="安全角度：先检查。")),
            FakeResponse(message=FakeMessage(content="效率角度：再优化。")),
            FakeResponse(message=FakeMessage(content="汇总：先安全后效率。")),
        ]
    )
    tui = TUI()
    session = CILSession(
        client=client,
        config=make_config(),
        pot=pot,
        tui=tui,
    )

    answer = asyncio.run(session._deliberate("如何执行这个命令？"))

    assert "先安全后效率" in answer
    roles = [role for role, _ in tui.messages]
    assert "第1轮 · 安全视角" in roles
    assert "第1轮 · 效率视角" in roles
    assert "主 Agent" in roles


def test_cil_deliberate_slash_switches_mode(tmp_path):
    session = CILSession(
        client=FakeOpenAI([]),
        config=make_config(),
        tui=TUI(),
    )

    asyncio.run(session._slash("/deliberate"))
    assert session.mode == "deliberate"
    asyncio.run(session._slash("/light"))
    assert session.mode == "light"


def test_cil_chat_tools_use_nested_function_schema(tmp_path):
    client = FakeOpenAI(
        [FakeResponse(message=FakeMessage(content="完成"))]
    )
    session = CILSession(
        client=client,
        config=make_config(),
        tui=TUI(),
    )

    asyncio.run(session._chat("任务", tool_use=True))

    tools = client.requests[0]["tools"]
    assert tools[0]["type"] == "function"
    assert "function" in tools[0]
    assert tools[0]["function"]["name"] == "recall"


def test_cil_quit_words_exit_session(tmp_path):
    class QuitTUI(TUI):
        def ask(self, prompt: str = "") -> str:
            return "q"

    session = CILSession(
        client=FakeOpenAI([]),
        config=make_config(),
        tui=QuitTUI(),
    )

    asyncio.run(session.run())

    assert session.tui.messages[-1][1] == "再见。"
