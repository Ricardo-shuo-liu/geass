"""敏感区域自动识别：AT-SPI 密码框 + OCR 敏感关键词。

只在用户点击“自动识别敏感区域”时运行一次，返回建议矩形（归一化坐标），
不会自动打码；是否应用由用户在信任面板决定。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from ..io.accessibility import list_sensitive_fields

logger = logging.getLogger(__name__)

DEFAULT_KEYWORDS: tuple[str, ...] = (
    "密码",
    "口令",
    "验证码",
    "校验码",
    "身份证",
    "银行卡",
    "信用卡",
    "手机号",
    "邮箱",
    "password",
    "passwd",
    "secret",
    "token",
    "api key",
    "api_key",
    "credential",
)

MAX_REGIONS = 20
KEYWORD_BAND_WIDTH = 0.32
KEYWORD_BAND_HEIGHT = 0.05


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _dedupe(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[int, int, int, int]] = set()
    result: list[dict[str, Any]] = []
    for region in regions:
        key = (
            round(float(region["x"]) * 100),
            round(float(region["y"]) * 100),
            round(float(region["w"]) * 100),
            round(float(region["h"]) * 100),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(region)
    return result


def detect_sensitive_regions(
    backend: Any,
    capture: Any,
    ocr: Any = None,
    *,
    keywords: Iterable[str] | None = None,
    use_accessibility: bool = True,
) -> dict[str, Any]:
    """返回 ``{"regions": [...], "sources": {...}, "keywords": [...]}``。"""
    try:
        width, height = backend.screen_size()
    except Exception:
        width = height = 0
    needle_list = [
        str(item).casefold()
        for item in (keywords if keywords is not None else DEFAULT_KEYWORDS)
        if str(item).strip()
    ]
    regions: list[dict[str, Any]] = []
    password_count = 0
    keyword_count = 0

    if use_accessibility:
        try:
            fields = list_sensitive_fields(limit=MAX_REGIONS, timeout=3.0)
        except Exception:
            logger.debug("AT-SPI 敏感控件识别失败", exc_info=True)
            fields = []
        for item in fields:
            if width <= 0 or height <= 0:
                continue
            try:
                x = _clamp01(float(item.get("x", 0)) / width)
                y = _clamp01(float(item.get("y", 0)) / height)
                w = _clamp01(float(item.get("w", 0)) / width)
                h = _clamp01(float(item.get("h", 0)) / height)
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            if w < 0.01 or h < 0.01 or x + w > 1.0 or y + h > 1.0:
                continue
            regions.append(
                {
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "source": "password",
                    "label": str(item.get("name") or item.get("role") or "密码输入框"),
                }
            )
            password_count += 1

    if ocr is not None and capture is not None and needle_list:
        try:
            image = capture.capture_image(1568)
            result = ocr.read(image)
        except Exception:
            logger.debug("OCR 敏感关键词识别失败", exc_info=True)
            result = None
        if result is not None and getattr(result, "ok", False):
            for box in getattr(result, "boxes", []):
                text = str(getattr(box, "text", "") or "")
                lowered = text.casefold()
                if not any(needle in lowered for needle in needle_list):
                    continue
                x0 = _clamp01(float(getattr(box, "x", 0.0)) - 0.02)
                y0 = _clamp01(float(getattr(box, "y", 0.0)) - 0.025)
                regions.append(
                    {
                        "x": x0,
                        "y": y0,
                        "w": min(1.0 - x0, KEYWORD_BAND_WIDTH),
                        "h": min(1.0 - y0, KEYWORD_BAND_HEIGHT),
                        "source": "keyword",
                        "label": text[:60],
                    }
                )
                keyword_count += 1
                if keyword_count >= MAX_REGIONS:
                    break

    deduped = _dedupe(regions)[:MAX_REGIONS]
    return {
        "regions": deduped,
        "sources": {
            "password_fields": password_count,
            "keyword_matches": keyword_count,
        },
        "keywords": needle_list,
    }
