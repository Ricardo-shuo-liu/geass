"""持久记忆：让 Agent 跨任务保存与检索用户偏好、环境事实等信息。

记忆目录默认位于 ``~/.geass/.memory``（与 ``~/.geass/env.toml`` 同级），
条目保存在其中的 ``entries.json``。写入采用临时文件 + 原子替换，多个进程
同时写时以最后一次替换为准，足够当前"同时只跑一个任务"的使用场景。
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_KEY_LENGTH = 200
MAX_VALUE_LENGTH = 8000


def default_memory_path() -> Path:
    home = Path(os.environ.get("GEASS_HOME", str(Path.home())))
    return home / ".geass" / ".memory"


@dataclass
class MemoryEntry:
    key: str
    value: str
    id: str
    created_at: float
    updated_at: float

    def to_dict(self) -> dict:
        return asdict(self)


class Memory:
    """基于目录中 ``entries.json`` 的简单键值记忆，键大小写不敏感。"""

    def __init__(
        self,
        path: str | Path | None = None,
        max_entries: int = 200,
    ) -> None:
        self.dir = Path(path) if path else default_memory_path()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.entries_path = self.dir / "entries.json"
        self.max_entries = max(1, int(max_entries))
        self._lock = threading.RLock()
        self._entries: dict[str, MemoryEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.entries_path.exists():
            return
        try:
            data = json.loads(self.entries_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("记忆文件读取失败，将使用空记忆：%s", exc)
            return

        raw = data.get("entries") if isinstance(data, dict) else data
        if not isinstance(raw, list):
            return
        now = time.time()
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            value = str(item.get("value") or "")
            if not key:
                continue
            created = self._as_float(item.get("created_at"), now)
            entry = MemoryEntry(
                key=key,
                value=value,
                id=str(item.get("id") or uuid.uuid4().hex),
                created_at=created,
                updated_at=self._as_float(item.get("updated_at"), created),
            )
            self._entries[key.casefold()] = entry
        self._trim()

    @staticmethod
    def _as_float(value, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    def _save(self) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "entries": [entry.to_dict() for entry in self._sorted()],
            }
            tmp = self.entries_path.with_suffix(
                self.entries_path.suffix + ".tmp"
            )
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, self.entries_path)
        except OSError as exc:
            logger.warning("记忆写入失败：%s", exc)

    def _sorted(self) -> list[MemoryEntry]:
        return sorted(
            self._entries.values(),
            key=lambda entry: (entry.updated_at, entry.key.casefold()),
            reverse=True,
        )

    def _trim(self) -> None:
        while len(self._entries) > self.max_entries:
            oldest = min(
                self._entries.values(), key=lambda entry: entry.updated_at
            )
            self._entries.pop(oldest.key.casefold(), None)

    def remember(self, key: str, value: str) -> MemoryEntry:
        key = str(key or "").strip()[:MAX_KEY_LENGTH]
        value = str(value or "").strip()[:MAX_VALUE_LENGTH]
        if not key:
            raise ValueError("记忆的 key 不能为空")
        if not value:
            raise ValueError("记忆的 value 不能为空")

        now = time.time()
        with self._lock:
            existing = self._entries.get(key.casefold())
            if existing is not None:
                existing.value = value
                existing.updated_at = now
                entry = existing
            else:
                entry = MemoryEntry(
                    key=key,
                    value=value,
                    id=uuid.uuid4().hex,
                    created_at=now,
                    updated_at=now,
                )
                self._entries[key.casefold()] = entry
                self._trim()
            self._save()
        return entry

    def forget(self, key: str) -> bool:
        key = str(key or "").strip()
        with self._lock:
            entry = self._entries.pop(key.casefold(), None)
            if entry is None:
                return False
            self._save()
        return True

    def recall(self, query: str = "", limit: int = 10) -> list[dict]:
        """按关键字检索记忆；空查询返回最近更新的条目。"""
        query = str(query or "").strip()
        limit = max(1, min(int(limit), 50))
        with self._lock:
            entries = self._sorted()

        if not query:
            return [entry.to_dict() for entry in entries[:limit]]

        tokens = [token for token in re.split(r"\W+", query.casefold()) if token]
        needle = query.casefold()
        scored: list[tuple[int, float, MemoryEntry]] = []
        for entry in entries:
            key = entry.key.casefold()
            value = entry.value.casefold()
            score = 0
            if needle in key:
                score += 3
            if needle in value:
                score += 1
            for token in tokens:
                if token in key:
                    score += 2
                elif token in value:
                    score += 1
            if score > 0:
                scored.append((score, entry.updated_at, entry))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [entry.to_dict() for _, _, entry in scored[:limit]]

    def recent(self, limit: int = 8) -> list[MemoryEntry]:
        limit = max(1, min(int(limit), 50))
        with self._lock:
            return self._sorted()[:limit]

    def context_for(
        self,
        text: str = "",
        limit: int = 8,
        max_chars: int = 1800,
    ) -> str:
        """生成注入系统提示的紧凑记忆上下文（优先匹配当前命令）。"""
        matched = self.recall(text, limit=limit)
        if not matched:
            matched = [entry.to_dict() for entry in self.recent(limit)]

        lines: list[str] = []
        used = 0
        for item in matched:
            line = f"- {item['key']}: {item['value']}"
            if used + len(line) > max_chars:
                break
            lines.append(line)
            used += len(line)
        return "\n".join(lines)
