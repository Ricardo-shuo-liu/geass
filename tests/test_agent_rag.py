from __future__ import annotations

import asyncio

from geass.rag import RAGManager

from .conftest import FakeMessage, FakeResponse, FakeToolCall
from .test_agent import build


def make_manager(tmp_path) -> RAGManager:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "guide.md").write_text(
        "打开终端的方法：按 ctrl+alt+t，然后输入命令。",
        encoding="utf-8",
    )
    manager = RAGManager(tmp_path / ".rag")
    manager.add_source(root, name="docs")
    return manager


def test_rag_tools_via_agent(tmp_path):
    agent, _, _ = build([])
    agent.rag = make_manager(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    (other / "note.md").write_text("另一个数据源", encoding="utf-8")

    added = asyncio.run(
        agent._execute(
            "rag_add",
            {"path": str(other), "name": "other"},
        )
    )
    assert added["ok"] is True

    listed = asyncio.run(agent._execute("rag_list", {}))
    assert listed["count"] >= 2

    searched = asyncio.run(agent._execute("rag_search", {"query": "打开终端", "limit": 2}))
    assert searched["found"] is True
    assert searched["matches"][0]["text"] == "打开终端的方法：按 ctrl+alt+t，然后输入命令。"

    removed = asyncio.run(
        agent._execute(
            "rag_remove",
            {"source": "other", "rel_path": "note.md"},
        )
    )
    assert removed["removed"] is True


def test_rag_context_injected_into_system_prompt(tmp_path):
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
    agent.rag = make_manager(tmp_path)

    result = asyncio.run(agent.run("怎么打开终端"))

    assert result["state"] == "done"
    system_prompt = client.requests[0]["messages"][0]["content"]
    assert "RAG 参考资料" in system_prompt
    assert "打开终端的方法" in system_prompt


def test_rag_injection_can_be_disabled(tmp_path):
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
    agent.rag = make_manager(tmp_path)
    agent.config.rag_inject_enabled = False

    asyncio.run(agent.run("怎么打开终端"))

    system_prompt = client.requests[0]["messages"][0]["content"]
    assert "RAG 参考资料" not in system_prompt
