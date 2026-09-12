from __future__ import annotations

import os

import pytest

from geass.server.trust import TrustManager


def test_defaults_and_persistence(tmp_path):
    path = tmp_path / ".trust.json"
    manager = TrustManager(path)

    assert manager.settings() == {
        "mode": "smart",
        "visual_delay_ms": 600,
        "overrides": {},
        "task_allow_all": False,
    }

    manager.update(mode="confirm", visual_delay_ms=1200, overrides={"open_terminal": "auto"})
    reloaded = TrustManager(path)

    assert reloaded.mode == "confirm"
    assert reloaded.visual_delay_ms == 1200
    assert reloaded.override_for("open_terminal") == "auto"
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_update_validates_values(tmp_path):
    manager = TrustManager(tmp_path / ".trust.json")

    manager.update(mode="off", visual_delay_ms=99999)
    assert manager.mode == "off"
    assert manager.visual_delay_ms == 2000

    with pytest.raises(ValueError):
        manager.update(mode="unknown")
    with pytest.raises(ValueError):
        manager.update(overrides={"click": "maybe"})

    manager.update(overrides={"click": None})
    assert manager.override_for("click") is None


def test_requires_confirmation_matrix(tmp_path):
    manager = TrustManager(tmp_path / ".trust.json")

    # smart 默认：GUI 自动，终端/MCP 确认
    assert manager.requires_confirmation("click") is False
    assert manager.requires_confirmation("type_text") is False
    assert manager.requires_confirmation("terminal_close") is True
    assert manager.requires_confirmation("open_terminal", command_present=True) is True
    assert manager.requires_confirmation("terminal_type", may_execute=False) is False
    assert manager.requires_confirmation("terminal_type", may_execute=True) is True
    assert manager.requires_confirmation("mcp__demo__add") is True

    # 黑名单命中无法被覆盖为自动
    manager.update(overrides={"open_terminal": "auto"})
    assert manager.requires_confirmation("open_terminal", command_present=True) is False
    assert manager.requires_confirmation("open_terminal", security_blocked=True) is True

    # confirm / off 模式
    manager.update(mode="confirm")
    assert manager.requires_confirmation("click") is True
    manager.update(mode="off")
    assert manager.requires_confirmation("terminal_close") is False


def test_task_allow_all_resets_on_new_task(tmp_path):
    manager = TrustManager(tmp_path / ".trust.json")

    manager.update(task_allow_all=True)
    assert manager.requires_confirmation("terminal_close") is False

    manager.begin_task()
    assert manager.settings()["task_allow_all"] is False
    assert manager.requires_confirmation("terminal_close") is True
