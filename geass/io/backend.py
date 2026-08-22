"""输入后端抽象：把归一化动作落到真实的键鼠操作。"""
from __future__ import annotations

import abc
import platform


class InputError(Exception):
    """输入操作失败。"""


def _super_key() -> str:
    """按平台返回主修饰键名称（super/win/command）。"""
    system = platform.system()
    if system == "Darwin":
        return "command"
    if system == "Windows":
        return "win"
    return "super"


_SUPER = _super_key()

# pyautogui 的按键名与常见写法的归一化别名。
_KEY_ALIASES = {
    "control": "ctrl",
    "return": "enter",
    "del": "delete",
    "spacebar": "space",
    "esc": "escape",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "cmd": _SUPER,
    "command": _SUPER,
    "meta": _SUPER,
    "windows": _SUPER,
    "win": _SUPER,
}

_PASTE_KEYS = ("command", "v") if platform.system() == "Darwin" else ("ctrl", "v")


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
            try:
                import pyautogui
            except Exception as exc:
                raise InputError(
                    f"初始化 pyautogui 失败，可能没有可用的图形环境：{exc}"
                ) from exc

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
        pg = self._pg_ensure()
        if text.isascii():
            try:
                pg.write(text, interval=0.01)
                return
            except Exception as exc:
                raise InputError(f"键盘输入失败：{exc}") from exc

        # 非 ASCII 文本（如中文）逐键写入依赖 IME，几乎必然失败；
        # 优先复制到剪贴板再粘贴，剪贴板不可用时退回逐键写入。
        try:
            import pyperclip

            previous = pyperclip.paste()
            pyperclip.copy(text)
            try:
                pg.hotkey(*_PASTE_KEYS)
            finally:
                pyperclip.copy(previous)
        except InputError:
            raise
        except Exception:
            try:
                pg.write(text, interval=0.01)
            except Exception as exc:
                raise InputError(f"键盘输入失败（剪贴板与逐键写入均不可用）：{exc}") from exc

    def key_press(self, combo: str) -> None:
        pg = self._pg_ensure()
        keys = [
            _KEY_ALIASES.get(key.strip().lower(), key.strip().lower())
            for key in combo.split("+")
            if key.strip()
        ]
        if not keys:
            return
        try:
            if len(keys) == 1:
                pg.press(keys[0])
            else:
                pg.hotkey(*keys)
        except Exception as exc:
            raise InputError(f"按键 {combo} 失败：{exc}") from exc
