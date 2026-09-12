"""Agent 工具注册表：每个工具在此一处登记 schema、元数据与处理器。

`geass.agent` 只负责查表分发、屏幕差异检测与异常翻译，循环层逻辑不
进入本模块；新增工具只需在 :data:`TOOL_REGISTRY` 中追加一个 :class:`Tool`
条目并实现对应的异步处理器。
"""

from __future__ import annotations

import asyncio
import contextvars
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .asyncutil import run_in_thread
from .io import browser
from .io.shell import open_terminal
from .safety import evaluate_command
from .skills import catalog_text, find_skill

Handler = Callable[[Any, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Tool:
    """一条工具定义：OpenAI 函数 schema + 模式元数据 + 处理器。"""

    name: str
    description: str
    parameters: dict[str, Any]
    text_only: bool
    state_changing: bool
    handler: Handler

    def openai_schema(self) -> dict[str, Any]:
        """返回 `geass.agent._tools` 所消费的扁平函数描述。"""
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


_NUMBER = {"type": "number", "minimum": 0.0, "maximum": 1.0}


def _point(required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"x": _NUMBER, "y": _NUMBER},
        "required": required,
        "additionalProperties": False,
    }


async def _move(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    x, y = agent.norm_to_px(args["x"], args["y"])
    agent.backend.move(x, y)
    return {"ok": True, "message": f"已移动鼠标到 ({x},{y})"}


async def _click(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    x, y = agent.norm_to_px(args["x"], args["y"])
    button = str(args.get("button") or "left")
    agent.backend.click(x, y, button=button)
    return {"ok": True, "message": f"已在 ({x},{y}) 单击 {button}"}


async def _double_click(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    x, y = agent.norm_to_px(args["x"], args["y"])
    agent.backend.double_click(x, y)
    return {"ok": True, "message": f"已在 ({x},{y}) 双击"}


async def _right_click(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    x, y = agent.norm_to_px(args["x"], args["y"])
    agent.backend.right_click(x, y)
    return {"ok": True, "message": f"已在 ({x},{y}) 右键"}


async def _scroll(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    dx, dy = int(args.get("dx") or 0), int(args.get("dy") or 0)
    agent.backend.scroll(dx, dy)
    return {"ok": True, "message": f"已滚动 dx={dx} dy={dy}"}


async def _drag(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    x1, y1 = agent.norm_to_px(args["x1"], args["y1"])
    x2, y2 = agent.norm_to_px(args["x2"], args["y2"])
    agent.backend.drag(x1, y1, x2, y2)
    return {"ok": True, "message": f"已从 ({x1},{y1}) 拖到 ({x2},{y2})"}


async def _type_text(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    text = str(args["text"])
    agent.backend.type_text(text)
    return {"ok": True, "message": f"已输入文本（{len(text)} 字符）"}


async def _key_press(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    combo = str(args["combo"])
    agent.backend.key_press(combo)
    return {"ok": True, "message": f"已按键 {combo}"}


async def _review_command(agent: Any, command: str, tool: str) -> dict[str, Any] | None:
    """高危命令走人工审核通道；允许时返回 None，拒绝时返回错误 dict。"""
    if PREAPPROVED.get():
        return None
    if agent.security is None or not command.strip():
        return None
    verdict = evaluate_command(command, agent.security.patterns)
    if not (verdict.blocked and agent.security.enabled):
        return None
    if agent.approval_gateway is None:
        return {
            "ok": False,
            "error": f"命令被安全边界拦截（{verdict.reason}），且审核通道不可用，未执行",
        }
    await agent._emit(
        "awaiting_approval",
        tool=tool,
        message=f"等待审核：{command}",
    )
    decision = await agent.approval_gateway.request(command, verdict.reason)
    if not decision.get("approved"):
        return {
            "ok": False,
            "error": str(decision.get("reason") or "命令未通过审核，未执行"),
        }
    return None


async def _open_terminal(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    command = str(args.get("command") or "")
    denied = await _review_command(agent, command, "open_terminal")
    if denied is not None:
        return denied
    if agent.terminal is None:
        return open_terminal(command)
    return await run_in_thread(agent.terminal.open, command)


async def _terminal_type(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    session, error = agent._terminal_session(args.get("session_id"))
    if error is not None:
        return error
    text = str(args["text"])
    interval = min(0.5, max(0.0, float(args.get("interval") or 0.0)))
    press_enter = bool(args.get("press_enter"))
    may_execute = press_enter or "\n" in text or "\r" in text
    verdict = (
        evaluate_command(text, agent.security.patterns) if agent.security is not None else None
    )
    if may_execute or (verdict is not None and verdict.blocked):
        denied = await _review_command(agent, text, "terminal_type")
        if denied is not None:
            return denied

    def _type() -> dict[str, Any]:
        count = session.write(text, interval=interval, press_enter=press_enter)
        suffix = "并回车" if press_enter else ""
        return {
            "ok": True,
            "message": f"已在终端流式输入 {count} 字符{suffix}",
            "session_id": session.id,
        }

    return await run_in_thread(_type)


async def _terminal_read(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    session, error = agent._terminal_session(args.get("session_id"))
    if error is not None:
        return error
    return await run_in_thread(agent._read_terminal, session)


async def _terminal_close(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    if agent.terminal is None:
        return {"ok": False, "error": "终端管理器不可用"}
    return await run_in_thread(agent.terminal.close, args.get("session_id"))


async def _list_skills(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "message": catalog_text(agent.skills),
        "skills": [
            {"name": skill.name, "description": skill.description} for skill in agent.skills
        ],
    }


async def _read_skill(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    target = str(args.get("name") or "").strip()
    skill = find_skill(agent.skills, target)
    if skill is None:
        available = ", ".join(s.name for s in agent.skills) or "无"
        return {
            "ok": False,
            "error": f"未找到 SKILL「{target}」，当前可用：{available}",
        }
    content = skill.body
    files = skill.files()
    if files:
        content += "\n\n## 附带文件\n" + "\n".join(f"- {str(skill.path / file)}" for file in files)
    return {
        "ok": True,
        "message": f"已读取 SKILL「{skill.name}」",
        "skill": skill.name,
        "content": content,
    }


async def _wait(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    seconds = min(10.0, max(0.0, float(args.get("seconds", 0.5))))
    await asyncio.sleep(seconds)
    return {"ok": True, "message": f"已等待 {seconds:.1f} 秒"}


async def _find_text(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    text = str(args.get("text") or "").strip()
    if not text:
        return {"ok": False, "error": "find_text 需要非空 text"}
    exact = bool(args.get("exact"))
    limit = min(20, max(1, int(args.get("limit") or 8)))
    if not await agent._ensure_ocr_ready():
        return {
            "ok": False,
            "error": "PaddleOCR 不可用，无法按文本查找坐标",
        }
    try:
        image = await run_in_thread(agent.capture.capture_image, agent.config.image_max_edge)
        result = await run_in_thread(agent.ocr.read, image)
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
        "message": (f"找到 {len(matches)} 处文本「{text}」，用返回的 x/y 调用 move/click"),
    }


async def _find_element(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("name") or "").strip()
    if not query:
        return {"ok": False, "error": "find_element 需要非空 name"}
    role = str(args.get("role") or "").strip()
    limit = min(20, max(1, int(args.get("limit") or 10)))

    def _lookup() -> list[dict[str, Any]]:
        from .io.accessibility import find_elements

        return find_elements(name=query, role=role, limit=limit)

    try:
        found = await run_in_thread(_lookup)
    except Exception as exc:
        return {"ok": False, "error": f"控件查找失败：{exc}"}
    if not found:
        return {
            "ok": True,
            "found": False,
            "matches": [],
            "message": f"未找到控件「{query}」",
        }
    width, height = agent.backend.screen_size()
    matches = [
        {
            "name": item["name"],
            "role": item.get("role", ""),
            "x": round((item["x"] + item["w"] / 2) / width, 4) if width else 0.5,
            "y": round((item["y"] + item["h"] / 2) / height, 4) if height else 0.5,
        }
        for item in found
    ]
    return {
        "ok": True,
        "found": True,
        "count": len(matches),
        "matches": matches,
        "message": (f"找到 {len(matches)} 个控件，用返回的 x/y 调用 move/click"),
    }


async def _browser(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    action = str(args.get("action") or "open")
    url = str(args.get("url") or "")
    return await run_in_thread(browser.open_page, action, url)


async def _window_info(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
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
        active.get("name") or "（无标题窗口）" if active is not None else "（未检测到活动窗口）"
    )
    return {
        "ok": True,
        "count": len(windows),
        "active_window": active,
        "windows": windows,
        "message": f"当前活动窗口：{active_label}；共发现 {len(windows)} 个窗口",
    }


async def _screenshot(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "message": "已获取最新截图（见下一条消息）"}


async def _plan(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    return agent._plan_result(args)


async def _schedule(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    return agent._handle_schedule(args)


async def _remember(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    return await run_in_thread(agent._remember, args)


async def _recall(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    return await run_in_thread(agent._recall, args)


async def _forget(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    return await run_in_thread(agent._forget, args)


async def _rag_add(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    return await run_in_thread(agent._rag_add, args)


async def _rag_search(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    return await run_in_thread(agent._rag_search, args)


async def _rag_list(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    return await run_in_thread(agent._rag_list, args)


async def _rag_remove(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    return await run_in_thread(agent._rag_remove, args)


async def _pot_list(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    return await run_in_thread(agent._pot_list, args)


async def _pot_use(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    return await run_in_thread(agent._pot_use, args)


async def _background(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    return agent._background(args)


async def _finish(agent: Any, args: dict[str, Any]) -> dict[str, Any]:
    summary = str(args.get("summary") or "") or "任务完成"
    return {"ok": True, "message": summary}


TOOL_REGISTRY: dict[str, Tool] = {
    tool.name: tool
    for tool in [
        Tool(
            name="move",
            description="把鼠标移动到屏幕指定位置。x、y 为 0~1 的归一化坐标。",
            parameters=_point(["x", "y"]),
            text_only=False,
            state_changing=False,
            handler=_move,
        ),
        Tool(
            name="click",
            description="在指定位置单击。button 可选 left/right/middle，默认 left。",
            parameters={
                "type": "object",
                "properties": {
                    "x": _NUMBER,
                    "y": _NUMBER,
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                    },
                },
                "required": ["x", "y"],
                "additionalProperties": False,
            },
            text_only=False,
            state_changing=True,
            handler=_click,
        ),
        Tool(
            name="double_click",
            description="在指定位置双击左键。",
            parameters=_point(["x", "y"]),
            text_only=False,
            state_changing=True,
            handler=_double_click,
        ),
        Tool(
            name="right_click",
            description="在指定位置单击右键。",
            parameters=_point(["x", "y"]),
            text_only=False,
            state_changing=True,
            handler=_right_click,
        ),
        Tool(
            name="scroll",
            description="滚动鼠标滚轮。dy>0 向上滚、dy<0 向下滚；dx 为水平滚动（支持时生效）。",
            parameters={
                "type": "object",
                "properties": {
                    "dx": {"type": "integer"},
                    "dy": {"type": "integer"},
                },
                "required": ["dx", "dy"],
                "additionalProperties": False,
            },
            text_only=False,
            state_changing=True,
            handler=_scroll,
        ),
        Tool(
            name="drag",
            description="从 (x1,y1) 按住左键拖动到 (x2,y2)。坐标均为归一化值。",
            parameters={
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
            text_only=False,
            state_changing=True,
            handler=_drag,
        ),
        Tool(
            name="type_text",
            description=(
                "在当前焦点处输入文本（模拟键盘逐字输入，适合 ASCII；中文受输入法限制）。"
            ),
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=True,
            handler=_type_text,
        ),
        Tool(
            name="key_press",
            description='按单个键或组合键，例如 "enter"、"esc"、"ctrl+c"、"alt+tab"。',
            parameters={
                "type": "object",
                "properties": {"combo": {"type": "string"}},
                "required": ["combo"],
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=True,
            handler=_key_press,
        ),
        Tool(
            name="open_terminal",
            description=(
                "打开一个新的可见终端窗口，并可一键执行一条 shell 命令并等待其输出。"
                "返回 session_id 和捕获到的 output；command 留空则只打开空白终端，"
                "终端会保持打开，可用 terminal_read 监控输出。"
            ),
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_open_terminal,
        ),
        Tool(
            name="terminal_type",
            description=(
                "向指定终端会话流式输入文本（模拟人类逐字打字）。"
                "session_id 留空时使用最近的会话；interval 是每字符间隔秒数，"
                "press_enter=true 表示输入后回车。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "text": {"type": "string"},
                    "interval": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 0.5,
                    },
                    "press_enter": {"type": "boolean"},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_terminal_type,
        ),
        Tool(
            name="terminal_read",
            description=(
                "读取指定终端会话自上次读取以来的新输出；session_id 留空时读取"
                "最近的会话。用于监控命令执行结果。"
            ),
            parameters={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_terminal_read,
        ),
        Tool(
            name="terminal_close",
            description="关闭指定终端会话；session_id 留空时关闭最近的会话。",
            parameters={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_terminal_close,
        ),
        Tool(
            name="list_skills",
            description="列出当前已加载的 SKILL 名称与描述。",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_list_skills,
        ),
        Tool(
            name="read_skill",
            description=(
                "读取指定 SKILL 的完整说明（渐进披露）。先根据系统提示中的清单"
                "或 list_skills 选择技能，再调用本工具获取正文与附带文件。"
            ),
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_read_skill,
        ),
        Tool(
            name="wait",
            description="等待指定秒数（0.1~10），用于等待界面加载。",
            parameters={
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "number",
                        "minimum": 0.1,
                        "maximum": 10.0,
                    }
                },
                "required": ["seconds"],
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_wait,
        ),
        Tool(
            name="find_text",
            description=(
                "在当前屏幕中查找包含指定文本的位置，返回文本包围盒中心的"
                "归一化坐标，供 move/click 使用。exact=true 时要求完全匹配；"
                "返回多个匹配时按列表顺序选择。适合不确定目标位置时先查坐标再点击。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "exact": {"type": "boolean"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
            text_only=False,
            state_changing=False,
            handler=_find_text,
        ),
        Tool(
            name="find_element",
            description=(
                "通过桌面无障碍树（AT-SPI）查找可交互控件，返回控件中心归一化坐标。"
                "name 是控件名称或名称的一部分；role 可选，如 push button、"
                "menu item、text、combo box。找不到文本或图标类目标时使用本工具。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
            text_only=False,
            state_changing=False,
            handler=_find_element,
        ),
        Tool(
            name="browser",
            description=(
                "用默认浏览器打开网址、新建标签页或新建窗口。比手动点击浏览器"
                "图标更可靠。action 取 open（打开页面）/new_tab（新建标签页）/"
                "new_window（新建窗口）；url 缺省时创建空白页。启动是异步的，"
                "调用后需 wait 1~3 秒，并用 window_info 与 screenshot 验证。"
            ),
            parameters={
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
            text_only=True,
            state_changing=False,
            handler=_browser,
        ),
        Tool(
            name="window_info",
            description=(
                "读取当前活动窗口与可见顶层窗口列表（标题、角色、是否活动、"
                "屏幕位置）。用于验证浏览器页面、应用窗口是否真的打开，"
                "或判断当前焦点在哪个应用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_window_info,
        ),
        Tool(
            name="screenshot",
            description="获取最新屏幕截图，帮助确认当前界面状态。",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            text_only=False,
            state_changing=False,
            handler=_screenshot,
        ),
        Tool(
            name="plan",
            description=(
                "记录或更新任务计划。困难任务应在执行前先调用本工具："
                "difficulty 取 easy/hard，goal 为任务目标，steps 为步骤数组。"
                "执行中可再次调用，用 current_step（1 起）标记当前推进到第几步。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "difficulty": {
                        "type": "string",
                        "enum": ["easy", "hard"],
                    },
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
            text_only=True,
            state_changing=False,
            handler=_plan,
        ),
        Tool(
            name="schedule",
            description=(
                "把用户要求定时执行的动作登记为定时任务。run_at 使用本地 ISO "
                "时间（如 2026-08-26T17:00:00）或 epoch 秒。persist=true 表示"
                "服务重启后仍执行，必须先征得用户同意：第一次调用不带 confirm "
                "登记待确认内容，用户明确同意且再次确认时间与命令后，再带 "
                "confirm=true 完成创建；临时任务 persist=false 直接创建。"
            ),
            parameters={
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
            text_only=True,
            state_changing=False,
            handler=_schedule,
        ),
        Tool(
            name="remember",
            description=(
                "把跨任务有用的信息写入持久记忆（按 key 覆盖）。适合保存用户"
                "偏好、环境事实、常用账号/路径、失败原因等。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["key", "value"],
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_remember,
        ),
        Tool(
            name="recall",
            description=(
                "按关键字检索持久记忆，返回相关条目；query 为空时返回最近条目。"
                "开始不熟悉的任务前先查询相关记忆。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_recall,
        ),
        Tool(
            name="forget",
            description="按 key 删除一条持久记忆（信息已过时或用户要求忘记时使用）。",
            parameters={
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_forget,
        ),
        Tool(
            name="rag_add",
            description=(
                "把本机文件或文件夹锁定为 RAG 数据源（文件夹递归读取）。"
                "extensions 为允许的后缀（逗号分隔，如 '.md,.txt'），缺省使用"
                "内置白名单。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "name": {"type": "string"},
                    "extensions": {"type": "string"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_rag_add,
        ),
        Tool(
            name="rag_search",
            description=(
                "在 RAG 数据源中检索与 query 最相关的片段，返回来源文件、"
                "分块序号、相似度与正文；source 留空则检索全部数据源。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "source": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_rag_search,
        ),
        Tool(
            name="rag_list",
            description="列出全部 RAG 数据源（名称、模式、文件数、分块数、是否启用）。",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_rag_list,
        ),
        Tool(
            name="rag_remove",
            description=(
                "删除 RAG 数据源或其单个文件的镜像；rel_path 缺省时删除整个"
                "数据源，只影响 RAG 镜像，不删除原始文件。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "rel_path": {"type": "string"},
                },
                "required": ["source"],
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_rag_remove,
        ),
        Tool(
            name="background",
            description=(
                "把一条命令放到后台执行（独立 Agent 实例，与当前任务并行；"
                "键鼠类动作仍全局串行）。返回 task_id，可用手机资源面板"
                "查看进度、结果或取消。"
            ),
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_background,
        ),
        Tool(
            name="pot_list",
            description="查看 Global-COT 与全部 ROT（角色思维模板）清单。",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_pot_list,
        ),
        Tool(
            name="pot_use",
            description=("固定/切换当前注入的 ROT 角色模板；name 留空表示取消固定，恢复自动选择。"),
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_pot_use,
        ),
        Tool(
            name="finish",
            description="任务完成或无法继续时调用，summary 简要说明结果。",
            parameters={
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
                "additionalProperties": False,
            },
            text_only=True,
            state_changing=False,
            handler=_finish,
        ),
    ]
}

TOOLS: list[dict[str, Any]] = [TOOL_REGISTRY[name].openai_schema() for name in TOOL_REGISTRY]

TEXT_ONLY_TOOLS: set[str] = {name for name, tool in TOOL_REGISTRY.items() if tool.text_only}

STATE_CHANGING_TOOLS: set[str] = {
    name for name, tool in TOOL_REGISTRY.items() if tool.state_changing
}

PREAPPROVED: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "geass_tool_preapproved", default=False
)

# 幽灵操作预览：工具 -> 可视化种类。MCP 工具统一走 generic。
PREVIEW_SPECS: dict[str, str] = {
    "move": "point",
    "click": "point",
    "double_click": "point",
    "right_click": "point",
    "drag": "drag",
    "scroll": "scroll",
    "type_text": "text",
    "key_press": "key",
    "open_terminal": "command",
    "terminal_type": "terminal",
    "terminal_close": "terminal",
    "browser": "url",
}


def preview_kind(tool: str) -> str | None:
    name = str(tool or "")
    if name.startswith("mcp__"):
        return "generic"
    return PREVIEW_SPECS.get(name)


def _clamp01(value: Any, default: float = 0.5) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return min(1.0, max(0.0, number))


def _short(value: Any, limit: int = 60) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_preview(tool: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """按工具生成预览元数据；不参与预览的工具返回 None。"""
    kind = preview_kind(tool)
    if kind is None:
        return None
    data = args or {}
    if kind == "point":
        target = {"x": _clamp01(data.get("x")), "y": _clamp01(data.get("y"))}
        button = str(data.get("button") or "left")
        label = {
            "move": "移动鼠标到",
            "click": "单击",
            "double_click": "双击",
            "right_click": "右键单击",
        }.get(tool, "操作")
        summary = f"{label} ({target['x']:.2f}, {target['y']:.2f})"
        if tool == "click" and button != "left":
            summary += f" · {button}"
        return {"kind": kind, "target": target, "summary": summary}
    if kind == "drag":
        target = {
            "x1": _clamp01(data.get("x1")),
            "y1": _clamp01(data.get("y1")),
            "x2": _clamp01(data.get("x2")),
            "y2": _clamp01(data.get("y2")),
        }
        summary = (
            f"拖拽 ({target['x1']:.2f}, {target['y1']:.2f}) → "
            f"({target['x2']:.2f}, {target['y2']:.2f})"
        )
        return {"kind": kind, "target": target, "summary": summary}
    if kind == "scroll":
        dx = max(-50, min(50, int(data.get("dx") or 0)))
        dy = max(-50, min(50, int(data.get("dy") or 0)))
        return {
            "kind": kind,
            "target": {"dx": dx, "dy": dy},
            "summary": f"滚动 dx={dx} dy={dy}",
        }
    if kind == "text":
        text = str(data.get("text") or "")
        return {
            "kind": kind,
            "target": {"text": text},
            "summary": f"输入文本：{_short(text)}",
        }
    if kind == "key":
        combo = str(data.get("combo") or "")
        return {
            "kind": kind,
            "target": {"combo": combo},
            "summary": f"按键：{_short(combo, 30)}",
        }
    if kind == "command":
        command = str(data.get("command") or "")
        summary = f"终端命令：{_short(command)}" if command else "打开空白终端"
        return {
            "kind": kind,
            "target": {"command": command},
            "summary": summary,
        }
    if kind == "terminal":
        if tool == "terminal_close":
            return {
                "kind": kind,
                "target": {"session_id": str(data.get("session_id") or "")},
                "summary": "关闭终端会话",
            }
        text = str(data.get("text") or "")
        return {
            "kind": kind,
            "target": {
                "session_id": str(data.get("session_id") or ""),
                "text": text,
                "press_enter": bool(data.get("press_enter")),
            },
            "summary": f"终端输入：{_short(text)}" + (" + 回车" if data.get("press_enter") else ""),
        }
    if kind == "url":
        action = str(data.get("action") or "open")
        url = str(data.get("url") or "")
        return {
            "kind": kind,
            "target": {"action": action, "url": url},
            "summary": f"浏览器 {action}：{_short(url, 80)}",
        }
    return {
        "kind": "generic",
        "target": {"args": dict(data)},
        "summary": f"调用工具 {_short(tool, 40)}",
    }


def apply_preview_target(tool: str, args: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """把用户修正后的 target 合并回工具参数（按 kind 校验/钳制）。"""
    kind = preview_kind(tool)
    merged = dict(args or {})
    if not kind or not isinstance(target, dict):
        return merged
    if kind == "point":
        if "x" in target:
            merged["x"] = _clamp01(target.get("x"))
        if "y" in target:
            merged["y"] = _clamp01(target.get("y"))
    elif kind == "drag":
        for key in ("x1", "y1", "x2", "y2"):
            if key in target:
                merged[key] = _clamp01(target.get(key))
    elif kind == "scroll":
        if "dx" in target:
            merged["dx"] = max(-50, min(50, int(target.get("dx") or 0)))
        if "dy" in target:
            merged["dy"] = max(-50, min(50, int(target.get("dy") or 0)))
    elif kind in ("text", "command"):
        key = "text" if kind == "text" else "command"
        if key in target:
            merged[key] = str(target.get(key) or "")[:2000]
    elif kind == "key":
        if "combo" in target:
            merged["combo"] = str(target.get("combo") or "")[:128]
    elif kind == "terminal":
        if "text" in target:
            merged["text"] = str(target.get("text") or "")[:2000]
        if "press_enter" in target:
            merged["press_enter"] = bool(target.get("press_enter"))
    elif kind == "url":
        if "url" in target:
            merged["url"] = str(target.get("url") or "")[:2048]
        if "action" in target and str(target.get("action")) in ("open", "new_tab", "new_window"):
            merged["action"] = str(target.get("action"))
    return merged
