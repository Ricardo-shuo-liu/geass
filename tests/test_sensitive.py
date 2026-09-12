from __future__ import annotations

from types import SimpleNamespace

import geass.server.sensitive as sensitive_module
from geass.ocr import OCRBox, OCRResult
from geass.server.sensitive import detect_sensitive_regions


class FakeBackend:
    def screen_size(self) -> tuple[int, int]:
        return (1000, 500)


class FakeCapture:
    def capture_image(self, max_edge: int | None = None):
        return SimpleNamespace(size=(1000, 500))


class FakeOCR:
    def read(self, image) -> OCRResult:
        return OCRResult(
            ok=True,
            boxes=[
                OCRBox(text="密码", confidence=0.9, x=0.2, y=0.3),
                OCRBox(text="登录", confidence=0.9, x=0.5, y=0.6),
            ],
        )


def test_detects_password_fields_and_keywords(monkeypatch):
    monkeypatch.setattr(
        sensitive_module,
        "list_sensitive_fields",
        lambda limit=10, timeout=3.0: [
            {"name": "", "role": "password text", "x": 100, "y": 50, "w": 300, "h": 40}
        ],
    )

    result = detect_sensitive_regions(FakeBackend(), FakeCapture(), FakeOCR())

    sources = result["sources"]
    assert sources["password_fields"] == 1
    assert sources["keyword_matches"] == 1
    regions = result["regions"]
    assert len(regions) == 2
    password = next(item for item in regions if item["source"] == "password")
    assert password["x"] == 0.1
    assert password["w"] == 0.3
    keyword = next(item for item in regions if item["source"] == "keyword")
    assert keyword["label"] == "密码"


def test_detection_skips_missing_sources(monkeypatch):
    monkeypatch.setattr(
        sensitive_module,
        "list_sensitive_fields",
        lambda **_: [],
    )

    result = detect_sensitive_regions(FakeBackend(), None, None)

    assert result["regions"] == []
    assert result["sources"] == {"password_fields": 0, "keyword_matches": 0}


def test_detection_handles_accessibility_failure(monkeypatch):
    def boom(**_: object):
        raise RuntimeError("no at-spi")

    monkeypatch.setattr(sensitive_module, "list_sensitive_fields", boom)

    result = detect_sensitive_regions(FakeBackend(), None, None)

    assert result["regions"] == []
