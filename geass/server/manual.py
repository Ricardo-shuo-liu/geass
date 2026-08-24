"""手动直控：把 PWA 的触屏/虚拟键鼠事件直接落到 InputBackend。

这一通道完全绕开 LLM Agent：手机把归一化坐标或按键事件发到
``/ws/control``，服务端立刻换算成真实像素并执行，用于打断 Agent 后的
直接接管，或用户全程手动操作。
"""
from __future__ import annotations

from typing import Any

from ..io.backend import InputBackend, InputError

MAX_TEXT_LENGTH = 2048
MAX_COMBO_LENGTH = 128


def _clamp(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, float(value)))


def _point(
    backend: InputBackend,
    payload: dict[str, Any],
    x_key: str = "x",
    y_key: str = "y",
) -> tuple[int, int]:
    width, height = backend.screen_size()
    x = _clamp(payload.get(x_key, 0.5))
    y = _clamp(payload.get(y_key, 0.5))
    return round(x * width), round(y * height)


def _button(value: Any) -> str:
    button = str(value or "left").strip().lower()
    if button not in {"left", "right", "middle"}:
        raise ValueError(f"无效按钮：{button}")
    return button


def execute_manual_input(
    backend: InputBackend, payload: dict[str, Any]
) -> dict[str, Any]:
    """执行单条手动输入事件，返回 ``{ok, message}`` 或 ``{ok, error}``。"""
    action = str(payload.get("action") or "").strip().lower()
    try:
        if action == "move":
            x, y = _point(backend, payload)
            backend.move(x, y, duration=0.0)
            return {"ok": True, "message": "move"}
        if action == "click":
            x, y = _point(backend, payload)
            backend.click(x, y, button=_button(payload.get("button")))
            return {"ok": True, "message": "click"}
        if action == "double_click":
            x, y = _point(backend, payload)
            backend.double_click(x, y)
            return {"ok": True, "message": "double_click"}
        if action == "right_click":
            x, y = _point(backend, payload)
            backend.right_click(x, y)
            return {"ok": True, "message": "right_click"}
        if action == "drag":
            x1, y1 = _point(backend, payload, "x1", "y1")
            x2, y2 = _point(backend, payload, "x2", "y2")
            backend.drag(x1, y1, x2, y2)
            return {"ok": True, "message": "drag"}
        if action == "scroll":
            dx = int(payload.get("dx") or 0)
            dy = int(payload.get("dy") or 0)
            backend.scroll(max(-50, min(50, dx)), max(-50, min(50, dy)))
            return {"ok": True, "message": "scroll"}
        if action == "key":
            combo = str(payload.get("combo") or "").strip()[:MAX_COMBO_LENGTH]
            if not combo:
                raise ValueError("key 需要非空 combo")
            backend.key_press(combo)
            return {"ok": True, "message": f"key {combo}"}
        if action == "type":
            text = str(payload.get("text") or "")[:MAX_TEXT_LENGTH]
            if not text:
                raise ValueError("type 需要非空 text")
            backend.type_text(text)
            return {"ok": True, "message": f"type {len(text)} chars"}
        return {"ok": False, "error": f"未知手动输入动作：{action}"}
    except (InputError, KeyError, TypeError, ValueError) as exc:
        return {"ok": False, "error": f"手动输入执行失败：{exc}"}
