from __future__ import annotations

import sys

import pytest

from geass.io.backend import InputError, PyAutoGUIInputBackend


class FakePG:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def write(self, text: str, interval: float = 0.0) -> None:
        self.calls.append(("write", text, interval))

    def press(self, key: str) -> None:
        self.calls.append(("press", key))

    def hotkey(self, *keys: str) -> None:
        self.calls.append(("hotkey", keys))


class FakeClipboard:
    def __init__(self) -> None:
        self.value = ""

    def paste(self) -> str:
        return self.value

    def copy(self, text: str) -> None:
        self.value = text


def build_backend(pg: FakePG | None = None) -> tuple[PyAutoGUIInputBackend, FakePG]:
    backend = PyAutoGUIInputBackend()
    fake = pg or FakePG()
    backend._pg = fake  # 跳过真实 pyautogui 初始化
    return backend, fake


def test_ascii_text_uses_write():
    backend, fake = build_backend()

    backend.type_text("hello world")

    assert fake.calls == [("write", "hello world", 0.01)]


def test_non_ascii_text_uses_clipboard_paste(monkeypatch):
    clipboard = FakeClipboard()
    monkeypatch.setitem(sys.modules, "pyperclip", clipboard)
    backend, fake = build_backend()

    backend.type_text("你好，世界")

    assert fake.calls[-1] == ("hotkey", ("ctrl", "v"))
    assert clipboard.value == ""  # 粘贴后恢复了原剪贴板内容


def test_non_ascii_falls_back_to_write_without_clipboard():
    backend, fake = build_backend()

    backend.type_text("中文")

    assert fake.calls == [("write", "中文", 0.01)]


def test_key_aliases_are_normalized():
    backend, fake = build_backend()

    backend.key_press("control+alt+delete")
    backend.key_press("cmd+c")
    backend.key_press("return")

    assert fake.calls == [
        ("hotkey", ("ctrl", "alt", "delete")),
        ("hotkey", ("super", "c")),
        ("press", "enter"),
    ]


def test_key_press_failure_is_wrapped():
    class RaisingPG(FakePG):
        def press(self, key: str) -> None:
            raise ValueError("invalid key")

    backend, _ = build_backend(RaisingPG())

    with pytest.raises(InputError, match="按键"):
        backend.key_press("not-a-real-key")


def test_initialization_failure_is_wrapped(monkeypatch):
    backend = PyAutoGUIInputBackend()

    def boom():
        raise RuntimeError("no display")

    monkeypatch.setattr("builtins.__import__", lambda *args, **kwargs: boom())
    with pytest.raises(InputError, match="pyautogui"):
        backend.screen_size()
