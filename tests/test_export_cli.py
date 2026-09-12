from __future__ import annotations

import json
from pathlib import Path

import pytest

import geass.export as export_module
from geass.config import Config
from geass.dispatch import COMMANDS
from geass.evolution.pot import POTStore


def make_config(tmp_path: Path) -> Config:
    config = Config()
    config.agent.skill_root = str(tmp_path / ".geass" / ".skill")
    config.agent.pot_path = str(tmp_path / ".geass" / ".pot")
    return config


def write_skill(root: Path, name: str, body: str = "# 步骤\n1. echo hi\n") -> Path:
    skill_dir = root / name
    (skill_dir / "attachments").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} 演示\n---\n\n{body}",
        encoding="utf-8",
    )
    (skill_dir / "attachments" / "note.txt").write_text("note", encoding="utf-8")
    return skill_dir


def load_manifest(destination: Path) -> dict:
    return json.loads((destination / "manifest.json").read_text(encoding="utf-8"))


def test_export_selected_skill(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    skill_dir = write_skill(Path(config.agent.skill_root), "demo")
    monkeypatch.setattr(export_module, "load_config", lambda persist=False: config)
    destination = tmp_path / "out"

    export_module.main(["skill", "demo", "--to", str(destination)])

    assert (destination / "skills" / "demo" / "SKILL.md").read_text(encoding="utf-8") == (
        skill_dir / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert (destination / "skills" / "demo" / "attachments" / "note.txt").exists()
    manifest = load_manifest(destination)
    assert [item["name"] for item in manifest["items"]] == ["demo"]
    assert manifest["items"][0]["files"] == ["SKILL.md", "attachments/note.txt"]


def test_export_conflicts_require_force(tmp_path, monkeypatch, capsys):
    config = make_config(tmp_path)
    write_skill(Path(config.agent.skill_root), "demo")
    monkeypatch.setattr(export_module, "load_config", lambda persist=False: config)
    destination = tmp_path / "out"

    export_module.main(["skill", "demo", "--to", str(destination)])
    with pytest.raises(SystemExit, match="--force"):
        export_module.main(["skill", "demo", "--to", str(destination)])

    export_module.main(["skill", "demo", "--to", str(destination), "--force"])
    assert "已导出" in capsys.readouterr().out


def test_export_all_assets_includes_disabled_rot(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    write_skill(Path(config.agent.skill_root), "demo")
    store = POTStore(config.agent.pot_path)
    store.set_cot("先验证再执行")
    store.save_rot("security", "安全视角", "安全工程师", "检查风险")
    store.save_rot("speed", "效率视角", "效率专家", "减少重复", enabled=False)
    monkeypatch.setattr(export_module, "load_config", lambda persist=False: config)
    destination = tmp_path / "out"

    export_module.main(["all", "--to", str(destination)])

    assert (destination / "pot" / "cot.md").read_text(encoding="utf-8").strip() == "先验证再执行"
    assert (destination / "pot" / "rot" / "security.md").exists()
    assert (destination / "pot" / "rot" / "speed.md").exists()
    names = {(item["type"], item["name"]) for item in load_manifest(destination)["items"]}
    assert names == {
        ("skill", "demo"),
        ("cot", "global-cot"),
        ("rot", "security"),
        ("rot", "speed"),
    }


def test_export_rot_enabled_only(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    store = POTStore(config.agent.pot_path)
    store.save_rot("security", "安全视角", "安全工程师", "检查风险")
    store.save_rot("speed", "效率视角", "效率专家", "减少重复", enabled=False)
    monkeypatch.setattr(export_module, "load_config", lambda persist=False: config)
    destination = tmp_path / "out"

    export_module.main(["rot", "--all", "--enabled-only", "--to", str(destination)])

    assert (destination / "pot" / "rot" / "security.md").exists()
    assert not (destination / "pot" / "rot" / "speed.md").exists()


def test_export_manifest_merges_across_runs(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    write_skill(Path(config.agent.skill_root), "demo")
    store = POTStore(config.agent.pot_path)
    store.save_rot("security", "安全视角", "安全工程师", "检查风险")
    monkeypatch.setattr(export_module, "load_config", lambda persist=False: config)
    destination = tmp_path / "out"

    export_module.main(["skill", "demo", "--to", str(destination)])
    export_module.main(["rot", "security", "--to", str(destination)])

    names = {(item["type"], item["name"]) for item in load_manifest(destination)["items"]}
    assert names == {("skill", "demo"), ("rot", "security")}
    manifest = load_manifest(destination)
    assert Path(manifest["source"]["skill_root"]).is_absolute()
    assert Path(manifest["source"]["pot_root"]).is_absolute()


def test_export_cot_without_cot_warns(tmp_path, monkeypatch, capsys):
    config = make_config(tmp_path)
    monkeypatch.setattr(export_module, "load_config", lambda persist=False: config)
    destination = tmp_path / "out"

    export_module.main(["cot", "--to", str(destination)])

    assert "警告" in capsys.readouterr().out
    assert load_manifest(destination)["warnings"] == ["当前没有 Global-COT，已跳过"]


def test_export_missing_skill_exits(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    write_skill(Path(config.agent.skill_root), "demo")
    monkeypatch.setattr(export_module, "load_config", lambda persist=False: config)

    with pytest.raises(SystemExit, match="SKILL 不存在"):
        export_module.main(["skill", "missing", "--to", str(tmp_path / "out")])


def test_export_missing_rot_exits(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    monkeypatch.setattr(export_module, "load_config", lambda persist=False: config)

    with pytest.raises(SystemExit, match="ROT 不存在"):
        export_module.main(["rot", "missing", "--to", str(tmp_path / "out")])


def test_export_requires_selection(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    monkeypatch.setattr(export_module, "load_config", lambda persist=False: config)

    with pytest.raises(SystemExit, match="--all"):
        export_module.main(["skill", "--to", str(tmp_path / "out")])


def test_dispatch_lists_export_command():
    assert "export" in COMMANDS
