from __future__ import annotations

import asyncio
import json

from geass.config import AgentConfig
from geass.evolution import EvolutionEngine
from geass.memory import Memory
from geass.skills import load_skills

from .conftest import FakeMessage, FakeOpenAI, FakeResponse


def build_engine(tmp_path, script, memory: Memory | None = None):
    client = FakeOpenAI(script)
    engine = EvolutionEngine(
        client=client,
        config=AgentConfig(model="gpt-test"),
        memory=memory or Memory(tmp_path / ".memory"),
        skill_root=tmp_path / ".skill",
        source_dir=tmp_path / "skills",
    )
    return engine, client


def test_evolve_once_creates_skill_and_emits_status(tmp_path):
    events = []

    async def callback(message):
        events.append(message)

    payload = {
        "create": True,
        "name": "My Browser!",
        "description": "打开常用网址",
        "body": "# 步骤\n\n调用 `browser` 打开目标页面。",
        "reason": "用户频繁打开浏览器",
    }
    engine, _ = build_engine(
        tmp_path,
        [FakeResponse(message=FakeMessage(content=json.dumps(payload)))],
    )
    engine.status_cb = callback
    engine.memory.remember("常用功能", "打开浏览器")

    result = asyncio.run(engine.evolve_once())

    assert result["created"] is True
    assert result["name"] == "my-browser"
    skill_file = engine.root / "my-browser" / "SKILL.md"
    assert skill_file.is_file()
    content = skill_file.read_text(encoding="utf-8")
    assert content.startswith("---\nname: my-browser\n")
    assert "调用 `browser`" in content
    assert events[-1]["type"] == "evolution_status"
    assert events[-1]["name"] == "my-browser"
    assert (engine.evolution_dir / "history.jsonl").is_file()


def test_evolve_once_skips_when_model_declines(tmp_path):
    engine, _ = build_engine(
        tmp_path,
        [
            FakeResponse(
                message=FakeMessage(
                    content=json.dumps(
                        {"create": False, "reason": "没有新价值"}
                    )
                )
            )
        ],
    )
    engine.memory.remember("常用功能", "打开浏览器")

    result = asyncio.run(engine.evolve_once())

    assert result == {"created": False, "reason": "没有新价值"}
    assert not (engine.root / "anything" / "SKILL.md").exists()


def test_evolve_once_respects_skill_cap(tmp_path):
    engine, _ = build_engine(
        tmp_path,
        [FakeResponse(message=FakeMessage(content="{}"))],
    )
    engine.config.evolution_max_skills = 0
    engine.memory.remember("常用功能", "打开浏览器")

    result = asyncio.run(engine.evolve_once())

    assert result["created"] is False
    assert "上限" in result["reason"]


def test_record_task_persists_and_trims(monkeypatch, tmp_path):
    import geass.evolution as evolution_module

    monkeypatch.setattr(evolution_module, "HISTORY_LIMIT", 2)
    engine, _ = build_engine(tmp_path, [])

    for text in ("任务一", "任务二", "任务三"):
        engine.record_task(text)

    lines = engine.tasks_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "任务三" in lines[-1]
    assert "任务一" not in "\n".join(lines)


def test_run_evolves_after_idle(monkeypatch, tmp_path):
    import geass.evolution as evolution_module

    monkeypatch.setattr(evolution_module, "POLL_INTERVAL", 0.01)
    engine, _ = build_engine(tmp_path, [])
    engine.config.evolution_idle_seconds = 0.0
    engine.config.evolution_interval = 0.0
    calls = []

    async def fake_evolve():
        calls.append(True)
        return {"created": False}

    engine.evolve_once = fake_evolve  # type: ignore[method-assign]

    async def run():
        cancel = asyncio.Event()
        task = asyncio.create_task(engine.run(cancel))
        await asyncio.sleep(0.06)
        cancel.set()
        await task

    asyncio.run(run())
    assert calls


def test_generated_skill_is_loaded_next_scan(tmp_path):
    engine, _ = build_engine(
        tmp_path,
        [
            FakeResponse(
                message=FakeMessage(
                    content=json.dumps(
                        {
                            "create": True,
                            "name": "daily-workflow",
                            "description": "日常流程",
                            "body": "# 步骤\n\n等待后执行。",
                        }
                    )
                )
            )
        ],
    )
    engine.memory.remember("常用功能", "日常流程")
    asyncio.run(engine.evolve_once())

    names = {skill.name for skill in load_skills(engine.root)}
    assert "daily-workflow" in names
