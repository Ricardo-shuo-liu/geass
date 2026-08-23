from __future__ import annotations

import asyncio

from geass.agent import Agent
from geass.config import AgentConfig
from geass.skills import (
    catalog_text,
    find_skill,
    load_skills,
    resolve_skill_root,
    sync_system_skills,
)

from .conftest import FakeBackend, FakeCapture


def write_skill(root, name: str = "echo-hello") -> None:
    skill_dir = root / name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        'description: 在可见终端中输出 hello world\n'
        "---\n\n"
        "# 步骤\n\n"
        '调用 `open_terminal` 执行 `echo "hello world"`。\n',
        encoding="utf-8",
    )
    (skill_dir / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")


def test_load_skills_parses_frontmatter_and_files(tmp_path):
    write_skill(tmp_path)

    skills = load_skills(tmp_path)

    assert len(skills) == 1
    skill = skills[0]
    assert skill.name == "echo-hello"
    assert skill.description == "在可见终端中输出 hello world"
    assert "open_terminal" in skill.body
    assert skill.files() == ["run.sh"]
    assert "echo-hello" in catalog_text(skills)
    assert find_skill(skills, "echo-hello") is skill
    assert find_skill(skills, "missing") is None


def test_load_skills_without_frontmatter_uses_directory_name(tmp_path):
    skill_dir = tmp_path / "plain"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "# 说明\n\n这是一个没有 frontmatter 的技能。\n", encoding="utf-8"
    )

    skills = load_skills(tmp_path)

    assert skills[0].name == "plain"
    assert skills[0].description == "这是一个没有 frontmatter 的技能。"


def test_agent_skill_tools_expose_catalog_and_body(tmp_path):
    write_skill(tmp_path)
    skills = load_skills(tmp_path)
    agent = Agent(
        client=None,
        backend=FakeBackend(),
        capture=FakeCapture(),
        config=AgentConfig(model="x"),
        skills=skills,
    )

    listed = asyncio.run(agent._execute("list_skills", {}))
    read = asyncio.run(agent._execute("read_skill", {"name": "echo-hello"}))
    missing = asyncio.run(agent._execute("read_skill", {"name": "nope"}))

    assert listed["ok"] is True
    assert listed["skills"][0]["name"] == "echo-hello"
    assert read["ok"] is True
    assert 'echo "hello world"' in read["content"]
    assert "run.sh" in read["content"]
    assert missing["ok"] is False


def test_load_skills_reads_system_and_evolved_with_override(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GEASS_HOME", str(tmp_path / "home"))
    root = resolve_skill_root(None)
    system = root / ".system"
    (system / "base").mkdir(parents=True)
    (system / "base" / "SKILL.md").write_text(
        "---\nname: base\ndescription: 系统技能\n---\n\nbody\n",
        encoding="utf-8",
    )
    (root / "evolved").mkdir(parents=True)
    (root / "evolved" / "SKILL.md").write_text(
        "---\nname: base\ndescription: 进化后覆盖\n---\n\nnew body\n",
        encoding="utf-8",
    )

    skills = load_skills(root)

    assert [skill.name for skill in skills] == ["base"]
    assert skills[0].description == "进化后覆盖"
    assert skills[0].body == "new body"


def test_sync_system_skills_copies_and_prunes(tmp_path, monkeypatch):
    monkeypatch.setenv("GEASS_HOME", str(tmp_path / "home"))
    source = tmp_path / "skills"
    (source / "keep").mkdir(parents=True)
    (source / "keep" / "SKILL.md").write_text(
        "---\nname: keep\ndescription: keep\n---\n\nbody\n",
        encoding="utf-8",
    )
    root = resolve_skill_root(None)
    (root / ".system" / "stale").mkdir(parents=True)
    (root / ".system" / "stale" / "SKILL.md").write_text(
        "---\nname: stale\ndescription: stale\n---\n\nbody\n",
        encoding="utf-8",
    )
    (root / "evolved").mkdir(parents=True)
    (root / "evolved" / "SKILL.md").write_text(
        "---\nname: evolved\ndescription: evolved\n---\n\nbody\n",
        encoding="utf-8",
    )

    sync_system_skills(source, root)
    skills = load_skills(root)

    assert (root / ".system" / "keep" / "SKILL.md").is_file()
    assert not (root / ".system" / "stale").exists()
    assert {skill.name for skill in skills} == {"keep", "evolved"}
