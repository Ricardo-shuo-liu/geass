"""输入后端抽象：把归一化动作落到真实的键鼠操作。"""
from __future__ import annotations

import abc


class InputError(Exception):
    """输入操作失败。"""


class InputBackend(abc.ABC):
    @abc.abstractmethod
    def screen_size(self) -> tuple[int, int]:
        ...

    @abc.abstractmethod
    def move(self, x: int, y: int) -> None:
        ...

    @abc.abstractmethod
    def click(self, x: int, y: int, button: str = "left") -> None:
        ...

    @abc.abstractmethod
    def double_click(self, x: int, y: int) -> None:
        ...

    @abc.abstractmethod
    def right_click(self, x: int, y: int) -> None:
        ...

    @abc.abstractmethod
    def scroll(self, dx: int, dy: int) -> None:
        ...

    @abc.abstractmethod
    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None:
        ...

    @abc.abstractmethod
    def type_text(self, text: str) -> None:
        ...

    @abc.abstractmethod
    def key_press(self, combo: str) -> None:
        ...


class PyAutoGUIInputBackend(InputBackend):
    """Linux X11 / Windows / macOS 通用后端（Wayland 除外）。"""

    def __init__(self, pause: float = 0.03) -> None:
        self._pause = pause
        self._pg = None

    def _pg_ensure(self):
        # 惰性导入：pyautogui 在 import 时就会连接 X display，
        # 这里延迟到真正操作键鼠时才初始化。
        if self._pg is None:
            import pyautogui

            self._pg = pyautogui
            self._pg.PAUSE = self._pause
            self._pg.FAILSAFE = True
        return self._pg

    def screen_size(self) -> tuple[int, int]:
        width, height = self._pg_ensure().size()
        return int(width), int(height)

    def move(self, x: int, y: int) -> None:
        self._pg_ensure().moveTo(x, y, duration=0.08)

    def click(self, x: int, y: int, button: str = "left") -> None:
        self._pg_ensure().click(x, y, button=button)

    def double_click(self, x: int, y: int) -> None:
        self._pg_ensure().doubleClick(x, y)

    def right_click(self, x: int, y: int) -> None:
        self._pg_ensure().rightClick(x, y)

    def scroll(self, dx: int, dy: int) -> None:
        pg = self._pg_ensure()
        if dy:
            pg.scroll(int(dy))
        if dx:
            hscroll = getattr(pg, "hscroll", None)
            if hscroll is not None:
                hscroll(int(dx))

    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None:
        pg = self._pg_ensure()
        pg.moveTo(x1, y1)
        pg.dragTo(x2, y2, duration=0.2, button="left")

    def type_text(self, text: str) -> None:
        self._pg_ensure().write(text, interval=0.01)

    def key_press(self, combo: str) -> None:
        pg = self._pg_ensure()
        keys = [key.strip().lower() for key in combo.split("+") if key.strip()]
        if not keys:
            return
        if len(keys) == 1:
            pg.press(keys[0])
        else:
            pg.hotkey(*keys)
