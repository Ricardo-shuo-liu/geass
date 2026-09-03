"""CLI 会话：light / deliberate 双模式，复用 Geass 资产。"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from ..config import AgentConfig
from ..safety import UNTRUSTED_BEGIN, UNTRUSTED_END
from ..skills import catalog_text, find_skill
from .tui import TUI

CIL_SYSTEM = (
    "你是 CIL，运行在电脑终端上的 Geass 命令行助手。你可以读取记忆、RAG、"
    "技能与 COT/ROT 资产来回答，也可以执行终端命令（执行前会征得用户确认）。"
    "你绝不能执行任何 GUI 键鼠操作。"
)

_EXIT_WORDS = {"q", "quit", "exit", "/exit", "/quit"}

CIL_TOOLS = [
    {
        "type": "function",
        "name": "recall",
        "description": "按关键字检索持久记忆。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "rag_search",
        "description": "检索 RAG 数据源中的相关片段。",
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
        "name": "list_skills",
        "description": "列出当前可用 SKILL。",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "read_skill",
        "description": "读取指定 SKILL 的完整说明。",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "run_command",
        "description": "在终端执行一条命令（执行前需用户确认）。",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
            "additionalProperties": False,
        },
    },
]


class CILSession:
    def __init__(
        self,
        client: Any,
        config: AgentConfig,
        memory: Any = None,
        rag: Any = None,
        skills: list | None = None,
        pot: Any = None,
        mcp: Any = None,
        tui: TUI | None = None,
    ) -> None:
        self.client = client
        self.config = config
        self.memory = memory
        self.rag = rag
        self.skills = list(skills or [])
        self.pot = pot
        self.mcp = mcp
        self.tui = tui or TUI()
        self.mode = "light"
        self.history: list[dict[str, Any]] = []

    def _asset_context(self, question: str) -> str:
        parts: list[str] = []
        if self.pot is not None:
            if self.config.pot_inject_cot:
                cot = self.pot.get_cot()
                if cot:
                    parts.append("## Global-COT\n" + cot)
            hits = max(0, int(self.config.pot_rot_hits))
            rots = []
            if self.config.pot_inject_rot and hits > 0:
                pinned = getattr(self, "_pinned_rot", None)
                if pinned:
                    rot = self.pot.get_rot(pinned)
                    if rot is not None and rot.enabled:
                        rots.append(rot)
                if len(rots) < hits:
                    rots.extend(self.pot.select_rots(question, limit=hits - len(rots)))
                for rot in rots:
                    parts.append(f"## ROT「{rot.name}」（{rot.role}）\n{rot.body}")
            self.tui.update_status(self.mode, [rot.name for rot in rots])
        if self.skills:
            parts.append("## SKILL 清单\n" + catalog_text(self.skills))
        if self.memory is not None:
            context = self.memory.context_for(question, limit=6)
            if context:
                parts.append(
                    "## 持久记忆\n" + UNTRUSTED_BEGIN + "\n" + context + "\n" + UNTRUSTED_END
                )
        if self.rag is not None:
            try:
                context = self.rag.context_for(
                    question,
                    limit=self.config.rag_inject_hits,
                    max_chars=self.config.rag_inject_chars,
                    min_score=self.config.rag_inject_min_score,
                )
                if context:
                    parts.append(
                        "## RAG 参考\n" + UNTRUSTED_BEGIN + "\n" + context + "\n" + UNTRUSTED_END
                    )
            except Exception:
                pass
        return "\n\n".join(parts)

    async def run(self) -> None:
        self.tui.model = self.config.model
        self.tui.render_header()
        while True:
            text = self.tui.ask()
            if not text.strip():
                continue
            if text.strip().lower() in _EXIT_WORDS:
                self.tui.say("CIL", "再见。")
                return
            if text.strip().startswith("/"):
                if await self._slash(text.strip()):
                    return
                continue
            await self._turn(text)

    async def _turn(self, text: str) -> None:
        if self.mode == "deliberate":
            await self._deliberate(text)
        else:
            await self._chat(text, tool_use=True)

    async def _chat(self, text: str, tool_use: bool) -> str:
        system = CIL_SYSTEM + "\n\n" + self._asset_context(text)
        messages = [
            {"role": "system", "content": system},
            *self.history[-12:],
            {"role": "user", "content": text},
        ]
        base_tools = [{"type": "function", "function": tool} for tool in CIL_TOOLS]
        if tool_use and self.mcp is not None:
            base_tools.extend({"type": "function", "function": tool} for tool in self.mcp.schemas())
        tools = base_tools if tool_use else None
        answer = ""
        for _ in range(8):
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                tools=tools,
            )
            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None) or []
            if not tool_calls:
                answer = str(getattr(message, "content", "") or "")
                break
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
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = await self._execute_tool(call.function.name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": answer})
        self.tui.say("CIL", answer)
        return answer

    async def _execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if self.mcp is not None:
            result = await self.mcp.call(name, args)
            if result is not None:
                return result
        if name == "recall":
            if self.memory is None:
                return {"ok": False, "error": "记忆未启用"}
            entries = self.memory.recall(
                str(args.get("query") or ""),
                limit=max(1, min(20, int(args.get("limit") or 8))),
            )
            return {"ok": True, "matches": entries, "count": len(entries)}
        if name == "rag_search":
            if self.rag is None:
                return {"ok": False, "error": "RAG 未启用"}
            hits = self.rag.search(
                str(args.get("query") or ""),
                source=args.get("source"),
                limit=max(1, min(20, int(args.get("limit") or 5))),
            )
            return {"ok": True, "matches": hits, "count": len(hits)}
        if name == "list_skills":
            return {
                "ok": True,
                "skills": [
                    {"name": skill.name, "description": skill.description} for skill in self.skills
                ],
            }
        if name == "read_skill":
            skill = find_skill(self.skills, str(args.get("name") or ""))
            if skill is None:
                return {"ok": False, "error": "技能不存在"}
            return {"ok": True, "content": skill.body}
        if name == "run_command":
            command = str(args.get("command") or "").strip()
            if not command:
                return {"ok": False, "error": "命令为空"}
            if not self.tui.confirm(f"确认执行终端命令：{command}"):
                return {"ok": False, "error": "用户拒绝执行"}
            try:
                completed = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except subprocess.TimeoutExpired:
                return {"ok": False, "error": "命令执行超时"}
            return {
                "ok": completed.returncode == 0,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-2000:],
            }
        return {"ok": False, "error": f"未知工具：{name}"}

    async def _deliberate(self, question: str) -> str:
        rots = []
        if self.pot is not None:
            rots = self.pot.select_rots(question, limit=max(1, int(self.config.cli_subagents)))
            if not rots:
                rots = self.pot.list_rots(include_disabled=False)[
                    : max(1, int(self.config.cli_subagents))
                ]
        if not rots:
            self.tui.say("CIL", "没有可用 ROT，使用默认视角分析。")
            rots = [type("ROT", (), {"name": "general", "role": "通用分析者", "body": ""})()]

        rounds = max(1, int(self.config.cli_rounds))
        transcript: list[str] = []
        self.tui.say("CIL", f"进入思辨：{len(rots)} 个角色 × {rounds} 轮")
        for round_index in range(1, rounds + 1):
            for rot in rots:
                transcript_text = "\n".join(transcript[-12:]) or "（暂无讨论）"
                messages = [
                    {
                        "role": "system",
                        "content": (f"你是角色「{rot.name}」：{rot.role}\n{rot.body}"),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"讨论主题：{question}\n\n已有讨论：\n{transcript_text}\n"
                            "请从你的角色视角继续分析、质疑或补充，只输出文字。"
                        ),
                    },
                ]
                response = await self.client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                )
                text = str(response.choices[0].message.content or "")
                self.tui.say(f"第{round_index}轮 · {rot.name}", text)
                transcript.append(f"「{rot.name}」：{text}")

        summary_messages = [
            {
                "role": "system",
                "content": CIL_SYSTEM + "\n你是主 Agent，负责汇总各角色讨论并回答用户。",
            },
            {
                "role": "user",
                "content": (
                    f"用户问题：{question}\n\n各角色讨论：\n"
                    + "\n".join(transcript)
                    + "\n请汇总观点并给出结论。"
                ),
            },
        ]
        response = await self.client.chat.completions.create(
            model=self.config.model,
            messages=summary_messages,
        )
        answer = str(response.choices[0].message.content or "")
        self.tui.say("主 Agent", answer)
        self.history.append({"role": "user", "content": question})
        self.history.append({"role": "assistant", "content": answer})
        return answer

    async def _slash(self, command: str) -> bool:
        parts = command.split(None, 1)
        name = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        if name == "/exit":
            self.tui.say("CIL", "再见。")
            return True
        if name == "/help":
            self.tui.say(
                "CIL",
                "/help /mode /deliberate /light /rot list|use <name> "
                "/skill list|read <name> /rag search <query> /mcp list "
                "/cot show /clear /exit",
            )
        elif name == "/mode":
            self.tui.say("CIL", self.tui._status_text())
        elif name == "/deliberate":
            self.mode = "deliberate"
            self.tui.update_status("deliberate")
            self.tui.say("CIL", "已进入思辨模式（Delib>）。")
        elif name == "/light":
            self.mode = "light"
            self.tui.update_status("light")
            self.tui.say("CIL", "已返回 light 模式。")
        elif name == "/rot":
            await self._slash_rot(rest)
        elif name == "/skill":
            await self._slash_skill(rest)
        elif name == "/rag":
            if rest.startswith("search "):
                await self._chat(rest[len("search ") :], tool_use=False)
            else:
                self.tui.say("CIL", "用法：/rag search <query>")
        elif name == "/mcp":
            if self.mcp is None:
                self.tui.say("CIL", "MCP 未启用")
            elif not rest or rest == "list":
                records = self.mcp.servers()
                for record in records:
                    status = "启用" if record.enabled else "停用"
                    verified = "已测试" if record.verified else "测试失败"
                    self.tui.say(
                        "MCP",
                        f"{record.name} [{status}/{verified}] · {len(record.tools)} 个工具",
                    )
                if not records:
                    self.tui.say("MCP", "暂无服务器（用 geass mcp add/import 添加）")
            else:
                self.tui.say("CIL", "用法：/mcp list")
        elif name == "/cot":
            cot = self.pot.get_cot() if self.pot is not None else ""
            self.tui.say("Global-COT", cot or "（暂无 COT）")
        elif name == "/clear":
            self.tui.clear()
        else:
            self.tui.say("CIL", f"未知命令：{name}（/help 查看）")
        return False

    async def _slash_rot(self, rest: str) -> None:
        parts = rest.split(None, 1)
        action = parts[0] if parts else ""
        if action == "list":
            rots = self.pot.list_rots() if self.pot is not None else []
            for rot in rots:
                status = "启用" if rot.enabled else "停用"
                self.tui.say(f"ROT {rot.name}", f"[{status}] {rot.description}")
        elif action == "use" and len(parts) > 1:
            if self.pot is None:
                return
            rot = self.pot.get_rot(parts[1])
            if rot is None or not rot.enabled:
                self.tui.say("CIL", f"ROT 不可用：{parts[1]}")
                return
            self._pinned_rot = rot.name
            self.tui.say("CIL", f"已固定 ROT：{rot.name}")
        else:
            self.tui.say("CIL", "用法：/rot list 或 /rot use <name>")

    async def _slash_skill(self, rest: str) -> None:
        parts = rest.split(None, 1)
        action = parts[0] if parts else ""
        if action == "list":
            for skill in self.skills:
                self.tui.say(f"SKILL {skill.name}", skill.description)
        elif action == "read" and len(parts) > 1:
            skill = find_skill(self.skills, parts[1])
            if skill is None:
                self.tui.say("CIL", f"技能不存在：{parts[1]}")
                return
            self.tui.say(f"SKILL {skill.name}", skill.body)
        else:
            self.tui.say("CIL", "用法：/skill list 或 /skill read <name>")
