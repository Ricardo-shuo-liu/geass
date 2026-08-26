from __future__ import annotations

from geass.cli.keys import parse_sequence
from geass.cli.menu import MenuApp, MenuItem, MenuModel


def test_parse_sequences():
    assert parse_sequence(b"\r") == "enter"
    assert parse_sequence(b"\x1b[A") == "up"
    assert parse_sequence(b"\x1b[B") == "down"
    assert parse_sequence(b"\x00H") == "home"
    assert parse_sequence(b"\x1b[4~") == "end"
    assert parse_sequence(b"q") == "quit"
    assert parse_sequence(b"\x03") == "ctrl_c"
    assert parse_sequence(b"x") is None


def test_menu_model_skips_groups_and_wraps():
    items = [
        MenuItem("group", "会话"),
        MenuItem("option", "对话", "chat", "💬"),
        MenuItem("group", "资产"),
        MenuItem("option", "技能", "skills", "📚"),
        MenuItem("exit", "退出", "exit", "🚪"),
    ]
    model = MenuModel(items)

    assert model.index == 1
    model.handle("down")
    assert model.index == 3
    model.handle("down")
    assert model.index == 4
    model.handle("down")
    assert model.index == 1
    model.handle("up")
    assert model.index == 4


def test_menu_model_select_and_exit():
    items = [
        MenuItem("option", "对话", "chat"),
        MenuItem("exit", "退出", "exit"),
    ]
    model = MenuModel(items)

    assert model.handle("enter") == "chat"
    model.handle("down")
    assert model.handle("enter") == "exit"
    assert model.handle("esc") == "exit"


def test_menu_app_runs_selection_with_key_source():
    actions: list[str] = []
    keys = iter(["enter", "down", "enter"])
    app = MenuApp(
        items=[
            MenuItem("option", "对话", "chat"),
            MenuItem("exit", "退出", "exit"),
        ],
        on_action=actions.append,
    )

    app.run(key_source=lambda: next(keys, None))

    assert actions == ["chat"]
