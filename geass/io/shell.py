"""系统级辅助操作：打开新的终端窗口执行 shell 命令。"""
from __future__ import annotations

import os
import platform
import subprocess
import time


def open_terminal(command: str = "") -> dict:
    system = platform.system()
    try:
        if system == "Linux":
            return _open_linux(command)
        if system == "Darwin":
            return _open_macos(command)
        if system == "Windows":
            return _open_windows(command)
        return {"ok": False, "error": f"暂不支持该系统：{system}"}
    except Exception as exc:
        return {"ok": False, "error": f"打开终端失败：{exc}"}


def _detached(argv: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        argv,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _open_linux(command: str) -> dict:
    if not os.environ.get("DISPLAY"):
        return {
            "ok": False,
            "error": "当前会话没有图形环境（DISPLAY 未设置），无法打开可见的终端窗口",
        }
    line = command.strip()
    shell_line = f"{line}; exec bash" if line else "exec bash"
    candidates = [
        lambda: ["gnome-terminal", "--", "bash", "-c", shell_line],
        lambda: ["x-terminal-emulator", "-e", "bash", "-c", shell_line],
        lambda: ["konsole", "-e", "bash", "-c", shell_line],
        lambda: ["xfce4-terminal", "-x", "bash", "-c", shell_line],
        lambda: ["mate-terminal", "--", "bash", "-c", shell_line],
        lambda: ["xterm", "-e", "bash", "-c", shell_line],
    ]
    last_error = ""
    for build in candidates:
        argv = build()
        try:
            process = _detached(argv)
        except FileNotFoundError as exc:
            last_error = f"{argv[0]}（未安装）"
            continue
        except OSError as exc:
            last_error = f"{argv[0]} 启动失败：{exc}"
            continue
        time.sleep(0.4)
        code = process.poll()
        if code is None or code == 0:
            return {
                "ok": True,
                "message": f"已在新终端窗口执行：{command or '（仅打开空白终端）'}",
            }
        last_error = f"{argv[0]} 启动后立即退出（退出码 {code}）"
    return {"ok": False, "error": f"无法打开可见的终端窗口：{last_error}"}


def _open_macos(command: str) -> dict:
    line = command.strip().replace('"', '\\"')
    _detached(
        [
            "osascript",
            "-e",
            f'tell application "Terminal" to do script "{line}"',
        ]
    )
    return {"ok": True, "message": f"已在新的 Terminal 窗口执行：{command or '（仅打开空白终端）'}"}


def _open_windows(command: str) -> dict:
    line = command.strip()
    _detached(["cmd", "/c", "start", "cmd", "/k", line] if line else ["cmd", "/c", "start", "cmd"])
    return {"ok": True, "message": f"已在新的 cmd 窗口执行：{command or '（仅打开空白终端）'}"}
