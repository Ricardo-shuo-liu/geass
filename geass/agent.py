"""Agent 循环：截图 -> OpenAI 视觉模型 -> 工具调用 -> 本地执行 -> 回填结果。"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import platform
from typing import Any, Awaitable, Callable

from openai import AsyncOpenAI

from .asyncutil import run_in_thread
from .config import AgentConfig, SecurityConfig
from .io.backend import InputBackend, InputError
from .io.shell import open_terminal
from .io.terminal import TerminalError, TerminalManager
from .safety import evaluate_command
from .screen import ScreenCapture
from .skills import Skill, catalog_text, find_skill

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是 Geass，一台电脑桌面的操作智能体。用户通过手机下达任务，"
    "你通过观察屏幕截图并调用工具完成操作。\n"
    "规则：\n"
    "1. 坐标统一使用归一化值：x、y 是 0~1 之间的浮点数，(0,0) 是截图左上角，(1,1) 是右下角。\n"
    "2. 每次工具执行后都会附上新的屏幕截图，请先观察截图再决定下一步。\n"
    "3. 一次响应可以调用一个或多个工具；不确定界面状态时先用 screenshot 或 wait。\n"
    "4. 只执行用户任务范围内的操作，不做无关动作。\n"
    "5. 当用户要求打开终端执行 shell 命令时，直接调用 open_terminal 工具，"
    "不要尝试手动模拟打开终端的快捷键。\n"
    "6. 如果用户任务匹配某个 SKILL 的描述，先调用 read_skill 获取该 SKILL"
    "的完整说明，再严格按说明执行；不要凭空编造不存在的技能。\n"
    "7. open_terminal 中的高危 shell 命令会先由用户审核；若审核被拒绝或超时，"
    "不要重复提交同一命令，换用其他方式，或调用 finish 说明无法继续。\n"
    "8. 任务完成或无法继续时，必须调用 finish 并说明结果。"
)


def _environment_hint() -> str:
    system = platform.system()
    if system == "Linux":
        return (
            "当前被控电脑是 Linux 桌面（通常为 Ubuntu/GNOME/X11）。"
            "打开终端使用组合键 ctrl+alt+t；打开应用启动器用 super（win）键。"
        )
    if system == "Windows":
        return (
            "当前被控电脑是 Windows。打开终端：按 win 键输入 cmd 后回车，"
            "或按 ctrl+r 输入 cmd 回车。"
        )
    if system == "Darwin":
        return (
            "当前被控电脑是 macOS。打开终端：按 cmd+space 呼出 Spotlight，"
            "输入 Terminal 后回车。"
        )
    return f"当前被控电脑系统：{system}。"


ENVIRONMENT_HINT = _environment_hint()

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
        "name": "open_terminal",
        "description": (
            "打开一个新的可见终端窗口，并可一键执行一条 shell 命令并等待其输出。"
            "返回 session_id 和捕获到的 output；command 留空则只打开空白终端，"
            "终端会保持打开，可用 terminal_read 监控输出。"
        ),
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "terminal_type",
        "description": (
            "向指定终端会话流式输入文本（模拟人类逐字打字）。"
            "session_id 留空时使用最近的会话；interval 是每字符间隔秒数，"
            "press_enter=true 表示输入后回车。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "text": {"type": "string"},
                "interval": {"type": "number", "minimum": 0.0, "maximum": 0.5},
                "press_enter": {"type": "boolean"},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "terminal_read",
        "description": (
            "读取指定终端会话自上次读取以来的新输出；session_id 留空时读取"
            "最近的会话。用于监控命令执行结果。"
        ),
        "parameters": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "terminal_close",
        "description": "关闭指定终端会话；session_id 留空时关闭最近的会话。",
        "parameters": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "list_skills",
        "description": "列出当前已加载的 SKILL 名称与描述。",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "read_skill",
        "description": (
            "读取指定 SKILL 的完整说明（渐进披露）。先根据系统提示中的清单"
            "或 list_skills 选择技能，再调用本工具获取正文与附带文件。"
        ),
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
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

TEXT_ONLY_TOOLS = {
    "type_text",
    "key_press",
    "open_terminal",
    "terminal_type",
    "terminal_read",
    "terminal_close",
    "list_skills",
    "read_skill",
    "wait",
    "finish",
}

StatusCallback = Callable[[dict[str, Any]], Awaitable[None]]
FallbackCallback = Callable[[], None]


def _is_vision_rejection(exc: Exception) -> bool:
    """识别"模型不支持图像输入"的 400 响应（如部分 DeepSeek 模型）。"""
    return type(exc).__name__ == "BadRequestError" and "image_url" in str(exc)


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
        vision_fallback_cb: FallbackCallback | None = None,
        skills: list[Skill] | None = None,
        terminal: TerminalManager | None = None,
        ocr: Any = None,
        security: SecurityConfig | None = None,
        approval_gateway: Any = None,
    ) -> None:
        self.client = client
        self.backend = backend
        self.capture = capture
        self.config = config
        self.status_cb = status_cb
        self.vision_fallback_cb = vision_fallback_cb
        self.vision = config.vision
        self.skills = list(skills or [])
        self.terminal = terminal
        self.ocr = ocr
        self.ocr_ready = False
        self.ocr_checked = False
        self.security = security
        self.approval_gateway = approval_gateway

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
            if name == "open_terminal":
                command = str(args.get("command") or "")
                if command.strip() and self.security is not None:
                    verdict = evaluate_command(command, self.security.patterns)
                    if verdict.blocked and self.security.enabled:
                        if self.approval_gateway is None:
                            return {
                                "ok": False,
                                "error": (
                                    f"命令被安全边界拦截（{verdict.reason}），"
                                    "且审核通道不可用，未执行"
                                ),
                            }
                        await self._emit(
                            "awaiting_approval",
                            tool=name,
                            message=f"等待审核：{command}",
                        )
                        decision = await self.approval_gateway.request(
                            command, verdict.reason
                        )
                        if not decision.get("approved"):
                            return {
                                "ok": False,
                                "error": str(
                                    decision.get("reason")
                                    or "命令未通过审核，未执行"
                                ),
                            }
                if self.terminal is None:
                    return open_terminal(command)
                return await run_in_thread(self.terminal.open, command)
            if name == "terminal_type":
                session, error = self._terminal_session(args.get("session_id"))
                if error is not None:
                    return error
                text = str(args["text"])
                interval = min(0.5, max(0.0, float(args.get("interval") or 0.0)))
                press_enter = bool(args.get("press_enter"))

                def _type() -> dict[str, Any]:
                    count = session.write(
                        text, interval=interval, press_enter=press_enter
                    )
                    suffix = "并回车" if press_enter else ""
                    return {
                        "ok": True,
                        "message": f"已在终端流式输入 {count} 字符{suffix}",
                        "session_id": session.id,
                    }

                return await run_in_thread(_type)
            if name == "terminal_read":
                session, error = self._terminal_session(args.get("session_id"))
                if error is not None:
                    return error
                return await run_in_thread(self._read_terminal, session)
            if name == "terminal_close":
                if self.terminal is None:
                    return {"ok": False, "error": "终端管理器不可用"}
                return await run_in_thread(
                    self.terminal.close, args.get("session_id")
                )
            if name == "list_skills":
                return {
                    "ok": True,
                    "message": catalog_text(self.skills),
                    "skills": [
                        {"name": skill.name, "description": skill.description}
                        for skill in self.skills
                    ],
                }
            if name == "read_skill":
                target = str(args.get("name") or "").strip()
                skill = find_skill(self.skills, target)
                if skill is None:
                    available = ", ".join(s.name for s in self.skills) or "无"
                    return {
                        "ok": False,
                        "error": f"未找到 SKILL「{target}」，当前可用：{available}",
                    }
                content = skill.body
                files = skill.files()
                if files:
                    content += "\n\n## 附带文件\n" + "\n".join(
                        f"- {str(skill.path / file)}" for file in files
                    )
                return {
                    "ok": True,
                    "message": f"已读取 SKILL「{skill.name}」",
                    "skill": skill.name,
                    "content": content,
                }
            if name == "wait":
                seconds = min(10.0, max(0.0, float(args.get("seconds", 0.5))))
                await asyncio.sleep(seconds)
                return {"ok": True, "message": f"已等待 {seconds:.1f} 秒"}
            if name == "screenshot":
                return {"ok": True, "message": "已获取最新截图（见下一条消息）"}
            return {"ok": False, "error": f"未知工具：{name}"}
        except (InputError, TerminalError, KeyError, TypeError, ValueError) as exc:
            return {"ok": False, "error": f"{name} 执行失败：{exc}"}

    def _terminal_session(
        self, session_id: Any
    ) -> tuple[Any, dict[str, Any] | None]:
        if self.terminal is None:
            return None, {"ok": False, "error": "终端管理器不可用"}
        try:
            session = self.terminal.get(
                str(session_id) if session_id is not None else None
            )
        except TerminalError as exc:
            return None, {"ok": False, "error": str(exc)}
        return session, None

    @staticmethod
    def _read_terminal(session: Any) -> dict[str, Any]:
        output = session.read()
        return {
            "ok": True,
            "message": "已读取终端新输出",
            "session_id": session.id,
            "output": output,
        }

    async def _prepare_ocr(self) -> None:
        """首次进入文本模式时探测 OCR，避免每个请求都重试加载模型。"""
        if self.ocr_checked or self.ocr is None or self.vision:
            return
        self.ocr_checked = True
        try:
            image = await run_in_thread(
                self.capture.capture_image, self.config.image_max_edge
            )
            result = await run_in_thread(self.ocr.read, image)
            self.ocr_ready = bool(result.ok)
            if not result.ok:
                logger.warning("PaddleOCR 初始化失败：%s", result.error)
        except Exception as exc:
            logger.warning("PaddleOCR 不可用，文本模式降级为键盘-only：%s", exc)

    async def _screen_content(self, label: str) -> dict[str, Any] | None:
        """返回当前屏幕的模型输入（视觉截图或 OCR 文本转写）。"""
        if self.vision:
            try:
                frame = self.capture.capture_jpeg(self.config.image_max_edge)
            except Exception:
                logger.warning("抓屏失败")
                return None
            return {
                "role": "user",
                "content": [
                    {"type": "text", "text": label},
                    self._image_content(frame),
                ],
            }
        if self.ocr is not None and self.ocr_ready:
            try:
                image = await run_in_thread(
                    self.capture.capture_image, self.config.image_max_edge
                )
                result = await run_in_thread(self.ocr.read, image)
            except Exception as exc:
                logger.warning("OCR 屏幕转写失败：%s", exc)
                return None
            return {
                "role": "user",
                "content": f"{label}\n{result.transcript(image.width, image.height)}",
            }
        return None

    async def run(
        self, command: str, cancel: asyncio.Event | None = None
    ) -> dict[str, Any]:
        if self.client is None:
            raise AgentError(
                "未配置 API Key（GEASS_API_KEY），无法调用模型接口"
            )

        cancel = cancel or asyncio.Event()
        await self._prepare_ocr()
        try:
            messages = await self._initial_messages(command)
        except Exception:
            logger.exception("初始截图失败")
            raise AgentError("无法抓取屏幕，Agent 无法启动")

        tools = self._tools()
        for step in range(1, self.config.max_steps + 1):
            if cancel.is_set():
                return {"state": "cancelled", "message": "任务已被用户中断"}

            await self._emit("thinking", step=step, message="正在观察屏幕并规划下一步…")
            try:
                response = await self._create_response(messages, tools)
            except Exception as exc:
                if self.vision and _is_vision_rejection(exc):
                    logger.info("模型不支持视觉输入，自动切换为文本模式")
                    self.vision = False
                    if self.vision_fallback_cb is not None:
                        try:
                            self.vision_fallback_cb()
                        except Exception:
                            logger.warning("持久化 vision=false 失败", exc_info=True)
                    await self._prepare_ocr()
                    tools = self._tools()
                    messages = await self._initial_messages(command)
                    await self._emit(
                        "thinking",
                        step=step,
                        message=(
                            "模型不支持视觉输入，已自动切换为"
                            + ("PaddleOCR 文本模式" if self.ocr_ready else "文本模式")
                            + "并重试"
                        ),
                    )
                    try:
                        response = await self._create_response(messages, tools)
                    except Exception as exc2:
                        logger.exception("模型调用失败")
                        return {"state": "error", "message": f"模型调用失败：{exc2}"}
                else:
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

            screen_content = await self._screen_content(
                "工具执行后的最新屏幕截图："
                if self.vision
                else "工具执行后的最新屏幕文本（PaddleOCR）："
            )
            if screen_content is not None:
                messages.append(screen_content)
            else:
                messages.append(
                    {
                        "role": "user",
                        "content": "（本次无法获取屏幕信息，请基于已有信息继续）",
                    }
                )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "请根据最新截图决定下一步操作；若任务已完成，调用 finish 总结结果。"
                        if self.vision
                        else "请继续完成剩余步骤；若任务已完成，调用 finish 总结结果。"
                    ),
                }
            )

        return {
            "state": "limit",
            "message": f"已达到 {self.config.max_steps} 步上限，任务终止",
        }

    def _system_prompt(self) -> str:
        prompt = SYSTEM_PROMPT + "\n\n环境信息：" + ENVIRONMENT_HINT
        if self.skills:
            prompt += "\n\n技能规则：\n" + catalog_text(self.skills)
        if not self.vision:
            if self.ocr is not None and self.ocr_ready:
                prompt += (
                    "\n注意：当前模型不支持图像输入，但已启用 PaddleOCR 屏幕识别。"
                    "每步会把屏幕文本和文本包围盒中心坐标（归一化 0~1）作为文本提供，"
                    "可以据此调用 move/click 等鼠标工具；若目标没有对应文本，"
                    "不要盲目点击，可先调用 screenshot 获取最新文本。"
                )
            else:
                prompt += (
                    "\n注意：当前模型不支持视觉输入，且 PaddleOCR 不可用。"
                    "不要调用坐标类或截图工具"
                    "（move/click/double_click/right_click/scroll/drag/screenshot），"
                    "仅使用 type_text、key_press、open_terminal、terminal_*、"
                    "wait 完成键盘与终端类任务。"
                )
        return prompt

    def _tools(self) -> list[dict[str, Any]]:
        if self.vision or (self.ocr is not None and self.ocr_ready):
            source = TOOLS
        else:
            source = [tool for tool in TOOLS if tool["name"] in TEXT_ONLY_TOOLS]
        # Chat Completions / DeepSeek 要求 function 字段嵌套：
        # {"type":"function","function":{"name":...,"description":...,"parameters":...}}
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in source
        ]

    async def _initial_messages(self, command: str) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": command},
        ]
        screen_content = await self._screen_content("当前屏幕状态如下：")
        if screen_content is not None:
            messages.append(screen_content)
        return messages

    async def _create_response(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ):
        return await self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            tools=tools,
        )

    @staticmethod
    def _image_content(jpeg: bytes) -> dict[str, Any]:
        encoded = base64.b64encode(jpeg).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
        }
