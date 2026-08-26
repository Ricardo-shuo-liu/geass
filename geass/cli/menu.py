"""claude-cmd 风格主菜单：纯 ANSI 文本渲染，方向键导航，分组菜单。"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Callable

from .keys import raw_mode, read_key

ASCII_LOGO = r"""
  ____ _____    _    ____ ____
 / ___| ____|  / \  / ___/ ___|
| |  _|  _|   / _ \ \___ \___ \
| |_| | |___ / ___ \ ___) |__) |
 \____|_____/_/   \_\____/____/
"""

_ORANGE = "\x1b[38;5;214m"
_WHITE = "\x1b[37m"
_DIM = "\x1b[90m"
_CYAN = "\x1b[1;36m"
_RESET = "\x1b[0m"
_HIDE = "\x1b[?25l"
_SHOW = "\x1b[?25h"
_CLEAR = "\x1b[2J\x1b[H"
_ALT_ON = "\x1b[?1049h"
_ALT_OFF = "\x1b[?1049l"


@dataclass
class MenuItem:
    kind: str
    label: str
    action: str = ""
    icon: str = ""


def default_menu_items() -> list[MenuItem]:
    return [
        MenuItem("group", "会话"),
        MenuItem("option", "进入 CLI 对话（light）", "chat", "💬"),
        MenuItem("group", "资产"),
        MenuItem("option", "查看 SKILL 技能", "skills", "📚"),
        MenuItem("option", "查看 RAG 数据源", "rag", "🗂️"),
        MenuItem("option", "查看 POT（COT/ROT）", "pot", "🪄"),
        MenuItem("option", "查看持久记忆", "memory", "🧾"),
        MenuItem("group", "Configuration"),
        MenuItem("option", "查看配置", "config", "⚙️"),
        MenuItem("option", "帮助 / 关于", "help", "📖"),
        MenuItem("exit", "退出", "exit", "🚪"),
    ]


class MenuModel:
    """菜单导航逻辑（与渲染/按键读取解耦，便于测试）。"""

    def __init__(self, items: list[MenuItem]) -> None:
        self.items = items
        self.index = 0
        indexes = self.option_indexes()
        if indexes:
            self.index = indexes[0]

    def option_indexes(self) -> list[int]:
        return [
            index
            for index, item in enumerate(self.items)
            if item.kind in ("option", "exit")
        ]

    def move(self, delta: int) -> None:
        indexes = self.option_indexes()
        if not indexes:
            return
        current = indexes.index(self.index) if self.index in indexes else 0
        current = (current + delta) % len(indexes)
        self.index = indexes[current]

    def handle(self, key: str) -> str | None:
        if key == "up":
            self.move(-1)
            return None
        if key == "down":
            self.move(1)
            return None
        if key == "home":
            self.index = self.option_indexes()[0]
            return None
        if key == "end":
            indexes = self.option_indexes()
            self.index = indexes[-1]
            return None
        if key in ("enter", "right"):
            item = self.items[self.index]
            if item.kind == "exit":
                return "exit"
            return item.action or None
        if key in ("quit", "esc", "ctrl_c"):
            return "exit"
        return None


class MenuApp:
    def __init__(
        self,
        items: list[MenuItem] | None = None,
        on_action: Callable[[str], None] | None = None,
    ) -> None:
        self.items = items or default_menu_items()
        self.model = MenuModel(self.items)
        self.on_action = on_action or (lambda _action: None)
        self.version = "0.1.0"
        self.author = "Ricardo-shuo-liu"

    def _text(self) -> str:
        lines: list[str] = []
        lines.append(_ORANGE + ASCII_LOGO.rstrip("\n") + _RESET)
        lines.append(_DIM + f"Geass CLI · v{self.version} · {self.author}" + _RESET)
        lines.append("")
        for index, item in enumerate(self.items):
            if item.kind == "group":
                lines.append(_DIM + f"--- {item.label} ---" + _RESET)
                continue
            selected = index == self.model.index
            prefix = "> " if selected else "  "
            style = _CYAN if selected else _WHITE
            icon = f"{item.icon} " if item.icon else ""
            lines.append(style + f"{prefix}{icon}{item.label}" + _RESET)
        lines.append("")
        lines.append(_DIM + "↑/↓ 导航 · Enter 确认 · q / Esc 退出" + _RESET)
        return "\n".join(lines) + "\n"

    @staticmethod
    def _clear_screen() -> None:
        if os.name == "nt":
            os.system("cls")
        else:
            sys.stdout.write(_CLEAR)

    def _redraw(self) -> None:
        self._clear_screen()
        sys.stdout.write(_HIDE + self._text())
        sys.stdout.flush()

    def run(self, key_source: Callable[[], str | None] | None = None) -> None:
        alt_screen = False
        try:
            if os.name != "nt":
                sys.stdout.write(_ALT_ON)
                sys.stdout.flush()
                alt_screen = True
            while True:
                self._redraw()
                action: str | None = None
                while action is None:
                    if key_source is not None:
                        key = key_source()
                    else:
                        with raw_mode():
                            key = read_key()
                    if key is None:
                        if key_source is None:
                            time.sleep(0.05)
                        continue
                    if key == "ctrl_c":
                        return
                    action = self.model.handle(key)
                    self._redraw()
                if action == "exit":
                    return
                sys.stdout.write(_SHOW + "\n")
                sys.stdout.flush()
                self.on_action(action)
                if key_source is None:
                    try:
                        input("按 Enter 返回菜单…")
                    except (EOFError, KeyboardInterrupt):
                        return
        finally:
            if alt_screen:
                sys.stdout.write(_ALT_OFF)
            sys.stdout.write(_SHOW + "\x1b[0m")
            sys.stdout.flush()
