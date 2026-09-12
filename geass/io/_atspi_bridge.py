"""AT-SPI 桥接脚本，由系统 Python 独立运行。

conda 环境通常无法加载发行版为系统 Python 编译的 gi/PyGObject C
扩展，但这个脚本只依赖标准库和系统 Python 自带的 pyatspi。父进程把
查询参数作为单个 JSON 参数传入，结果以 JSON 输出，stdout 只允许出现
这一行结果，方便父进程解析。

本文件不能 import Geass 包，必须保持对系统 Python 的完全独立性。
"""

from __future__ import annotations

import json
import sys
import time


def main() -> None:
    if len(sys.argv) != 2:
        print(json.dumps({"ok": False, "error": "缺少查询参数"}))
        return
    try:
        args = json.loads(sys.argv[1])
    except (TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": f"参数不是有效 JSON：{exc}"}))
        return
    if not isinstance(args, dict):
        print(json.dumps({"ok": False, "error": "查询参数必须是对象"}))
        return

    try:
        import pyatspi
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": (
                        "系统 Python 也无法导入 pyatspi："
                        f"{exc}（Ubuntu/Debian: sudo apt install "
                        "python3-pyatspi；Fedora: sudo dnf install "
                        "python3-pyatspi）"
                    ),
                }
            )
        )
        return

    if args.get("probe"):
        print(json.dumps({"ok": True}))
        return

    if args.get("op") == "windows":
        limit = max(1, min(int(args.get("limit") or 50), 100))
        timeout = max(0.1, float(args.get("timeout") or 5.0))
        try:
            desktop = pyatspi.Registry.getDesktop(0)
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": f"无法连接 AT-SPI 无障碍总线：{exc}",
                    }
                )
            )
            return

        windows: list[dict[str, object]] = []
        seen: set[int] = set()
        deadline = time.monotonic() + timeout
        desktop_coords = getattr(pyatspi, "DESKTOP_COORDS", 0)
        window_roles = {"frame", "window", "dialog"}
        active_state = getattr(pyatspi, "STATE_ACTIVE", None)
        visible_state = getattr(pyatspi, "STATE_VISIBLE", None)

        def walk_windows(node: object) -> None:
            if len(windows) >= limit or time.monotonic() >= deadline:
                return
            marker = id(node)
            if marker in seen:
                return
            seen.add(marker)

            try:
                role_name = str(node.getRoleName() or "").casefold()  # type: ignore[attr-defined]
            except Exception:
                role_name = ""

            if role_name in window_roles:
                name = str(getattr(node, "name", "") or "")
                active = False
                visible = False
                x = y = w = h = 0
                try:
                    state = node.getState()  # type: ignore[attr-defined]
                    active = bool(active_state and state.contains(active_state))
                    visible = bool(visible_state and state.contains(visible_state))
                    component = node.queryComponent()  # type: ignore[attr-defined]
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
                child_count = int(node.childCount)  # type: ignore[attr-defined]
            except Exception:
                return
            for index in range(child_count):
                if len(windows) >= limit or time.monotonic() >= deadline:
                    return
                try:
                    child = node.getChildAtIndex(index)  # type: ignore[attr-defined]
                except Exception:
                    continue
                if child is not None:
                    walk_windows(child)

        try:
            walk_windows(desktop)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": f"遍历窗口失败：{exc}"}))
            return
        print(json.dumps({"ok": True, "windows": windows[:limit]}, ensure_ascii=False))
        return

    if args.get("op") == "sensitive":
        limit = max(1, min(int(args.get("limit") or 10), 50))
        timeout = max(0.1, float(args.get("timeout") or 3.0))
        try:
            desktop = pyatspi.Registry.getDesktop(0)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": f"无法连接 AT-SPI 无障碍总线：{exc}"}))
            return

        fields: list[dict[str, object]] = []
        seen_sensitive: set[int] = set()
        deadline = time.monotonic() + timeout
        desktop_coords = getattr(pyatspi, "DESKTOP_COORDS", 0)

        def is_sensitive(node: object, role_name: str) -> bool:
            if "password" in role_name.casefold():
                return True
            try:
                attributes = node.getAttributes() or []  # type: ignore[attr-defined]
            except Exception:
                return False
            for item in attributes:
                text = str(item).casefold()
                if text.startswith("protected:") and text.split(":", 1)[1].strip() in (
                    "true",
                    "1",
                    "yes",
                ):
                    return True
            return False

        def walk_sensitive(node: object) -> None:
            if len(fields) >= limit or time.monotonic() >= deadline:
                return
            marker = id(node)
            if marker in seen_sensitive:
                return
            seen_sensitive.add(marker)
            try:
                role_name = str(node.getRoleName() or "")  # type: ignore[attr-defined]
            except Exception:
                role_name = ""
            if role_name and is_sensitive(node, role_name):
                try:
                    component = node.queryComponent()  # type: ignore[attr-defined]
                    extents = component.getExtents(desktop_coords)
                    x = int(getattr(extents, "x", 0))
                    y = int(getattr(extents, "y", 0))
                    w = int(getattr(extents, "width", 0))
                    h = int(getattr(extents, "height", 0))
                    if w > 0 and h > 0:
                        fields.append(
                            {
                                "name": str(getattr(node, "name", "") or ""),
                                "role": role_name,
                                "x": x,
                                "y": y,
                                "w": w,
                                "h": h,
                            }
                        )
                except Exception:
                    pass
            try:
                child_count = int(node.childCount)  # type: ignore[attr-defined]
            except Exception:
                return
            for index in range(child_count):
                if len(fields) >= limit or time.monotonic() >= deadline:
                    return
                try:
                    child = node.getChildAtIndex(index)  # type: ignore[attr-defined]
                except Exception:
                    continue
                if child is not None:
                    walk_sensitive(child)

        walk_sensitive(desktop)
        print(json.dumps({"ok": True, "fields": fields[:limit]}, ensure_ascii=False))
        return

    query = str(args.get("name") or "").strip()
    role = str(args.get("role") or "").strip()
    limit = max(1, min(int(args.get("limit") or 20), 100))
    timeout = max(0.1, float(args.get("timeout") or 5.0))
    if not query:
        print(json.dumps({"ok": False, "error": "控件名称不能为空"}))
        return

    try:
        desktop = pyatspi.Registry.getDesktop(0)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"无法连接 AT-SPI 无障碍总线：{exc}",
                }
            )
        )
        return

    matches: list[dict[str, object]] = []
    seen_nodes: set[int] = set()
    deadline = time.monotonic() + timeout
    role_needle = role.casefold()
    name_needle = query.casefold()
    desktop_coords = getattr(pyatspi, "DESKTOP_COORDS", 0)

    def walk(node: object) -> None:
        if len(matches) >= limit or time.monotonic() >= deadline:
            return
        marker = id(node)
        if marker in seen_nodes:
            return
        seen_nodes.add(marker)

        try:
            node_name = str(getattr(node, "name", "") or "")
            node_role = str(node.getRoleName() or "")  # type: ignore[attr-defined]
        except Exception:
            node_name = ""
            node_role = ""

        if node_name and name_needle in node_name.casefold():
            if not role_needle or role_needle in node_role.casefold():
                try:
                    component = node.queryComponent()  # type: ignore[attr-defined]
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
            child_count = int(node.childCount)  # type: ignore[attr-defined]
        except Exception:
            return
        for index in range(child_count):
            if len(matches) >= limit or time.monotonic() >= deadline:
                return
            try:
                child = node.getChildAtIndex(index)  # type: ignore[attr-defined]
            except Exception:
                continue
            if child is not None:
                walk(child)

    try:
        walk(desktop)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"遍历无障碍树失败：{exc}"}))
        return

    print(json.dumps({"ok": True, "matches": matches[:limit]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
