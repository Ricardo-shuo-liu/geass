from __future__ import annotations

import asyncio

from geass.agent import Agent
from geass.config import AgentConfig

from .conftest import FakeMessage, FakeOpenAI, FakeResponse


def build_messages() -> list[dict]:
    messages = [{"role": "system", "content": "system"}]
    for index in range(12):
        messages.append(
            {
                "role": "user" if index % 2 == 0 else "assistant",
                "content": f"第 {index} 段很长的对话内容" + "x" * 200,
            }
        )
    return messages


def test_context_compression_replaces_early_messages(tmp_path):
    client = FakeOpenAI([FakeResponse(message=FakeMessage(content="摘要：用户意图与关键结果"))])
    agent = Agent(
        client=client,
        backend=None,
        capture=None,
        config=AgentConfig(model="gpt-test"),
    )
    agent.config.context_compress_enabled = True
    agent.config.context_compress_after = 6
    agent.config.context_compress_chars = 500
    agent.compression_path = str(tmp_path / "compressed.jsonl")
    messages = build_messages()

    asyncio.run(agent._maybe_compress(messages))

    assert any("摘要" in str(message.get("content")) for message in messages)
    assert len(messages) <= 10
    assert (tmp_path / "compressed.jsonl").exists()


def test_context_compression_fallback_keeps_first_user(tmp_path):
    client = FakeOpenAI(
        [
            RuntimeError("压缩服务不可用"),
        ]
    )
    agent = Agent(
        client=client,
        backend=None,
        capture=None,
        config=AgentConfig(model="gpt-test"),
    )
    agent.config.context_compress_enabled = True
    agent.config.context_compress_after = 6
    agent.config.context_compress_chars = 500
    agent.compression_path = str(tmp_path / "compressed.jsonl")
    messages = build_messages()

    asyncio.run(agent._maybe_compress(messages))

    joined = " ".join(str(message.get("content")) for message in messages)
    assert "降级" in joined
    assert "第 0 段" in joined
