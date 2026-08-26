"""跨平台终端按键捕获（方向键/回车/Esc），不依赖第三方库。"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager


def parse_sequence(data: bytes) -> str | None:
    """把终端字节序列解析为语义按键。"""
    if data in (b"\r", b"\n"):
        return "enter"
    if data == b"\x1b":
        return "esc"
    if data in (b"\x1b[A", b"\x1bOA"):
        return "up"
    if data in (b"\x1b[B", b"\x1bOB"):
        return "down"
    if data in (b"\x1b[C", b"\x1bOC"):
        return "right"
    if data in (b"\x1b[D", b"\x1bOD"):
        return "left"
    if data in (b"\x1b[H", b"\x1b[1~", b"\x00H"):
        return "home"
    if data in (b"\x1b[F", b"\x1b[4~", b"\x00K"):
        return "end"
    if data in (b"q", b"Q"):
        return "quit"
    if data == b"\x03":
        return "ctrl_c"
    return None


def _read_unix_key() -> str | None:
    import select

    fd = sys.stdin.fileno()
    first = os.read(fd, 1)
    if first != b"\x1b":
        return parse_sequence(first)
    data = first
    for _ in range(3):
        ready, _, _ = select.select([fd], [], [], 0.03)
        if not ready:
            break
        data += os.read(fd, 1)
    return parse_sequence(data)


@contextmanager
def raw_mode(fd=None):
    """保持终端 raw 模式，减少每次按键的进出切换开销。"""
    if os.name == "nt" or not sys.stdin.isatty():
        yield
        return
    import termios
    import tty

    target = fd if fd is not None else sys.stdin.fileno()
    old = termios.tcgetattr(target)
    try:
        tty.setraw(target)
        yield
    finally:
        termios.tcsetattr(target, termios.TCSADRAIN, old)


def _read_windows_key() -> str | None:
    import msvcrt

    first = msvcrt.getwch()
    if first in ("\x00", "\xe0"):
        second = msvcrt.getwch()
        mapping = {
            "H": "up",
            "P": "down",
            "M": "right",
            "K": "left",
            "G": "home",
            "O": "end",
        }
        return mapping.get(second)
    if first in ("\r", "\n"):
        return "enter"
    if first == "\x1b":
        return "esc"
    if first in ("q", "Q"):
        return "quit"
    if first == "\x03":
        return "ctrl_c"
    return None


def read_key() -> str | None:
    """读取一个按键；非 TTY 环境返回 None 以避免阻塞。"""
    if not sys.stdin.isatty():
        return None
    if os.name == "nt":
        return _read_windows_key()
    return _read_unix_key()
