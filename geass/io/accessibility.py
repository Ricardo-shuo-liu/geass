"""通过 Linux AT-SPI 无障碍树查找可交互控件。

很多桌面应用会把控件名称/角色通过 AT-SPI 总线暴露出来，附带屏幕上的
位置和大小。这里让 Agent 用「语义描述」找控件，返回其屏幕包围盒，
而不是让模型凭截图猜坐标。

依赖可选的 ``pyatspi``（以及运行中的 AT-SPI 总线）；缺失时抛出
``AccessibilityError``，调用方应把它当作普通工具错误回填给模型。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import Any


class AccessibilityError(RuntimeError):
    """无障碍树不可用或查询失败。"""

    def __init__(self, message: str, *, bridge_fallback: bool = False) -> None:
        super().__init__(message)
        # bridge_fallback=True 表示 pyatspi 本身存在，但当前 Python
        # 环境缺少兼容的 gi/PyGObject，应改用系统 Python 桥接进程查询。
        self.bridge_fallback = bridge_fallback


_SYSTEM_PYTHON_PATHS = (
    "/usr/lib/python3/dist-packages",
    "/usr/local/lib/python3/dist-packages",
)
_SYSTEM_PYTHON_CANDIDATES = (
    "/usr/bin/python3",
    "/usr/local/bin/python3",
    "/usr/bin/python",
)
_BRIDGE_SCRIPT = os.path.join(os.path.dirname(__file__), "_atspi_bridge.py")
_WINDOW_ROLES = {"frame", "window", "dialog"}


def _load_pyatspi() -> Any:
    """加载 pyatspi；conda 环境看不到发行版包时回退到系统 Python 路径。

    pyatspi 没有发布到 PyPI/conda-forge，Ubuntu/Debian 通过
    ``sudo apt install python3-pyatspi`` 安装到系统 Python 的
    dist-packages；它是纯 Python 包，可以直接从那里 import。
    """
    try:
        import pyatspi

        return pyatspi
    except ImportError as exc:
        if getattr(exc, "name", None) != "pyatspi":
            raise AccessibilityError(f"pyatspi 依赖缺失：{exc}", bridge_fallback=True) from exc

    added_paths: list[str] = []
    for path in _SYSTEM_PYTHON_PATHS:
        if os.path.isdir(path) and path not in sys.path:
            sys.path.append(path)
            added_paths.append(path)
    try:
        import pyatspi

        return pyatspi
    except ImportError as exc:
        if getattr(exc, "name", None) != "pyatspi":
            raise AccessibilityError(
                "找到系统 pyatspi，但 conda Python 缺少兼容的 gi/PyGObject"
                f"（{exc}）。将尝试用系统 Python 桥接查询。",
                bridge_fallback=True,
            ) from exc
        raise AccessibilityError(
            "未找到 pyatspi：请先安装发行版包"
            "（Ubuntu/Debian: sudo apt install python3-pyatspi；"
            "Fedora: sudo dnf install python3-pyatspi）"
        ) from exc
    finally:
        for path in added_paths:
            if path in sys.path:
                sys.path.remove(path)


def is_available() -> bool:
    """供环境自检使用：pyatspi 是否可以被导入。"""
    try:
        _load_pyatspi()
    except AccessibilityError as exc:
        if not exc.bridge_fallback:
            return False
        try:
            _run_bridge({"probe": True}, timeout=5.0)
        except AccessibilityError:
            return False
    return True


def _system_python() -> str:
    for candidate in _SYSTEM_PYTHON_CANDIDATES:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise AccessibilityError("找不到系统 Python，无法运行 AT-SPI 桥接；请确认系统已安装 python3")


def _run_bridge(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    """让系统 Python 运行独立桥接脚本，绕开 conda Python 的 ABI 差异。"""
    try:
        python = _system_python()
    except AccessibilityError as exc:
        raise AccessibilityError(str(exc), bridge_fallback=True) from exc

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    try:
        completed = subprocess.run(
            [python, _BRIDGE_SCRIPT, json.dumps(payload, ensure_ascii=False)],
            capture_output=True,
            text=True,
            timeout=max(0.5, float(timeout) + 2.0),
            env=env,
        )
    except FileNotFoundError as exc:
        raise AccessibilityError(f"系统 Python 无法启动：{exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise AccessibilityError(f"AT-SPI 桥接查询超时：{exc}") from exc
    except OSError as exc:
        raise AccessibilityError(f"AT-SPI 桥接启动失败：{exc}") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise AccessibilityError(
            f"AT-SPI 桥接退出异常：{detail or f'退出码 {completed.returncode}'}"
        )
    try:
        result = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise AccessibilityError(f"AT-SPI 桥接返回无效数据：{exc}") from exc
    if not isinstance(result, dict) or not result.get("ok"):
        reason = result.get("error") if isinstance(result, dict) else "未知错误"
        raise AccessibilityError(f"AT-SPI 桥接查询失败：{reason}")
    return result


def _find_via_bridge(
    query: str,
    role: str,
    limit: int,
    timeout: float,
) -> list[dict[str, Any]]:
    result = _run_bridge(
        {
            "name": query,
            "role": role,
            "limit": limit,
            "timeout": timeout,
        },
        timeout,
    )
    matches = result.get("matches")
    if not isinstance(matches, list):
        return []
    return [item for item in matches if isinstance(item, dict) and "name" in item]


def _list_windows_via_bridge(limit: int, timeout: float) -> list[dict[str, Any]]:
    result = _run_bridge(
        {
            "op": "windows",
            "limit": limit,
            "timeout": timeout,
        },
        timeout,
    )
    windows = result.get("windows")
    if not isinstance(windows, list):
        return []
    return [item for item in windows if isinstance(item, dict) and "name" in item]


def find_elements(
    name: str = "",
    role: str = "",
    limit: int = 20,
    timeout: float = 5.0,
) -> list[dict[str, Any]]:
    """在无障碍树中查找控件，返回 ``{name, role, x, y, w, h}``（屏幕像素）。"""
    query = str(name or "").strip()
    if not query:
        raise AccessibilityError("控件名称不能为空")
    try:
        pyatspi = _load_pyatspi()
    except AccessibilityError as exc:
        if exc.bridge_fallback:
            return _find_via_bridge(
                query=query,
                role=str(role or "").strip(),
                limit=max(1, min(int(limit), 100)),
                timeout=float(timeout),
            )
        raise

    try:
        desktop = pyatspi.Registry.getDesktop(0)
    except Exception as exc:
        raise AccessibilityError(f"无法连接 AT-SPI 无障碍总线：{exc}") from exc

    matches: list[dict[str, Any]] = []
    seen: set[int] = set()
    deadline = time.monotonic() + max(0.1, float(timeout))
    role_needle = str(role or "").strip().casefold()
    name_needle = query.casefold()
    desktop_coords = getattr(pyatspi, "DESKTOP_COORDS", 0)

    def walk(node: Any) -> None:
        if len(matches) >= limit or time.monotonic() >= deadline:
            return
        marker = id(node)
        if marker in seen:
            return
        seen.add(marker)

        try:
            node_name = str(getattr(node, "name", "") or "")
            node_role = str(node.getRoleName() or "")
        except Exception:
            node_name = ""
            node_role = ""

        if node_name and name_needle in node_name.casefold():
            if not role_needle or role_needle in node_role.casefold():
                try:
                    component = node.queryComponent()
                    extents = component.getExtents(desktop_coords)
                    x = int(getattr(extents, "x", 0))
                    y = int(getattr(extents, "y", 0))
                    w = int(getattr(extents, "width", 0))
                    h = int(getattr(extents, "height", 0))
                    if w > 0 and h > 0:
                        matches.append(
                            {
                                "name": node_name,
                                "role": node_role,
                                "x": x,
                                "y": y,
                                "w": w,
                                "h": h,
                            }
                        )
                except Exception:
                    pass

        try:
            child_count = int(node.childCount)
        except Exception:
            return
        for index in range(child_count):
            if len(matches) >= limit or time.monotonic() >= deadline:
                return
            try:
                child = node.getChildAtIndex(index)
            except Exception:
                continue
            if child is not None:
                walk(child)

    walk(desktop)
    return matches[:limit]


def list_windows(limit: int = 50, timeout: float = 5.0) -> list[dict[str, Any]]:
    """返回可见顶层窗口信息：``{name, role, x, y, w, h, active, visible}``。

    供 Agent 在动作后验证"新窗口/新标签页是否真的打开了"；视觉之外的第二条
    信息通道。依赖 AT-SPI（缺失时经系统 Python 桥接，不可用则抛错）。
    """
    try:
        pyatspi = _load_pyatspi()
    except AccessibilityError as exc:
        if exc.bridge_fallback:
            return _list_windows_via_bridge(max(1, min(int(limit), 100)), float(timeout))
        raise

    try:
        desktop = pyatspi.Registry.getDesktop(0)
    except Exception as exc:
        raise AccessibilityError(f"无法连接 AT-SPI 无障碍总线：{exc}") from exc

    windows: list[dict[str, Any]] = []
    seen: set[int] = set()
    deadline = time.monotonic() + max(0.1, float(timeout))
    desktop_coords = getattr(pyatspi, "DESKTOP_COORDS", 0)
    active_state = getattr(pyatspi, "STATE_ACTIVE", None)
    visible_state = getattr(pyatspi, "STATE_VISIBLE", None)

    def walk(node: Any) -> None:
        if len(windows) >= limit or time.monotonic() >= deadline:
            return
        marker = id(node)
        if marker in seen:
            return
        seen.add(marker)

        try:
            role_name = str(node.getRoleName() or "").casefold()
        except Exception:
            role_name = ""

        if role_name in _WINDOW_ROLES:
            name = str(getattr(node, "name", "") or "")
            active = False
            visible = False
            x = y = w = h = 0
            try:
                state = node.getState()
                active = bool(active_state and state.contains(active_state))
                visible = bool(visible_state and state.contains(visible_state))
                component = node.queryComponent()
                extents = component.getExtents(desktop_coords)
                x = int(getattr(extents, "x", 0))
                y = int(getattr(extents, "y", 0))
                w = int(getattr(extents, "width", 0))
                h = int(getattr(extents, "height", 0))
            except Exception:
                pass
            if name or active or visible or (w > 0 and h > 0):
                windows.append(
                    {
                        "name": name,
                        "role": role_name,
                        "x": x,
                        "y": y,
                        "w": w,
                        "h": h,
                        "active": active,
                        "visible": visible,
                    }
                )
                if len(windows) >= limit:
                    return

        try:
            child_count = int(node.childCount)
        except Exception:
            return
        for index in range(child_count):
            if len(windows) >= limit or time.monotonic() >= deadline:
                return
            try:
                child = node.getChildAtIndex(index)
            except Exception:
                continue
            if child is not None:
                walk(child)

    walk(desktop)
    return windows[:limit]
