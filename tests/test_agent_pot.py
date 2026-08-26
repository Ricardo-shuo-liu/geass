from __future__ import annotations

import asyncio

from geass.evolution import POTStore

from .conftest import FakeMessage, FakeResponse, FakeToolCall
from .test_agent import build


def make_pot(tmp_path) -> POTStore:
    store = POTStore(tmp_path / ".pot")
    store.set_cot("先明确目标，再拆解步骤，最后验证。")
    store.save_rot("工程师视角", "严谨分析", "严谨工程师", "先验证再下结论。")
    return store


def test_pot_context_injected_into_system_prompt(tmp_path):
    script = [
        FakeResponse(
            message=FakeMessage(
                tool_calls=[
                    FakeToolCall("call_1", "finish", '{"summary": "完成"}'),
                ]
            )
        )
    ]
    agent, _, client = build(script)
    agent.pot = make_pot(tmp_path)

    asyncio.run(agent.run("分析这个问题"))

    system_prompt = client.requests[0]["messages"][0]["content"]
    assert "Global-COT" in system_prompt
    assert "ROT「工程师视角」" in system_prompt


def test_pot_tools_via_agent(tmp_path):
    agent, _, _ = build([])
    agent.pot = make_pot(tmp_path)

    listed = asyncio.run(agent._execute("pot_list", {}))
    assert listed["ok"] is True
    assert len(listed["rots"]) == 1

    used = asyncio.run(
        agent._execute("pot_use", {"name": "工程师视角"})
    )
    assert used["ok"] is True
    assert agent.pinned_rot == "工程师视角"
