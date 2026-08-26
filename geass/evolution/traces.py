"""POT 反思所需的交流痕迹保留（jsonl 追加/裁剪/读取）。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def append_trace(path: Path, entry: dict[str, Any], limit: int = 200) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        trim_traces(path, limit)
    except OSError:
        logger.warning("POT trace 写入失败", exc_info=True)


def trim_traces(path: Path, limit: int) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= limit:
        return
    try:
        path.write_text(
            "\n".join(lines[-limit:]) + "\n", encoding="utf-8"
        )
    except OSError:
        logger.warning("POT trace 裁剪失败", exc_info=True)


def recent_traces(path: Path, limit: int = 40) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            entries.append(payload)
    return entries
