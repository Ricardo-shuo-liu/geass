"""用默认浏览器打开页面、新建标签页或窗口。

浏览器任务的常见失败原因是模型去屏幕上找浏览器图标、手动点击，再猜测
地址栏位置。这里把它收口成确定性命令：Linux 用 ``xdg-open`` / 浏览器
自带参数，macOS 用 ``open``，Windows 用 ``start``。启动是异步的，调用
方拿到成功后仍需等待并截图验证页面是否加载。
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Any

from .shell import terminal_env


class BrowserError(RuntimeError):
    """打开浏览器失败。"""


_ACTIONS = ("open", "new_tab", "new_window")

# 用于 new_tab / new_window 的候选浏览器可执行文件，按常见程度排序。
_BROWSER_CANDIDATES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
    "brave-browser",
    "brave",
    "firefox",
    "vivaldi",
    "opera",
)


def _display_ready() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _detached(argv: list[str]) -> subprocess.Popen:
    try:
        return subprocess.Popen(
            argv,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=terminal_env(),
        )
    except FileNotFoundError as exc:
        raise BrowserError(f"未找到可执行程序：{argv[0]}") from exc
    except OSError as exc:
        raise BrowserError(f"启动浏览器失败（{argv[0]}）：{exc}") from exc


def _page_arg(url: str) -> str:
    return url.strip() if url and url.strip() else "about:blank"


def _result(action: str, url: str, argv: list[str]) -> dict[str, Any]:
    page = _page_arg(url)
    message = (
        f"已请求浏览器执行 {action}"
        + (f"：{page}" if url and url.strip() else "（新建空白页）")
        + "；启动是异步的，页面可能仍在加载，请 wait 1~3 秒后用 screenshot 验证"
    )
    return {
        "ok": True,
        "message": message,
        "action": action,
        "url": page,
        "command": " ".join(argv),
    }


def _installed_browsers() -> list[str]:
    found: list[str] = []
    for name in _BROWSER_CANDIDATES:
        if shutil.which(name):
            found.append(name)
    return found


def _open_linux(action: str, url: str) -> dict[str, Any]:
    if not _display_ready():
        raise BrowserError(
            "当前会话没有图形环境（DISPLAY/WAYLAND_DISPLAY 未设置），"
            "无法打开浏览器"
        )

    if action == "open":
        argv = ["xdg-open", _page_arg(url)]
        _detached(argv)
        return _result(action, url, argv)

    flag = "--new-tab" if action == "new_tab" else "--new-window"
    last_error = ""
    for browser in _installed_browsers():
        argv = [browser, flag, _page_arg(url)]
        try:
            _detached(argv)
        except BrowserError as exc:
            last_error = str(exc)
            continue
        return _result(action, url, argv)

    # 没有可识别的浏览器时退回 xdg-open；新窗口请求会退化为新标签/窗口。
    argv = ["xdg-open", _page_arg(url)]
    try:
        _detached(argv)
        return _result(action, url, argv)
    except BrowserError as exc:
        last_error = str(exc)
    raise BrowserError(f"无法执行新建页操作：{last_error or '未找到浏览器'}")


def _open_macos(action: str, url: str) -> dict[str, Any]:
    page = _page_arg(url)
    argv = ["open", "-u", page]
    if action == "new_window":
        argv = ["open", "-n", "-u", page]
    _detached(argv)
    return _result(action, url, argv)


def _open_windows(action: str, url: str) -> dict[str, Any]:
    page = _page_arg(url)
    argv = ["cmd", "/c", "start", "", page]
    _detached(argv)
    return _result(action, url, argv)


def open_page(action: str = "open", url: str = "") -> dict[str, Any]:
    """在默认浏览器中打开页面 / 新建标签页 / 新建窗口。"""
    action = str(action or "open").strip().lower()
    if action not in _ACTIONS:
        raise BrowserError(f"未知的浏览器动作：{action}（可选 {_ACTIONS}）")
    url = str(url or "").strip()

    system = platform.system()
    try:
        if system == "Linux":
            return _open_linux(action, url)
        if system == "Darwin":
            return _open_macos(action, url)
        if system == "Windows":
            return _open_windows(action, url)
    except BrowserError:
        raise
    except Exception as exc:
        raise BrowserError(f"打开浏览器失败：{exc}") from exc
    return {
        "ok": False,
        "error": f"暂不支持该系统：{system}",
    }
