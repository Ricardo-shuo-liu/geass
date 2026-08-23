from __future__ import annotations

from geass.server.state import build_state

from .conftest import make_config


def test_build_state_syncs_seed_skills_into_runtime_root(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GEASS_HOME", str(tmp_path / "home"))
    source = tmp_path / "skills"
    (source / "alpha").mkdir(parents=True)
    (source / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: 基础技能\n---\n\nbody\n",
        encoding="utf-8",
    )
    config = make_config()
    config.config_path = tmp_path / "config.toml"
    config.agent.skills_dir = str(source)

    state = build_state(config)

    assert [skill.name for skill in state.skills] == ["alpha"]
    runtime_root = tmp_path / "home" / ".geass" / ".skill"
    assert (runtime_root / ".system" / "alpha" / "SKILL.md").is_file()
    assert state.skill_root == runtime_root
