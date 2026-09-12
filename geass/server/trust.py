"""可信设置：动作预览模式、可视化延迟与按工具覆盖。

数据保存在 ``~/.geass/.trust.json``（0600、原子写入），由 PWA 的“信任”面板
通过 REST 修改；``task_allow_all`` 是任务级开关，新任务开始时自动复位。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

VALID_MODES = ("smart", "confirm", "off")
DEFAULT_MODE = "smart"
DEFAULT_DELAY_MS = 600
MAX_DELAY_MS = 2000
VALID_OVERRIDES = ("auto", "confirm")
CONFIRM_TOOLS = ("open_terminal", "terminal_type", "terminal_close")
MCP_PREFIX = "mcp__"


def default_trust_path() -> Path:
    home = Path(os.environ.get("GEASS_HOME", str(Path.home())))
    return home / ".geass" / ".trust.json"


class TrustManager:
    """读写可信设置，并给出某个工具是否需要人工确认。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else default_trust_path()
        self._lock = threading.RLock()
        self._mode = DEFAULT_MODE
        self._visual_delay_ms = DEFAULT_DELAY_MS
        self._overrides: dict[str, str] = {}
        self._task_allow_all = False
        self._load()

    # ---------- 持久化 ----------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("可信设置文件损坏，已使用默认值：%s", self.path)
            return
        if not isinstance(data, dict):
            return
        mode = str(data.get("mode") or DEFAULT_MODE)
        if mode in VALID_MODES:
            self._mode = mode
        try:
            delay = int(data.get("visual_delay_ms", DEFAULT_DELAY_MS))
        except (TypeError, ValueError):
            delay = DEFAULT_DELAY_MS
        self._visual_delay_ms = max(0, min(MAX_DELAY_MS, delay))
        overrides = data.get("overrides")
        if isinstance(overrides, dict):
            self._overrides = {
                str(key): str(value)
                for key, value in overrides.items()
                if str(value) in VALID_OVERRIDES
            }
        self._task_allow_all = bool(data.get("task_allow_all", False))

    def _save(self) -> None:
        payload = self.settings()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    # ---------- 查询/更新 ----------

    def settings(self) -> dict[str, Any]:
        with self._lock:
            return {
                "mode": self._mode,
                "visual_delay_ms": self._visual_delay_ms,
                "overrides": dict(self._overrides),
                "task_allow_all": self._task_allow_all,
            }

    def update(
        self,
        *,
        mode: str | None = None,
        visual_delay_ms: int | None = None,
        overrides: dict[str, str | None] | None = None,
        task_allow_all: bool | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if mode is not None:
                value = str(mode)
                if value not in VALID_MODES:
                    raise ValueError(f"不支持的模式：{value}")
                self._mode = value
            if visual_delay_ms is not None:
                self._visual_delay_ms = max(0, min(MAX_DELAY_MS, int(visual_delay_ms)))
            if overrides is not None:
                for tool, override_value in overrides.items():
                    tool_name = str(tool).strip()
                    if not tool_name:
                        continue
                    if override_value is None:
                        self._overrides.pop(tool_name, None)
                        continue
                    override = str(override_value)
                    if override not in VALID_OVERRIDES:
                        raise ValueError(f"不支持的覆盖值：{override}")
                    self._overrides[tool_name] = override
            if task_allow_all is not None:
                self._task_allow_all = bool(task_allow_all)
            self._save()
            return self.settings()

    def begin_task(self) -> None:
        with self._lock:
            if self._task_allow_all:
                self._task_allow_all = False
                self._save()

    def override_for(self, tool: str) -> str | None:
        with self._lock:
            return self._overrides.get(str(tool))

    def requires_confirmation(
        self,
        tool: str,
        *,
        security_blocked: bool = False,
        may_execute: bool = False,
        command_present: bool = False,
    ) -> bool:
        """判断工具是否需要等待人工确认（黑名单命中无法被覆盖为自动）。"""
        name = str(tool)
        with self._lock:
            if security_blocked:
                return True
            if self._mode == "off":
                return False
            if self._mode == "confirm":
                return True
            if self._task_allow_all:
                return False
            override = self._overrides.get(name)
            if override is not None:
                return override == "confirm"
            if name == "open_terminal":
                return command_present
            if name == "terminal_type":
                return may_execute
            if name == "terminal_close":
                return True
            if name.startswith(MCP_PREFIX):
                return True
            return False

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    @property
    def visual_delay_ms(self) -> int:
        with self._lock:
            return self._visual_delay_ms
