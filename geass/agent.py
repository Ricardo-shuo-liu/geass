"""Agent 循环：截图 -> OpenAI 视觉模型 -> 工具调用 -> 本地执行 -> 回填结果。"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import platform
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from openai import AsyncOpenAI

from .asyncutil import run_in_thread
from .config import AgentConfig, SecurityConfig
from .io import browser
from .io.backend import InputBackend, InputError
from .io.browser import BrowserError
from .io.shell import open_terminal
from .io.terminal import TerminalError, TerminalManager
from .memory import Memory
from .safety import evaluate_command
from .screen import ScreenCapture, image_difference
from .skills import Skill, catalog_text, find_skill
from .tasks import TaskPlan

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
    "6. 需要点击目标时，优先调用 find_text（按文字找）或 find_element"
    "（按控件名找）拿到精确归一化坐标，再用返回的 x/y 调用 click；"
    "不要凭截图凭空估计坐标。能用键盘/快捷键完成的操作优先用"
    "type_text / key_press，减少对像素坐标的依赖。\n"
    "7. 如果用户任务匹配某个 SKILL 的描述，先调用 read_skill 获取该 SKILL"
    "的完整说明，再严格按说明执行；不要凭空编造不存在的技能。\n"
    "8. open_terminal 中的高危 shell 命令会先由用户审核；若审核被拒绝或超时，"
    "不要重复提交同一命令，换用其他方式，或调用 finish 说明无法继续。\n"
    "9. 任务完成或无法继续时，必须调用 finish 并说明结果。\n"
    "10. 每个任务开始前先判断难度，难度由你决定：简单任务（单步、目标明确、"
    "一次操作即可完成）可以直接调用工具执行；困难任务（多步骤、跨应用、"
    "需要新建页面/搜索/等待/验证，或不确定如何完成）必须先调用 plan 工具，"
    "用 difficulty='hard' 记录目标和完整步骤，再按计划逐步执行并验证。"
    "不确定时按困难任务处理。\n"
    "11. 涉及打开浏览器、打开网址、新建标签页/窗口的任务，优先调用 browser "
    "工具（action 取 open/new_tab/new_window），不要手动寻找并点击浏览器"
    "图标；浏览器启动后 wait 1~3 秒，可用 screenshot 时用它验证页面状态。"
    "若 browser 工具失败，可用 open_terminal 执行 xdg-open \"URL\" 兜底，"
    "但不要反复启动同一个页面。\n"
    "12. 跨任务有用的信息（用户偏好、常用账号、环境事实、失败原因）用 "
    "remember 持久化；开始任务前可用 recall 查询相关记忆，避免重复踩坑。\n"
    "13. 计划中每一步执行后都要验证再进入下一步：优先用 find_text / "
    "find_element / window_info / screenshot 确认预期状态；工具结果若提示"
    "屏幕未变化，说明操作可能没生效，应调整坐标或换一种方法重试，"
    "不要机械重复同一操作。\n"
    "14. 当用户要求“在某个时间做某事”时，先调用 schedule 工具登记："
    "run_at 使用本地 ISO 时间（如 2026-08-26T17:00:00）。一次性近期任务 "
    "persist=false 直接创建；只有用户明确要求长期/跨重启/重复执行时才需要"
    "持久化，并且必须先询问用户是否长期保存，用户同意后再询问一次确认"
    "命令与时间，最后带 confirm=true 完成创建；未经用户确认不要带 "
    "confirm=true。\n"
    "15. 系统提示可能包含 Global-COT 与若干 ROT（角色思维模板）；当用户要求"
    "以特定角色/视角分析时，可调用 pot_list 查看，并用 pot_use 固定注入的 ROT。"
    "\n16. 用户要求“后台运行/在后台执行 xxx”时，调用 background 工具把命令"
    "交给后台任务管理器；后台任务与当前任务并行，键鼠动作仍全局串行，"
    "结果可在手机资源面板查看。"
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
        "name": "find_text",
        "description": (
            "在当前屏幕中查找包含指定文本的位置，返回文本包围盒中心的"
            "归一化坐标，供 move/click 使用。exact=true 时要求完全匹配；"
            "返回多个匹配时按列表顺序选择。适合不确定目标位置时先查坐标再点击。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "exact": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "find_element",
        "description": (
            "通过桌面无障碍树（AT-SPI）查找可交互控件，返回控件中心归一化坐标。"
            "name 是控件名称或名称的一部分；role 可选，如 push button、"
            "menu item、text、combo box。找不到文本或图标类目标时使用本工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "role": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "browser",
        "description": (
            "用默认浏览器打开网址、新建标签页或新建窗口。比手动点击浏览器"
            "图标更可靠。action 取 open（打开页面）/new_tab（新建标签页）/"
            "new_window（新建窗口）；url 缺省时创建空白页。启动是异步的，"
            "调用后需 wait 1~3 秒，并用 window_info 与 screenshot 验证。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["open", "new_tab", "new_window"],
                },
                "url": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "window_info",
        "description": (
            "读取当前活动窗口与可见顶层窗口列表（标题、角色、是否活动、"
            "屏幕位置）。用于验证浏览器页面、应用窗口是否真的打开，"
            "或判断当前焦点在哪个应用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
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
        "name": "plan",
        "description": (
            "记录或更新任务计划。困难任务应在执行前先调用本工具："
            "difficulty 取 easy/hard，goal 为任务目标，steps 为步骤数组。"
            "执行中可再次调用，用 current_step（1 起）标记当前推进到第几步。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "difficulty": {"type": "string", "enum": ["easy", "hard"]},
                "goal": {"type": "string"},
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 20,
                },
                "current_step": {"type": "integer", "minimum": 1},
            },
            "required": ["difficulty", "goal", "steps"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "schedule",
        "description": (
            "把用户要求定时执行的动作登记为定时任务。run_at 使用本地 ISO "
            "时间（如 2026-08-26T17:00:00）或 epoch 秒。persist=true 表示"
            "服务重启后仍执行，必须先征得用户同意：第一次调用不带 confirm "
            "登记待确认内容，用户明确同意且再次确认时间与命令后，再带 "
            "confirm=true 完成创建；临时任务 persist=false 直接创建。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "run_at": {"type": "string"},
                "persist": {"type": "boolean"},
                "confirm": {"type": "boolean"},
            },
            "required": ["command", "run_at"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "remember",
        "description": (
            "把跨任务有用的信息写入持久记忆（按 key 覆盖）。适合保存用户"
            "偏好、环境事实、常用账号/路径、失败原因等。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["key", "value"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "recall",
        "description": (
            "按关键字检索持久记忆，返回相关条目；query 为空时返回最近条目。"
            "开始不熟悉的任务前先查询相关记忆。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "forget",
        "description": "按 key 删除一条持久记忆（信息已过时或用户要求忘记时使用）。",
        "parameters": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "rag_add",
        "description": (
            "把本机文件或文件夹锁定为 RAG 数据源（文件夹递归读取）。"
            "extensions 为允许的后缀（逗号分隔，如 '.md,.txt'），缺省使用"
            "内置白名单。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "name": {"type": "string"},
                "extensions": {"type": "string"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "rag_search",
        "description": (
            "在 RAG 数据源中检索与 query 最相关的片段，返回来源文件、"
            "分块序号、相似度与正文；source 留空则检索全部数据源。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "source": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "rag_list",
        "description": "列出全部 RAG 数据源（名称、模式、文件数、分块数、是否启用）。",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "rag_remove",
        "description": (
            "删除 RAG 数据源或其单个文件的镜像；rel_path 缺省时删除整个"
            "数据源，只影响 RAG 镜像，不删除原始文件。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "rel_path": {"type": "string"},
            },
            "required": ["source"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "background",
        "description": (
            "把一条命令放到后台执行（独立 Agent 实例，与当前任务并行；"
            "键鼠类动作仍全局串行）。返回 task_id，可用手机资源面板"
            "查看进度、结果或取消。"
        ),
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "pot_list",
        "description": "查看 Global-COT 与全部 ROT（角色思维模板）清单。",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "pot_use",
        "description": (
            "固定/切换当前注入的 ROT 角色模板；name 留空表示取消固定，"
            "恢复自动选择。"
        ),
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": False,
        },
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
    "plan",
    "schedule",
    "browser",
    "window_info",
    "remember",
    "recall",
    "forget",
    "rag_add",
    "rag_search",
    "rag_list",
    "rag_remove",
    "background",
    "pot_list",
    "pot_use",
    "wait",
    "finish",
}

MEMORY_TOOL_NAMES = {"remember", "recall", "forget"}
STATE_CHANGING_TOOLS = {
    "click",
    "double_click",
    "right_click",
    "drag",
    "scroll",
    "type_text",
    "key_press",
}
SCREEN_DIFF_THRESHOLD = 0.003

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
        memory: Memory | None = None,
        schedule_store: Any = None,
        rag: Any = None,
        pot: Any = None,
        input_lock: Any = None,
        background_starter: Any = None,
        compression_path: str | None = None,
    ) -> None:
        self.client = client
        self.backend = backend
        self.capture = capture
        self.config = config
        self.status_cb = status_cb
        self.vision_fallback_cb = vision_fallback_cb
        self.vision = self.resolve_vision()
        self.skills = list(skills or [])
        self.terminal = terminal
        self.ocr = ocr
        self.ocr_ready = False
        self.ocr_checked = False
        self.security = security
        self.approval_gateway = approval_gateway
        self.memory = memory
        self.plan: TaskPlan | None = None
        self.schedule_store = schedule_store
        self.pending_schedule: dict[str, Any] | None = None
        self.rag = rag
        self.pot = pot
        self.pinned_rot: str | None = None
        self.last_trace: dict[str, Any] | None = None
        self.input_lock = input_lock
        self.background_starter = background_starter
        self.compression_path = compression_path
        self._compress_watermark = 1

    def resolve_vision(self) -> bool:
        """按 vision_whitelist 决定是否给模型发截图。

        白名单非空时以白名单为准：当前模型在名单内 → 视觉模式；
        不在名单内 → 文本模式（可再与 PaddleOCR 配对）。
        白名单为空时回退到 `config.vision` 布尔开关，保持旧行为。
        """
        whitelist = {
            name.strip().casefold()
            for name in self.config.vision_whitelist
            if name.strip()
        }
        if whitelist:
            return self.config.model.strip().casefold() in whitelist
        return self.config.vision

    async def _emit(
        self,
        state: str,
        step: int = 0,
        tool: str | None = None,
        message: str = "",
        **extra: Any,
    ) -> None:
        if self.status_cb is not None:
            await self.status_cb(
                {
                    "type": "agent_status",
                    "state": state,
                    "step": step,
                    "tool": tool,
                    "message": message,
                    **extra,
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
            if name == "plan":
                return self._plan_result(args)
            if name == "schedule":
                return self._handle_schedule(args)
            if name == "browser":
                action = str(args.get("action") or "open")
                url = str(args.get("url") or "")
                return await run_in_thread(browser.open_page, action, url)
            if name == "window_info":
                limit = max(1, min(50, int(args.get("limit") or 20)))

                def _lookup_windows() -> list[dict[str, Any]]:
                    from .io.accessibility import list_windows

                    return list_windows(limit=limit)

                try:
                    windows = await run_in_thread(_lookup_windows)
                except Exception as exc:
                    return {
                        "ok": False,
                        "error": f"窗口信息读取失败：{exc}",
                    }
                active = next(
                    (window for window in windows if window.get("active")),
                    None,
                )
                active_label = (
                    active.get("name") or "（无标题窗口）"
                    if active is not None
                    else "（未检测到活动窗口）"
                )
                return {
                    "ok": True,
                    "count": len(windows),
                    "active_window": active,
                    "windows": windows,
                    "message": f"当前活动窗口：{active_label}；共发现 {len(windows)} 个窗口",
                }
            if name == "remember":
                return await run_in_thread(self._remember, args)
            if name == "recall":
                return await run_in_thread(self._recall, args)
            if name == "forget":
                return await run_in_thread(self._forget, args)
            if name == "rag_add":
                return await run_in_thread(self._rag_add, args)
            if name == "rag_search":
                return await run_in_thread(self._rag_search, args)
            if name == "rag_list":
                return await run_in_thread(self._rag_list, args)
            if name == "rag_remove":
                return await run_in_thread(self._rag_remove, args)
            if name == "pot_list":
                return await run_in_thread(self._pot_list, args)
            if name == "pot_use":
                return await run_in_thread(self._pot_use, args)
            if name == "background":
                return self._background(args)
            if name == "find_text":
                text = str(args.get("text") or "").strip()
                if not text:
                    return {"ok": False, "error": "find_text 需要非空 text"}
                exact = bool(args.get("exact"))
                limit = min(20, max(1, int(args.get("limit") or 8)))
                if not await self._ensure_ocr_ready():
                    return {
                        "ok": False,
                        "error": "PaddleOCR 不可用，无法按文本查找坐标",
                    }
                try:
                    image = await run_in_thread(
                        self.capture.capture_image, self.config.image_max_edge
                    )
                    result = await run_in_thread(self.ocr.read, image)
                except Exception as exc:
                    return {"ok": False, "error": f"屏幕文本识别失败：{exc}"}
                if not result.ok:
                    return {"ok": False, "error": f"OCR 失败：{result.error}"}
                needle = text.casefold()
                matches = []
                for box in result.boxes:
                    candidate = str(box.text).casefold()
                    hit = candidate == needle if exact else needle in candidate
                    if hit:
                        matches.append(
                            {
                                "text": box.text,
                                "x": round(float(box.x), 4),
                                "y": round(float(box.y), 4),
                                "confidence": round(float(box.confidence), 4),
                            }
                        )
                    if len(matches) >= limit:
                        break
                if not matches:
                    return {
                        "ok": True,
                        "found": False,
                        "matches": [],
                        "message": f"当前屏幕未找到文本「{text}」",
                    }
                return {
                    "ok": True,
                    "found": True,
                    "count": len(matches),
                    "matches": matches,
                    "message": (
                        f"找到 {len(matches)} 处文本「{text}」，"
                        "用返回的 x/y 调用 move/click"
                    ),
                }
            if name == "find_element":
                query = str(args.get("name") or "").strip()
                if not query:
                    return {"ok": False, "error": "find_element 需要非空 name"}
                role = str(args.get("role") or "").strip()
                limit = min(20, max(1, int(args.get("limit") or 10)))

                def _lookup() -> list[dict[str, Any]]:
                    from .io.accessibility import find_elements

                    return find_elements(
                        name=query, role=role, limit=limit
                    )

                try:
                    found = await run_in_thread(_lookup)
                except Exception as exc:
                    return {
                        "ok": False,
                        "error": f"控件查找失败：{exc}",
                    }
                if not found:
                    return {
                        "ok": True,
                        "found": False,
                        "matches": [],
                        "message": f"未找到控件「{query}」",
                    }
                width, height = self.backend.screen_size()
                matches = [
                    {
                        "name": item["name"],
                        "role": item.get("role", ""),
                        "x": round((item["x"] + item["w"] / 2) / width, 4)
                        if width
                        else 0.5,
                        "y": round((item["y"] + item["h"] / 2) / height, 4)
                        if height
                        else 0.5,
                    }
                    for item in found
                ]
                return {
                    "ok": True,
                    "found": True,
                    "count": len(matches),
                    "matches": matches,
                    "message": (
                        f"找到 {len(matches)} 个控件，用返回的 x/y 调用 move/click"
                    ),
                }
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
        except (
            InputError,
            TerminalError,
            BrowserError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            return {"ok": False, "error": f"{name} 执行失败：{exc}"}

    def _plan_result(self, args: dict[str, Any]) -> dict[str, Any]:
        try:
            plan = TaskPlan.from_args(args)
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": f"计划无效：{exc}"}
        self.plan = plan
        if self.last_trace is not None:
            self.last_trace["plan"] = plan.render()
        return {
            "ok": True,
            "message": "计划已记录，请按步骤执行并逐步验证",
            "plan": plan.to_dict(),
        }

    @staticmethod
    def _parse_run_at(value: Any) -> float:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("缺少执行时间")
        try:
            return float(raw)
        except ValueError:
            pass
        from datetime import datetime

        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"执行时间格式无效：{raw}") from exc
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return parsed.timestamp()

    def _handle_schedule(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.schedule_store is None:
            return {"ok": False, "error": "定时系统未启用"}
        command = str(args.get("command") or "").strip()
        if not command:
            return {"ok": False, "error": "定时命令不能为空"}
        persist = bool(args.get("persist"))
        confirm = bool(args.get("confirm"))
        try:
            run_at = self._parse_run_at(args.get("run_at"))
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        if run_at <= time.time():
            return {"ok": False, "error": "执行时间必须晚于当前时间"}

        if persist and not confirm:
            self.pending_schedule = {
                "command": command,
                "run_at": run_at,
            }
            return {
                "ok": True,
                "status": "awaiting_confirmation",
                "message": (
                    "已登记待确认的长期定时任务。请先询问用户是否长期保存，"
                    "并在用户同意且确认时间与命令后，再次调用 schedule "
                    "（confirm=true）完成创建"
                ),
            }

        if persist:
            pending = self.pending_schedule
            if (
                pending is None
                or pending.get("command") != command
                or abs(float(pending.get("run_at") or 0) - run_at) > 60
            ):
                return {
                    "ok": False,
                    "error": (
                        "没有匹配的待确认定时任务。请先不带 confirm 调用一次，"
                        "征得用户同意后再确认创建"
                    ),
                }
            self.pending_schedule = None

        try:
            job = self.schedule_store.add(
                command, run_at, persistent=persist
            )
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        label = "长期" if persist else "临时"
        return {
            "ok": True,
            "job": job.to_dict(),
            "message": f"已创建{label}定时任务：{command}",
        }

    def _remember(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.memory is None:
            return {"ok": False, "error": "记忆系统未启用"}
        try:
            entry = self.memory.remember(
                str(args.get("key") or ""), str(args.get("value") or "")
            )
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": f"写入记忆失败：{exc}"}
        return {
            "ok": True,
            "message": f"已记住「{entry.key}」",
            "key": entry.key,
        }

    def _recall(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.memory is None:
            return {"ok": False, "error": "记忆系统未启用"}
        query = str(args.get("query") or "").strip()
        limit = max(1, min(20, int(args.get("limit") or 8)))
        entries = self.memory.recall(query, limit=limit)
        if not entries:
            return {
                "ok": True,
                "found": False,
                "matches": [],
                "message": "记忆中没有匹配条目",
            }
        return {
            "ok": True,
            "found": True,
            "count": len(entries),
            "matches": entries,
            "message": f"找到 {len(entries)} 条相关记忆",
        }

    def _forget(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.memory is None:
            return {"ok": False, "error": "记忆系统未启用"}
        key = str(args.get("key") or "").strip()
        removed = self.memory.forget(key)
        message = f"已删除记忆「{key}」" if removed else f"没有找到记忆「{key}」"
        return {"ok": True, "removed": removed, "message": message}

    def _rag_add(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.rag is None:
            return {"ok": False, "error": "RAG 未启用"}
        exts = None
        if args.get("extensions"):
            exts = [
                item.strip()
                for item in str(args["extensions"]).split(",")
                if item.strip()
            ]
        try:
            return self.rag.add_source(
                str(args.get("path") or ""),
                name=args.get("name"),
                exts=exts,
            )
        except (ValueError, OSError) as exc:
            return {"ok": False, "error": f"RAG 导入失败：{exc}"}

    def _rag_search(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.rag is None:
            return {"ok": False, "error": "RAG 未启用"}
        query = str(args.get("query") or "").strip()
        if not query:
            return {"ok": False, "error": "rag_search 需要非空 query"}
        try:
            hits = self.rag.search(
                query,
                source=args.get("source"),
                limit=max(1, min(20, int(args.get("limit") or 5))),
            )
        except Exception as exc:
            return {"ok": False, "error": f"RAG 检索失败：{exc}"}
        if not hits:
            return {
                "ok": True,
                "found": False,
                "matches": [],
                "message": "RAG 未找到相关内容",
            }
        matches = [
            {
                "source": hit.get("source_name"),
                "path": hit.get("path"),
                "chunk_index": hit.get("index"),
                "score": hit.get("score"),
                "text": hit.get("text"),
            }
            for hit in hits
        ]
        return {
            "ok": True,
            "found": True,
            "count": len(matches),
            "matches": matches,
            "message": f"找到 {len(matches)} 条相关片段",
        }

    def _rag_list(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.rag is None:
            return {"ok": False, "error": "RAG 未启用"}
        sources = self.rag.list_sources()
        return {
            "ok": True,
            "count": len(sources),
            "sources": sources,
            "message": f"共 {len(sources)} 个 RAG 数据源",
        }

    def _rag_remove(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.rag is None:
            return {"ok": False, "error": "RAG 未启用"}
        source = str(args.get("source") or "").strip()
        rel_path = str(args.get("rel_path") or "").strip()
        if rel_path:
            removed = self.rag.remove_file(source, rel_path)
            message = (
                f"已删除 {source}/{rel_path} 的 RAG 镜像"
                if removed
                else f"找不到 {source}/{rel_path}"
            )
        else:
            removed = self.rag.remove_source(source)
            message = f"已删除 RAG 数据源：{source}" if removed else f"数据源不存在：{source}"
        return {"ok": True, "removed": removed, "message": message}

    def _pot_list(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.pot is None:
            return {"ok": False, "error": "POT 未启用"}
        rots = self.pot.list_rots()
        return {
            "ok": True,
            "cot": self.pot.get_cot(),
            "rots": [rot.to_dict() for rot in rots],
            "pinned_rot": self.pinned_rot,
            "message": f"Global-COT：{'有' if self.pot.get_cot() else '无'}；ROT 共 {len(rots)} 个",
        }

    def _pot_use(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.pot is None:
            return {"ok": False, "error": "POT 未启用"}
        name = str(args.get("name") or "").strip()
        if not name:
            self.pinned_rot = None
            return {"ok": True, "pinned_rot": None, "message": "已取消固定 ROT，恢复自动选择"}
        rot = self.pot.get_rot(name)
        if rot is None:
            return {"ok": False, "error": f"ROT 不存在：{name}"}
        if not rot.enabled:
            return {"ok": False, "error": f"ROT 已停用：{name}"}
        self.pinned_rot = rot.name
        return {"ok": True, "pinned_rot": rot.name, "message": f"已固定 ROT：{rot.name}"}

    def _background(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.background_starter is None:
            return {"ok": False, "error": "后台任务系统未启用"}
        return self.background_starter(str(args.get("command") or ""))

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

    async def _ensure_ocr_ready(self) -> bool:
        """探测 OCR 是否可用；只探测一次，失败后不再重复。"""
        if self.ocr is None:
            return False
        if self.ocr_ready:
            return True
        if self.ocr_checked:
            return False
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
        return self.ocr_ready

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

    def _capture_change_before(self) -> Any:
        try:
            return self.capture.capture_image(max_edge=160)
        except Exception:
            return None

    async def _capture_change_after(self, before: Any) -> dict[str, Any] | None:
        """动作后稍等片刻再抓屏，判断界面是否真的发生变化。"""
        await asyncio.sleep(0.18)
        try:
            after = self.capture.capture_image(max_edge=160)
        except Exception:
            return None
        ratio = image_difference(before, after)
        return {
            "screen_changed": ratio >= SCREEN_DIFF_THRESHOLD,
            "screen_change_ratio": round(float(ratio), 4),
        }

    async def _guarded_action(
        self, name: str, args: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """执行工具；键鼠类动作在全局输入锁内串行。"""
        if name in STATE_CHANGING_TOOLS:
            async def run_with_capture():
                before = self._capture_change_before()
                result = await self._execute(name, args)
                change = (
                    await self._capture_change_after(before)
                    if before is not None
                    else None
                )
                return result, change

            if self.input_lock is not None:
                async with self.input_lock:
                    return await run_with_capture()
            return await run_with_capture()
        return await self._execute(name, args), None

    async def _maybe_compress(self, messages: list[dict[str, Any]]) -> None:
        if not getattr(self.config, "context_compress_enabled", True):
            return
        if self.client is None:
            return
        threshold = int(getattr(self.config, "context_compress_after", 18))
        char_limit = int(getattr(self.config, "context_compress_chars", 20000))
        if len(messages) < threshold:
            return
        total_chars = sum(
            len(str(message.get("content") or "")) for message in messages
        )
        if total_chars < char_limit:
            return
        keep = 8
        end = len(messages) - keep
        start = self._compress_watermark
        if start >= end:
            return
        segment = messages[start:end]
        texts = [
            f"[{message.get('role')}] "
            + (
                str(message.get("content"))
                if isinstance(message.get("content"), str)
                else "（含图像/复杂内容）"
            )
            for message in segment
        ]
        label = "【早期对话摘要】\n"
        try:
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是对话压缩器。把给定对话压缩成保留用户意图、"
                            "计划、已完成步骤、关键结果与结论的中文摘要，"
                            "只输出摘要正文。"
                        ),
                    },
                    {"role": "user", "content": "\n".join(texts)},
                ],
                max_tokens=800,
            )
            summary = str(response.choices[0].message.content or "").strip()
            if not summary:
                raise ValueError("空摘要")
        except Exception:
            logger.warning("上下文压缩失败，降级保留首条用户消息", exc_info=True)
            first_user = next(
                (message for message in segment if message.get("role") == "user"),
                segment[0],
            )
            if isinstance(first_user.get("content"), str):
                summary = str(first_user["content"])[:4000]
            else:
                summary = "（早期对话摘要，含图像/复杂内容）"
            label = "【早期对话摘要（降级）】\n"
        replacement = [{"role": "user", "content": label + summary}]
        self._log_compression(segment, summary)
        messages[start:end] = replacement
        self._compress_watermark = start + 1

    def _log_compression(
        self, segment: list[dict[str, Any]], summary: str
    ) -> None:
        try:
            path = Path(
                self.compression_path
                or os.path.join(
                    os.environ.get("GEASS_HOME", str(Path.home())),
                    ".geass",
                    ".tasks",
                    "compressed.jsonl",
                )
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "time": time.time(),
                            "summary": summary,
                            "segment": segment,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            lines = path.read_text(encoding="utf-8").splitlines()
            if len(lines) > 200:
                path.write_text(
                    "\n".join(lines[-200:]) + "\n", encoding="utf-8"
                )
        except OSError:
            logger.warning("压缩日志写入失败", exc_info=True)

    async def run(
        self, command: str, cancel: asyncio.Event | None = None
    ) -> dict[str, Any]:
        if self.client is None:
            raise AgentError(
                "未配置 API Key（GEASS_API_KEY），无法调用模型接口"
            )

        cancel = cancel or asyncio.Event()
        self.plan = None
        self.last_trace = {
            "time": time.time(),
            "command": command,
            "plan": None,
            "tools": [],
            "result": None,
        }
        self._compress_watermark = 1
        if not self.vision:
            await self._ensure_ocr_ready()
        try:
            messages = await self._initial_messages(command)
        except Exception:
            logger.exception("初始截图失败")
            raise AgentError("无法抓取屏幕，Agent 无法启动")

        tools = self._tools()
        for step in range(1, self.config.max_steps + 1):
            if cancel.is_set():
                self.last_trace["result"] = "任务已被用户中断"
                return {"state": "cancelled", "message": "任务已被用户中断"}

            await self._emit("thinking", step=step, message="正在观察屏幕并规划下一步…")
            await self._maybe_compress(messages)
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
                    await self._ensure_ocr_ready()
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
                        self.last_trace["result"] = f"模型调用失败：{exc2}"
                        return {"state": "error", "message": f"模型调用失败：{exc2}"}
                else:
                    logger.exception("模型调用失败")
                    self.last_trace["result"] = f"模型调用失败：{exc}"
                    return {"state": "error", "message": f"模型调用失败：{exc}"}

            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None) or []
            if not tool_calls:
                text = getattr(message, "content", "") or "任务结束（模型未调用工具）"
                self.last_trace["result"] = text
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
                    self.last_trace["result"] = summary
                    await self._emit("done", step=step, tool="finish", message=summary)
                    return {"state": "done", "message": summary}

                await self._emit("acting", step=step, tool=name, message=f"执行工具 {name}…")
                self.last_trace["tools"].append(name)
                result, change = await self._guarded_action(name, args)
                if change is not None:
                    result = {**result, **change}
                    if not change["screen_changed"]:
                        result["message"] = (
                            str(result.get("message") or "")
                            + "；注意：屏幕未检测到变化，操作可能未生效"
                        ).lstrip("；")
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
                if name == "plan" and result.get("ok"):
                    await self._emit(
                        "planned",
                        step=step,
                        tool="plan",
                        message=f"已制定{len(result.get('plan', {}).get('steps', []))}步计划",
                        plan=result.get("plan"),
                    )
                if cancel.is_set():
                    self.last_trace["result"] = "任务已被用户中断"
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
                    "content": self._next_instruction(),
                }
            )

        self.last_trace["result"] = (
            f"已达到 {self.config.max_steps} 步上限，任务终止"
        )
        return {
            "state": "limit",
            "message": f"已达到 {self.config.max_steps} 步上限，任务终止",
        }

    def _next_instruction(self) -> str:
        if self.vision:
            text = "请根据最新截图决定下一步操作；若任务已完成，调用 finish 总结结果。"
        else:
            text = "请继续完成剩余步骤；若任务已完成，调用 finish 总结结果。"
        if self.plan is not None:
            text += (
                "\n\n"
                + self.plan.render()
                + "\n请严格按上述计划推进：完成一步后再做下一步，"
                "每步都要验证结果；进度变化时再次调用 plan 更新 current_step。"
            )
        return text

    def _system_prompt(
        self,
        command: str = "",
        rag_context: str = "",
        pot_context: str = "",
    ) -> str:
        prompt = SYSTEM_PROMPT + "\n\n环境信息：" + ENVIRONMENT_HINT
        if self.skills:
            prompt += "\n\n技能规则：\n" + catalog_text(self.skills)
        if self.memory is not None:
            context = self.memory.context_for(
                command, limit=self.config.memory_context_entries
            )
            if context:
                prompt += "\n\n持久记忆（与本任务相关的最近条目）：\n" + context
        if rag_context:
            prompt += (
                "\n\nRAG 参考资料（来自用户数据源，供回答与执行参考，"
                "以实际观察到的界面为准）：\n" + rag_context
            )
        if pot_context:
            prompt += "\n\n" + pot_context
        if not self.vision:
            if self.ocr is not None and self.ocr_ready:
                prompt += (
                    "\n注意：当前未启用图像输入，但已与 PaddleOCR 屏幕识别配对。"
                    "每步会把屏幕文本和文本包围盒中心坐标（归一化 0~1）作为文本提供，"
                    "可以据此调用 move/click 等鼠标工具；若目标没有对应文本，"
                    "不要盲目点击，可先调用 screenshot 获取最新文本。"
                )
            else:
                prompt += (
                    "\n注意：当前未启用图像输入，且 PaddleOCR 不可用。"
                    "不要调用坐标类或截图工具"
                    "（move/click/double_click/right_click/scroll/drag/screenshot），"
                    "仅使用 type_text、key_press、open_terminal、terminal_*、"
                    "browser、plan、remember、recall、forget、wait 完成键盘、"
                    "终端与浏览器类任务。"
                )
        return prompt

    def _tools(self) -> list[dict[str, Any]]:
        if self.vision or (self.ocr is not None and self.ocr_ready):
            source = TOOLS
        else:
            source = [tool for tool in TOOLS if tool["name"] in TEXT_ONLY_TOOLS]
        if self.memory is None:
            source = [
                tool for tool in source if tool["name"] not in MEMORY_TOOL_NAMES
            ]
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
        rag_context = await self._rag_context(command)
        pot_context = await self._pot_context(command)
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": self._system_prompt(
                    command, rag_context, pot_context
                ),
            },
            {"role": "user", "content": command},
        ]
        screen_content = await self._screen_content("当前屏幕状态如下：")
        if screen_content is not None:
            messages.append(screen_content)
        return messages

    async def _pot_context(self, command: str) -> str:
        if self.pot is None or not getattr(self.config, "pot_enabled", True):
            return ""

        def build() -> str:
            parts: list[str] = []
            if getattr(self.config, "pot_inject_cot", True):
                cot = self.pot.get_cot()
                if cot:
                    parts.append("## Global-COT（通用思维范式）\n" + cot)
            hits = max(0, int(getattr(self.config, "pot_rot_hits", 2)))
            if getattr(self.config, "pot_inject_rot", True) and hits > 0:
                rots = []
                if self.pinned_rot:
                    pinned = self.pot.get_rot(self.pinned_rot)
                    if pinned is not None and pinned.enabled:
                        rots.append(pinned)
                if len(rots) < hits:
                    rots.extend(
                        self.pot.select_rots(command, limit=hits - len(rots))
                    )
                for rot in rots[:hits]:
                    parts.append(
                        f"## ROT「{rot.name}」（{rot.role}）\n{rot.body}"
                    )
            return "\n\n".join(parts)

        try:
            return await run_in_thread(build)
        except Exception:
            logger.warning("POT 注入失败，跳过", exc_info=True)
            return ""

    async def _rag_context(self, command: str) -> str:
        if (
            self.rag is None
            or not getattr(self.config, "rag_enabled", True)
            or not getattr(self.config, "rag_inject_enabled", True)
        ):
            return ""
        try:
            return await run_in_thread(
                lambda: self.rag.context_for(
                    command,
                    limit=self.config.rag_inject_hits,
                    max_chars=self.config.rag_inject_chars,
                    min_score=self.config.rag_inject_min_score,
                )
            )
        except Exception:
            logger.warning("RAG 注入失败，跳过", exc_info=True)
            return ""

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
