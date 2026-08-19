"""Agent 循环：截图 -> OpenAI 视觉模型 -> 工具调用 -> 本地执行 -> 回填结果。"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any, Awaitable, Callable

from openai import AsyncOpenAI

from .config import AgentConfig
from .io.backend import InputBackend, InputError
from .screen import ScreenCapture

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是 Geass，一台电脑桌面的操作智能体。用户通过手机下达任务，"
    "你通过观察屏幕截图并调用工具完成操作。\n"
    "规则：\n"
    "1. 坐标统一使用归一化值：x、y 是 0~1 之间的浮点数，(0,0) 是截图左上角，(1,1) 是右下角。\n"
    "2. 每次工具执行后都会附上新的屏幕截图，请先观察截图再决定下一步。\n"
    "3. 一次响应可以调用一个或多个工具；不确定界面状态时先用 screenshot 或 wait。\n"
    "4. 只执行用户任务范围内的操作，不做无关动作。\n"
    "5. 任务完成或无法继续时，必须调用 finish 并说明结果。"
)

_NUMBER = {"type": "number", "minimum": 0.0, "maximum": 1.0}


def _point(required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"x": _NUMBER, "y": _NUMBER},
        "required": required,
        "additionalProperties": False,
    }


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "move",
        "description": "把鼠标移动到屏幕指定位置。x、y 为 0~1 的归一化坐标。",
        "parameters": _point(["x", "y"]),
    },
    {
        "type": "function",
        "name": "click",
        "description": "在指定位置单击。button 可选 left/right/middle，默认 left。",
        "parameters": {
            "type": "object",
            "properties": {
                "x": _NUMBER,
                "y": _NUMBER,
                "button": {"type": "string", "enum": ["left", "right", "middle"]},
            },
            "required": ["x", "y"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "double_click",
        "description": "在指定位置双击左键。",
        "parameters": _point(["x", "y"]),
    },
    {
        "type": "function",
        "name": "right_click",
        "description": "在指定位置单击右键。",
        "parameters": _point(["x", "y"]),
    },
    {
        "type": "function",
        "name": "scroll",
        "description": "滚动鼠标滚轮。dy>0 向上滚、dy<0 向下滚；dx 为水平滚动（支持时生效）。",
        "parameters": {
            "type": "object",
            "properties": {"dx": {"type": "integer"}, "dy": {"type": "integer"}},
            "required": ["dx", "dy"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "drag",
        "description": "从 (x1,y1) 按住左键拖动到 (x2,y2)。坐标均为归一化值。",
        "parameters": {
            "type": "object",
            "properties": {
                "x1": _NUMBER,
                "y1": _NUMBER,
                "x2": _NUMBER,
                "y2": _NUMBER,
            },
            "required": ["x1", "y1", "x2", "y2"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "type_text",
        "description": "在当前焦点处输入文本（模拟键盘逐字输入，适合 ASCII；中文受输入法限制）。",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "key_press",
        "description": "按单个键或组合键，例如 \"enter\"、\"esc\"、\"ctrl+c\"、\"alt+tab\"。",
        "parameters": {
            "type": "object",
            "properties": {"combo": {"type": "string"}},
            "required": ["combo"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "wait",
        "description": "等待指定秒数（0.1~10），用于等待界面加载。",
        "parameters": {
            "type": "object",
            "properties": {
                "seconds": {"type": "number", "minimum": 0.1, "maximum": 10.0}
            },
            "required": ["seconds"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "screenshot",
        "description": "获取最新屏幕截图，帮助确认当前界面状态。",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "finish",
        "description": "任务完成或无法继续时调用，summary 简要说明结果。",
        "parameters": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        },
    },
]

StatusCallback = Callable[[dict[str, Any]], Awaitable[None]]


class AgentError(RuntimeError):
    """Agent 运行前的配置错误（如缺少 API key）。"""


class Agent:
    def __init__(
        self,
        client: AsyncOpenAI | None,
        backend: InputBackend,
        capture: ScreenCapture,
        config: AgentConfig,
        status_cb: StatusCallback | None = None,
    ) -> None:
        self.client = client
        self.backend = backend
        self.capture = capture
        self.config = config
        self.status_cb = status_cb

    async def _emit(
        self, state: str, step: int = 0, tool: str | None = None, message: str = ""
    ) -> None:
        if self.status_cb is not None:
            await self.status_cb(
                {
                    "type": "agent_status",
                    "state": state,
                    "step": step,
                    "tool": tool,
                    "message": message,
                }
            )

    def norm_to_px(self, x: float, y: float) -> tuple[int, int]:
        width, height = self.backend.screen_size()
        cx = min(1.0, max(0.0, float(x)))
        cy = min(1.0, max(0.0, float(y)))
        return round(cx * width), round(cy * height)

    async def _execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "move":
                x, y = self.norm_to_px(args["x"], args["y"])
                self.backend.move(x, y)
                return {"ok": True, "message": f"已移动鼠标到 ({x},{y})"}
            if name == "click":
                x, y = self.norm_to_px(args["x"], args["y"])
                button = str(args.get("button") or "left")
                self.backend.click(x, y, button=button)
                return {"ok": True, "message": f"已在 ({x},{y}) 单击 {button}"}
            if name == "double_click":
                x, y = self.norm_to_px(args["x"], args["y"])
                self.backend.double_click(x, y)
                return {"ok": True, "message": f"已在 ({x},{y}) 双击"}
            if name == "right_click":
                x, y = self.norm_to_px(args["x"], args["y"])
                self.backend.right_click(x, y)
                return {"ok": True, "message": f"已在 ({x},{y}) 右键"}
            if name == "scroll":
                dx, dy = int(args.get("dx") or 0), int(args.get("dy") or 0)
                self.backend.scroll(dx, dy)
                return {"ok": True, "message": f"已滚动 dx={dx} dy={dy}"}
            if name == "drag":
                x1, y1 = self.norm_to_px(args["x1"], args["y1"])
                x2, y2 = self.norm_to_px(args["x2"], args["y2"])
                self.backend.drag(x1, y1, x2, y2)
                return {"ok": True, "message": f"已从 ({x1},{y1}) 拖到 ({x2},{y2})"}
            if name == "type_text":
                text = str(args["text"])
                self.backend.type_text(text)
                return {"ok": True, "message": f"已输入文本（{len(text)} 字符）"}
            if name == "key_press":
                combo = str(args["combo"])
                self.backend.key_press(combo)
                return {"ok": True, "message": f"已按键 {combo}"}
            if name == "wait":
                seconds = min(10.0, max(0.0, float(args.get("seconds", 0.5))))
                await asyncio.sleep(seconds)
                return {"ok": True, "message": f"已等待 {seconds:.1f} 秒"}
            if name == "screenshot":
                return {"ok": True, "message": "已获取最新截图（见下一条消息）"}
            return {"ok": False, "error": f"未知工具：{name}"}
        except (InputError, KeyError, TypeError, ValueError) as exc:
            return {"ok": False, "error": f"{name} 执行失败：{exc}"}

    async def run(
        self, command: str, cancel: asyncio.Event | None = None
    ) -> dict[str, Any]:
        if self.client is None:
            raise AgentError(
                "未配置 API Key（GEASS_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY），"
                "无法调用模型接口"
            )

        cancel = cancel or asyncio.Event()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": command},
        ]
        try:
            first_frame = self.capture.capture_jpeg(self.config.image_max_edge)
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "当前屏幕状态如下："},
                        self._image_content(first_frame),
                    ],
                }
            )
        except Exception:
            logger.exception("初始截图失败")
            raise AgentError("无法抓取屏幕，Agent 无法启动")

        for step in range(1, self.config.max_steps + 1):
            if cancel.is_set():
                return {"state": "cancelled", "message": "任务已被用户中断"}

            await self._emit("thinking", step=step, message="正在观察屏幕并规划下一步…")
            try:
                response = await self._create_response(messages)
            except Exception as exc:
                logger.exception("模型调用失败")
                return {"state": "error", "message": f"模型调用失败：{exc}"}

            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None) or []
            if not tool_calls:
                text = getattr(message, "content", "") or "任务结束（模型未调用工具）"
                await self._emit("done", step=step, message=text)
                return {"state": "done", "message": text}

            messages.append(
                {
                    "role": "assistant",
                    "content": getattr(message, "content", "") or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in tool_calls
                    ],
                }
            )

            for call in tool_calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                if name == "finish":
                    summary = str(args.get("summary") or "") or "任务完成"
                    await self._emit("done", step=step, tool="finish", message=summary)
                    return {"state": "done", "message": summary}

                await self._emit("acting", step=step, tool=name, message=f"执行工具 {name}…")
                result = await self._execute(name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
                await self._emit(
                    "acted",
                    step=step,
                    tool=name,
                    message=result.get("message") or result.get("error", ""),
                )
                if cancel.is_set():
                    return {"state": "cancelled", "message": "任务已被用户中断"}

            try:
                frame = self.capture.capture_jpeg(self.config.image_max_edge)
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "工具执行后的最新屏幕截图："},
                            self._image_content(frame),
                        ],
                    }
                )
            except Exception:
                logger.warning("工具执行后截图失败")
                messages.append(
                    {
                        "role": "user",
                        "content": "（本次无法获取截图，请基于已有信息继续）",
                    }
                )
            messages.append(
                {
                    "role": "user",
                    "content": "请根据最新截图决定下一步操作；若任务已完成，调用 finish 总结结果。",
                }
            )

        return {
            "state": "limit",
            "message": f"已达到 {self.config.max_steps} 步上限，任务终止",
        }

    async def _create_response(self, messages: list[dict[str, Any]]):
        return await self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            tools=TOOLS,
        )

    @staticmethod
    def _image_content(jpeg: bytes) -> dict[str, Any]:
        encoded = base64.b64encode(jpeg).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
        }
