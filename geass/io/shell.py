"""系统级辅助操作：打开新的终端窗口执行 shell 命令。"""

from __future__ import annotations

import os
import platform
import subprocess
import time

# 从 VS Code（snap 版）集成终端等环境继承来的变量，会让宿主 GTK 应用加载
# snap 的 GTK 模块，把 /snap/core20 库路径注入动态链接器搜索路径，导致
# gnome-terminal 出现 "__libc_pthread_init / GLIBC_PRIVATE" 符号错误崩溃。
_SNAP_POLLUTED_KEYS = {
    "GTK_PATH",
    "GTK_EXE_PREFIX",
    "GTK_IM_MODULE_FILE",
    "GTK2_MODULE_FILE",
    "GIO_MODULE_DIR",
    "GIO_LAUNCHED_DESKTOP_FILE",
    "GDK_PIXBUF_MODULE_FILE",
    "GDK_PIXBUF_MODULEDIR",
    "LOCPATH",
    "GSETTINGS_SCHEMA_DIR",
}


def terminal_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """构造启动终端窗口进程所需的干净环境。

    剔除 snap 注入的变量，并过滤 LD_LIBRARY_PATH 中的 /snap 与
    /var/lib/snapd 条目；其余环境原样保留（DISPLAY、DBus 等）。
    """
    clean = dict(env if env is not None else os.environ)
    for key in list(clean):
        if key.startswith("SNAP") or key in _SNAP_POLLUTED_KEYS:
            clean.pop(key, None)
    ld_path = clean.get("LD_LIBRARY_PATH")
    if ld_path:
        kept = [
            entry
            for entry in str(ld_path).split(":")
            if entry and "/snap/" not in entry and "/var/lib/snapd/" not in entry
        ]
        if kept:
            clean["LD_LIBRARY_PATH"] = ":".join(kept)
        else:
            clean.pop("LD_LIBRARY_PATH", None)
    return clean


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
        env=terminal_env(),
    )


def _open_linux(command: str) -> dict:
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return {
            "ok": False,
            "error": (
                "当前会话没有图形环境（DISPLAY/WAYLAND_DISPLAY 未设置），无法打开可见的终端窗口"
            ),
        }
    line = command.strip()
    shell_line = f"{line}; exec bash" if line else "exec bash"
    candidates = [
        lambda: ["x-terminal-emulator", "-e", "bash", "-c", shell_line],
        lambda: ["gnome-terminal", "--wait", "--", "bash", "-c", shell_line],
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
        except FileNotFoundError:
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
