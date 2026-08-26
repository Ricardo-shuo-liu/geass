"""POT：反思 → 提炼 → 生成通用 COT 与一系列 ROT 模板。

- COT：解决所有问题的通用思维范式，常驻注入提示词；
- ROT：按某个角色视角形成的思考方式，类似 SKILL，按需选择 1~2 个注入；
- trace：保留交流痕迹，供空闲反思使用。
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .traces import append_trace, recent_traces

TRACE_LIMIT = 200


def default_pot_path() -> Path:
    home = Path(os.environ.get("GEASS_HOME", str(Path.home())))
    return home / ".geass" / ".pot"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^\w-]+", "-", value.strip(), flags=re.UNICODE).strip("-")
    return slug[:48].rstrip("-") or "rot"


@dataclass
class ROT:
    name: str
    description: str
    role: str
    body: str
    enabled: bool = True
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class POTStore:
    """COT/ROT/trace 的目录存储与选择。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self.root = Path(path) if path else default_pot_path()
        self.root.mkdir(parents=True, exist_ok=True)
        self.rot_dir = self.root / "rot"
        self.rot_dir.mkdir(parents=True, exist_ok=True)

    @property
    def cot_path(self) -> Path:
        return self.root / "cot.md"

    @property
    def trace_path(self) -> Path:
        return self.root / "trace.jsonl"

    def get_cot(self) -> str:
        try:
            return self.cot_path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def set_cot(self, text: str) -> None:
        tmp = self.cot_path.with_suffix(self.cot_path.suffix + ".tmp")
        tmp.write_text(text.strip() + "\n", encoding="utf-8")
        tmp.replace(self.cot_path)

    def rot_path(self, name: str) -> Path:
        return self.rot_dir / f"{_slugify(name)}.md"

    def list_rots(self, include_disabled: bool = True) -> list[ROT]:
        rots: list[ROT] = []
        for path in sorted(self.rot_dir.glob("*.md")):
            rot = self._read_rot_path(path)
            if rot is not None and (include_disabled or rot.enabled):
                rots.append(rot)
        return rots

    def _read_rot_path(self, path: Path) -> ROT | None:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return None
        body = raw
        metadata: dict[str, Any] = {}
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].splitlines():
                    if ":" in line:
                        key, value = line.split(":", 1)
                        metadata[key.strip()] = value.strip().strip("\"'")
                body = parts[2].strip()
        name = str(metadata.get("name") or path.stem)
        return ROT(
            name=name,
            description=str(metadata.get("description") or ""),
            role=str(metadata.get("role") or ""),
            body=body,
            enabled=str(metadata.get("enabled", "true")).lower() != "false",
        )

    def get_rot(self, name: str) -> ROT | None:
        path = self.rot_path(name)
        if not path.exists():
            return None
        return self._read_rot_path(path)

    def save_rot(
        self,
        name: str,
        description: str,
        role: str,
        body: str,
        enabled: bool = True,
    ) -> ROT:
        rot = ROT(
            name=_slugify(name),
            description=str(description or "").strip()[:300],
            role=str(role or "").strip()[:300],
            body=str(body or "").strip()[:8000],
            enabled=bool(enabled),
        )
        content = (
            f"---\nname: {rot.name}\n"
            f"description: {rot.description}\n"
            f"role: {rot.role}\n"
            f"enabled: {'true' if rot.enabled else 'false'}\n---\n\n"
            f"{rot.body}\n"
        )
        self.rot_path(rot.name).write_text(content, encoding="utf-8")
        return rot

    def delete_rot(self, name: str) -> bool:
        path = self.rot_path(name)
        if not path.exists():
            return False
        path.unlink()
        return True

    def set_rot_enabled(self, name: str, enabled: bool) -> bool:
        rot = self.get_rot(name)
        if rot is None:
            return False
        self.save_rot(
            rot.name,
            rot.description,
            rot.role,
            rot.body,
            enabled=enabled,
        )
        return True

    def select_rots(self, query: str, limit: int = 2) -> list[ROT]:
        """按名称/描述/角色/正文的关键词相关性选择启用中的 ROT。"""
        query = str(query or "").strip().lower()
        candidates = self.list_rots(include_disabled=False)
        if not query:
            return candidates[:limit]
        scored: list[tuple[int, ROT]] = []
        for rot in candidates:
            haystack = (
                f"{rot.name} {rot.description} {rot.role} {rot.body}"
            ).lower()
            score = haystack.count(query) * 3
            for term in query.split():
                if term in haystack:
                    score += 1
            scored.append((score, rot))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [rot for score, rot in scored[:limit] if score > 0] or candidates[:limit]

    def append_trace(self, entry: dict[str, Any]) -> None:
        append_trace(self.trace_path, entry, limit=TRACE_LIMIT)

    def recent_traces(self, limit: int = 40) -> list[dict[str, Any]]:
        return recent_traces(self.trace_path, limit=limit)
