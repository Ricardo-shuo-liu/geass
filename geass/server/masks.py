"""隐私遮罩：归一化矩形，默认关闭，启用后对截图统一填黑。

数据保存在 ``~/.geass/.masks.json``（0600、原子写入）。遮罩只覆盖主屏，
不阻止输入；交互拦截由动作预览负责。
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

STORE_VERSION = 1
MAX_MASKS = 20
MIN_SIZE = 0.01


def default_masks_path() -> Path:
    home = Path(os.environ.get("GEASS_HOME", str(Path.home())))
    return home / ".geass" / ".masks.json"


def _clamp(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, float(value)))


class MaskManager:
    """线程安全的遮罩表；``apply()`` 在截图线程里被调用。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else default_masks_path()
        self._lock = threading.RLock()
        self._enabled = False
        self._masks: list[dict[str, Any]] = []
        self._load()

    # ---------- 持久化 ----------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("遮罩文件损坏，已忽略：%s", self.path)
            return
        if not isinstance(data, dict):
            return
        self._enabled = bool(data.get("enabled", False))
        masks = data.get("masks")
        if not isinstance(masks, list):
            return
        parsed: list[dict[str, Any]] = []
        for item in masks[:MAX_MASKS]:
            if not isinstance(item, dict):
                continue
            try:
                rect = self._normalize(item)
            except (TypeError, ValueError):
                continue
            rect["id"] = str(item.get("id") or secrets.token_hex(4))
            parsed.append(rect)
        self._masks = parsed

    def _save(self) -> None:
        payload = {
            "version": STORE_VERSION,
            "enabled": self._enabled,
            "masks": self._masks,
        }
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

    @staticmethod
    def _normalize(rect: dict[str, Any]) -> dict[str, Any]:
        x = _clamp(rect.get("x", 0.0))
        y = _clamp(rect.get("y", 0.0))
        width = _clamp(rect.get("w", 0.0))
        height = _clamp(rect.get("h", 0.0))
        if x + width > 1.0:
            width = 1.0 - x
        if y + height > 1.0:
            height = 1.0 - y
        if width < MIN_SIZE or height < MIN_SIZE:
            raise ValueError("遮罩区域过小")
        return {"x": x, "y": y, "w": width, "h": height}

    # ---------- 查询/修改 ----------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"enabled": self._enabled, "masks": [dict(item) for item in self._masks]}

    def add(self, rect: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if len(self._masks) >= MAX_MASKS:
                raise ValueError(f"遮罩数量已达上限（{MAX_MASKS}）")
            normalized = self._normalize(rect)
            normalized["id"] = secrets.token_hex(4)
            self._masks.append(normalized)
            self._enabled = True
            self._save()
            return dict(normalized)

    def remove(self, mask_id: str) -> bool:
        with self._lock:
            target = str(mask_id)
            remaining = [item for item in self._masks if item.get("id") != target]
            if len(remaining) == len(self._masks):
                return False
            self._masks = remaining
            self._save()
            return True

    def set_enabled(self, enabled: bool) -> bool:
        with self._lock:
            self._enabled = bool(enabled)
            self._save()
            return self._enabled

    def clear(self) -> int:
        with self._lock:
            removed = len(self._masks)
            self._masks = []
            self._save()
            return removed

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def apply(self, image: Image.Image) -> Image.Image:
        """按归一化坐标把遮罩区域填黑；关闭或无遮罩时原样返回。"""
        with self._lock:
            if not self._enabled or not self._masks:
                return image
            masks = [dict(item) for item in self._masks]
        width, height = image.size
        if width <= 0 or height <= 0:
            return image
        draw = ImageDraw.Draw(image)
        for mask in masks:
            x0 = int(round(float(mask["x"]) * width))
            y0 = int(round(float(mask["y"]) * height))
            x1 = int(round((float(mask["x"]) + float(mask["w"])) * width))
            y1 = int(round((float(mask["y"]) + float(mask["h"])) * height))
            draw.rectangle([x0, y0, max(x0, x1 - 1), max(y0, y1 - 1)], fill=(0, 0, 0))
        return image
