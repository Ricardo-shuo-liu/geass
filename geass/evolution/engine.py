"""空闲进化引擎：把用户高频使用模式自动沉淀为新的 SKILL，并驱动 POT 反思。

引擎由服务端在后台运行：持续检测"当前没有任务且空闲超过阈值"，随后把
持久记忆与最近任务历史交给模型，让模型判断是否值得新增一个底层、通用的
SKILL，并把结果写入运行时 SKILL 根目录（``.system/`` 之外）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from ..safety import check_injected_content
from ..skills import (
    FRONTMATTER_RE,
    Skill,
    load_skills,
    sync_system_skills,
)
from .pot import POTStore

logger = logging.getLogger(__name__)

POLL_INTERVAL = 10.0
HISTORY_LIMIT = 200
CONTEXT_HISTORY_LIMIT = 40
CONTEXT_MEMORY_LIMIT = 20
CONTEXT_CATALOG_CHARS = 2000
NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")

EVOLUTION_SYSTEM_PROMPT = (
    "你是 Geass 的进化器。根据用户记忆和最近任务，判断是否应把某个反复"
    "出现、且现有 SKILL 未覆盖的使用模式沉淀为一个新的 SKILL。\n"
    "约束：\n"
    "1. 只生成底层、通用的多步工作流；单个工具能完成的事情不要生成；\n"
    "2. SKILL 只能使用已有工具：move/click/double_click/right_click/scroll/"
    "drag/type_text/key_press/open_terminal/terminal_type/terminal_read/"
    "terminal_close/browser/window_info/find_text/find_element/screenshot/"
    "wait/plan/remember/recall/finish；\n"
    "3. 信息不足或没有新价值时 create=false；\n"
    '4. 输出严格 JSON：{"create": bool, "name": "小写短横线", '
    '"description": "何时使用", "body": "SKILL 正文（不含 frontmatter）", '
    '"reason": "简短理由"}。'
)

StatusCallback = Callable[[dict[str, Any]], Awaitable[None]]
ActivityCallback = Callable[[], float]


class EvolutionEngine:
    """后台轮询空闲状态，并调用模型进化 SKILL。"""

    def __init__(
        self,
        client: Any,
        config: Any,
        memory: Any,
        skill_root: str | Path,
        source_dir: str | Path,
        status_cb: StatusCallback | None = None,
        activity_since: ActivityCallback | None = None,
        pot: POTStore | None = None,
        tasks_active: Callable[[], bool] | None = None,
    ) -> None:
        self.client = client
        self.config = config
        self.memory = memory
        self.root = Path(skill_root)
        self.source_dir = Path(source_dir)
        self.status_cb = status_cb
        self.activity_since = activity_since
        self.pot = pot
        self.tasks_active = tasks_active
        self._running = False
        self._last_run = 0.0

    @property
    def evolution_dir(self) -> Path:
        return self.root / ".evolution"

    @property
    def tasks_path(self) -> Path:
        return self.evolution_dir / "tasks.jsonl"

    def record_task(self, text: str) -> None:
        text = str(text or "").strip()
        if not text:
            return
        try:
            self.evolution_dir.mkdir(parents=True, exist_ok=True)
            line = json.dumps({"time": time.time(), "command": text}, ensure_ascii=False)
            with self.tasks_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            self._trim_history()
        except OSError:
            logger.warning("任务历史写入失败", exc_info=True)

    def _trim_history(self) -> None:
        if not self.tasks_path.exists():
            return
        try:
            lines = self.tasks_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        if len(lines) > HISTORY_LIMIT:
            try:
                self.tasks_path.write_text(
                    "\n".join(lines[-HISTORY_LIMIT:]) + "\n",
                    encoding="utf-8",
                )
            except OSError:
                logger.warning("任务历史裁剪失败", exc_info=True)

    def _recent_history(self, limit: int = CONTEXT_HISTORY_LIMIT) -> list[str]:
        if not self.tasks_path.exists():
            return []
        try:
            lines = self.tasks_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        commands: list[str] = []
        for line in lines[-limit:]:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("command"):
                commands.append(str(payload["command"]))
        return commands

    def _memory_snapshot(self) -> list[str]:
        if self.memory is None:
            return []
        try:
            entries = self.memory.recall("", limit=CONTEXT_MEMORY_LIMIT)
        except Exception:
            logger.warning("读取记忆失败", exc_info=True)
            return []
        snapshot: list[str] = []
        for entry in entries:
            if isinstance(entry, dict) and entry.get("key"):
                snapshot.append(f"{entry['key']}: {entry.get('value', '')}")
        return snapshot

    def _idle_seconds(self) -> float:
        if self.activity_since is None:
            return 0.0
        try:
            return max(0.0, time.time() - float(self.activity_since()))
        except Exception:
            return 0.0

    async def run(self, cancel: asyncio.Event | None = None) -> None:
        cancel = cancel or asyncio.Event()
        while True:
            try:
                await asyncio.wait_for(cancel.wait(), timeout=POLL_INTERVAL)
                return
            except asyncio.TimeoutError:
                pass

            if not self.config.evolution_enabled or self.client is None or self._running:
                continue
            if self._idle_seconds() < self.config.evolution_idle_seconds:
                continue
            if self.tasks_active is not None and self.tasks_active():
                continue
            now = time.time()
            if now - self._last_run < self.config.evolution_interval:
                continue

            self._running = True
            try:
                await self.evolve_once()
                self._last_run = time.time()
            except Exception:
                logger.exception("空闲进化失败")
            finally:
                self._running = False

    async def evolve_once(self) -> dict[str, Any]:
        result = await self._evolve_skills_once()
        if self.pot is not None and self.config.pot_enabled:
            try:
                await self._evolve_pot()
            except Exception:
                logger.exception("POT 反思失败")
        return result

    async def _evolve_skills_once(self) -> dict[str, Any]:
        sync_system_skills(self.source_dir, self.root)
        existing = load_skills(self.root)
        existing_names = {skill.name for skill in existing}
        evolved_count = sum(1 for skill in existing if skill.path.parent == self.root)
        if evolved_count >= self.config.evolution_max_skills:
            return {"created": False, "reason": "已达自动生成技能数量上限"}

        memory_entries = self._memory_snapshot()
        history = self._recent_history(20)
        if not memory_entries and not history:
            return {"created": False, "reason": "没有足够的记忆或任务历史"}

        payload = await self._ask_model(existing, memory_entries, history)
        if not isinstance(payload, dict) or not payload.get("create"):
            return {
                "created": False,
                "reason": str(payload.get("reason") or "模型认为无需新增技能")
                if isinstance(payload, dict)
                else "模型返回无效结果",
            }

        name = self._pick_name(str(payload.get("name") or ""), existing_names)
        description = str(payload.get("description") or "").strip()[:300] or name
        body = FRONTMATTER_RE.sub("", str(payload.get("body") or ""), count=1).strip()[:8000]
        if not body:
            return {"created": False, "reason": "模型未生成 SKILL 正文"}
        injection_reason = check_injected_content(body)
        if injection_reason is not None:
            self._log_event({"type": "reject", "name": name, "reason": injection_reason})
            return {
                "created": False,
                "reason": f"SKILL 正文疑似包含指令覆盖内容（{injection_reason}），已拒绝",
            }

        skill_dir = self.root / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        content = f"---\nname: {name}\ndescription: {description}\n---\n\n{body.strip()}\n"
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
        self._log_event(
            {
                "type": "evolve",
                "name": name,
                "description": description,
                "reason": str(payload.get("reason") or ""),
            }
        )
        await self._emit(
            {
                "type": "evolution_status",
                "created": True,
                "name": name,
                "description": description,
                "message": f"空闲进化生成了新技能：{name}",
            }
        )
        return {"created": True, "name": name, "description": description}

    def record_trace(self, entry: dict[str, Any]) -> None:
        if self.pot is not None:
            self.pot.append_trace(entry)

    async def _evolve_pot(self) -> dict[str, Any]:
        pot = self.pot
        if pot is None:
            return {"created": False, "reason": "POT 未启用"}
        traces = pot.recent_traces(20)
        if not traces:
            return {"created": False, "reason": "没有可反思的交流痕迹"}
        cot = pot.get_cot()
        rots = pot.list_rots()
        trace_text = "\n".join(
            f"- [{entry.get('time', '')}] {entry.get('command', '')}"
            f"（结果：{entry.get('result', '')}）"
            for entry in traces[-20:]
        )
        rot_text = "\n".join(f"- {rot.name}: {rot.description}" for rot in rots) or "（无）"
        prompt = (
            "## 当前 Global-COT\n"
            f"{cot or '（空）'}\n\n"
            "## 现有 ROT\n"
            f"{rot_text}\n\n"
            "## 最近交流痕迹\n"
            f"{trace_text}\n\n"
            "请反思这些痕迹，输出严格 JSON："
            '{"cot_update": string|null, "rot_create": [{"name", '
            '"description", "role", "body"}], '
            '"rot_update": [{"name", "description", "role", "body"}]}。'
            "cot_update 是通用问题解决范式的改进；rot 以某个角色视角形成思考方式。"
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 Geass 的反思器。根据交流痕迹提炼通用思维范式 COT 与"
                    "角色思考模板 ROT；信息不足时 cot_update 与数组留空。"
                ),
            },
            {"role": "user", "content": prompt},
        ]
        kwargs = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": int(self.config.pot_reflect_max_tokens),
        }
        try:
            response = await self.client.chat.completions.create(
                response_format={"type": "json_object"}, **kwargs
            )
        except Exception:
            response = await self.client.chat.completions.create(**kwargs)
        content = str(response.choices[0].message.content or "")
        payload = self._parse_pot_json(content)
        if not payload:
            return {"created": False, "reason": "反思输出无法解析"}

        cot_updated = False
        cot_update = str(payload.get("cot_update") or "").strip()
        if cot_update:
            if check_injected_content(cot_update) is None:
                pot.set_cot(cot_update[:8000])
                cot_updated = True

        rots_saved: list[str] = []
        for item in list(payload.get("rot_create") or []) + list(payload.get("rot_update") or []):
            if not isinstance(item, dict) or not item.get("name"):
                continue
            body = str(item.get("body") or "")
            if check_injected_content(body) is not None:
                continue
            rot = pot.save_rot(
                str(item["name"]),
                str(item.get("description") or ""),
                str(item.get("role") or ""),
                body,
            )
            rots_saved.append(rot.name)

        await self._emit(
            {
                "type": "pot_status",
                "cot_updated": cot_updated,
                "rots": rots_saved,
                "message": (
                    "POT 反思完成"
                    + (
                        f"：更新 COT，新增/更新 {len(rots_saved)} 个 ROT"
                        if rots_saved
                        else "：未产生新 ROT"
                    )
                ),
            }
        )
        return {
            "created": bool(cot_updated or rots_saved),
            "cot_updated": cot_updated,
            "rots": rots_saved,
        }

    @staticmethod
    def _parse_pot_json(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start < 0 or end <= start:
                return {}
            try:
                data = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                return {}
        return data if isinstance(data, dict) else {}

    async def _ask_model(
        self,
        existing: list[Skill],
        memory_entries: list[str],
        history: list[str],
    ) -> dict[str, Any]:
        catalog = (
            "\n".join(f"- {skill.name}: {skill.description}" for skill in existing) or "（无）"
        )
        if len(catalog) > CONTEXT_CATALOG_CHARS:
            catalog = catalog[:CONTEXT_CATALOG_CHARS] + "…（已裁剪）"
        memory_text = "\n".join(f"- {entry}" for entry in memory_entries) or "（无）"
        history_text = "\n".join(f"- {command}" for command in history) or "（无）"
        user_prompt = (
            "## 已有 SKILL\n"
            f"{catalog}\n\n"
            "## 用户记忆\n"
            f"{memory_text}\n\n"
            "## 最近任务\n"
            f"{history_text}\n\n"
            "请按系统要求输出 JSON。"
        )
        messages = [
            {"role": "system", "content": EVOLUTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        kwargs = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": int(self.config.evolution_max_tokens),
        }
        response = None
        try:
            response = await self.client.chat.completions.create(
                response_format={"type": "json_object"}, **kwargs
            )
        except Exception:
            response = await self.client.chat.completions.create(**kwargs)

        message = response.choices[0].message
        content = getattr(message, "content", "") or ""
        if isinstance(content, list):
            content = "".join(
                str(part.get("text", "")) if isinstance(part, dict) else str(part)
                for part in content
            )
        return _parse_json_object(str(content))

    def _pick_name(self, raw: str, existing: set[str]) -> str:
        candidate = re.sub(r"[^a-z0-9]+", "-", raw.lower().strip()).strip("-")
        if not candidate:
            candidate = "evolved-skill"
        if not NAME_RE.match(candidate):
            candidate = ("evolved-" + candidate)[:63].rstrip("-")
        if not NAME_RE.match(candidate):
            candidate = "evolved-skill"

        base = candidate
        index = 2
        while candidate in existing or (self.root / candidate).exists():
            suffix = f"-{index}"
            candidate = (base[: 63 - len(suffix)] + suffix).rstrip("-")
            index += 1
        return candidate

    def _log_event(self, payload: dict[str, Any]) -> None:
        try:
            self.evolution_dir.mkdir(parents=True, exist_ok=True)
            payload = {"time": time.time(), **payload}
            line = json.dumps(payload, ensure_ascii=False)
            with (self.evolution_dir / "history.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            logger.warning("进化事件写入失败", exc_info=True)

    async def _emit(self, message: dict[str, Any]) -> None:
        if self.status_cb is not None:
            try:
                await self.status_cb(message)
            except Exception:
                logger.warning("进化状态广播失败", exc_info=True)


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}
