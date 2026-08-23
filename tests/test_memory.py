from __future__ import annotations

import json

from geass.memory import Memory, default_memory_path


def test_remember_recall_and_forget(tmp_path, monkeypatch):
    path = tmp_path / ".memory"
    memory = Memory(path)

    memory.remember("default_browser", "firefox")
    memory.remember("用户偏好", "界面语言使用中文")
    memory.remember("home_dir", "/home/demo")

    browser_hits = memory.recall("browser")
    assert len(browser_hits) == 1
    assert browser_hits[0]["key"] == "default_browser"

    assert memory.recall("不存在") == []
    assert len(memory.recall("", limit=2)) == 2

    assert memory.forget("DEFAULT_BROWSER") is True
    assert memory.forget("default_browser") is False
    assert memory.recall("browser") == []


def test_remember_upserts_case_insensitively(tmp_path):
    memory = Memory(tmp_path / ".memory")
    first = memory.remember("key", "v1")
    second = memory.remember("KEY", "v2")

    assert second.id == first.id
    entries = memory.recall("key")
    assert len(entries) == 1
    assert entries[0]["value"] == "v2"


def test_memory_persists_across_instances(tmp_path):
    path = tmp_path / ".memory"
    Memory(path).remember("os", "ubuntu")

    reloaded = Memory(path)
    entries = reloaded.recall("os")
    assert entries[0]["value"] == "ubuntu"

    payload = json.loads((path / "entries.json").read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["entries"][0]["key"] == "os"


def test_max_entries_trims_oldest(tmp_path):
    memory = Memory(tmp_path / ".memory", max_entries=2)
    memory.remember("a", "1")
    memory.remember("b", "2")
    memory.remember("c", "3")

    assert memory.recall("a") == []
    assert {entry["key"] for entry in memory.recall("", limit=10)} == {"b", "c"}


def test_context_for_prefers_query_match(tmp_path):
    memory = Memory(tmp_path / ".memory")
    memory.remember("browser", "firefox")
    memory.remember("unrelated", "hello")

    context = memory.context_for("打开浏览器", limit=5)
    assert "firefox" in context
    assert "unrelated" in context  # 相关条目不足时补齐最近条目


def test_default_memory_path_respects_geass_home(tmp_path, monkeypatch):
    monkeypatch.setenv("GEASS_HOME", str(tmp_path))
    assert default_memory_path() == tmp_path / ".geass" / ".memory"
