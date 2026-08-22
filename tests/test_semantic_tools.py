from __future__ import annotations

import asyncio

from geass.agent import Agent
from geass.config import AgentConfig
from geass.io.accessibility import AccessibilityError

from .conftest import FakeBackend, FakeCapture
from .test_agent import FakeOCR


def build_agent(ocr=FakeOCR()):
    return Agent(
        client=None,
        backend=FakeBackend(size=(1920, 1080)),
        capture=FakeCapture(),
        config=AgentConfig(model="gpt-test", image_max_edge=100),
        ocr=ocr,
    )


def test_find_text_returns_center_coordinates():
    agent = build_agent()

    result = asyncio.run(agent._execute("find_text", {"text": "hello"}))

    assert result["ok"] is True
    assert result["found"] is True
    assert result["matches"][0]["text"] == "hello"
    assert result["matches"][0]["x"] == 0.5
    assert result["matches"][0]["y"] == 0.5


def test_find_text_not_found_is_not_an_error():
    agent = build_agent()

    result = asyncio.run(agent._execute("find_text", {"text": "zzz"}))

    assert result["ok"] is True
    assert result["found"] is False
    assert result["matches"] == []


def test_find_text_exact_matching():
    agent = build_agent()

    fuzzy = asyncio.run(agent._execute("find_text", {"text": "hel"}))
    exact = asyncio.run(
        agent._execute("find_text", {"text": "hel", "exact": True})
    )

    assert fuzzy["found"] is True
    assert exact["found"] is False


def test_find_text_without_ocr_returns_error():
    agent = build_agent(ocr=None)

    result = asyncio.run(agent._execute("find_text", {"text": "hello"}))

    assert result["ok"] is False
    assert "OCR 不可用" in result["error"]


def test_find_element_normalizes_to_center(monkeypatch):
    agent = build_agent()
    monkeypatch.setattr(
        "geass.io.accessibility.find_elements",
        lambda **kwargs: [
            {
                "name": "保存",
                "role": "push button",
                "x": 100,
                "y": 200,
                "w": 80,
                "h": 40,
            }
        ],
    )

    result = asyncio.run(agent._execute("find_element", {"name": "保存"}))

    assert result["found"] is True
    assert result["matches"][0]["name"] == "保存"
    assert result["matches"][0]["x"] == round((100 + 40) / 1920, 4)
    assert result["matches"][0]["y"] == round((200 + 20) / 1080, 4)


def test_find_element_not_found(monkeypatch):
    agent = build_agent()
    monkeypatch.setattr(
        "geass.io.accessibility.find_elements", lambda **kwargs: []
    )

    result = asyncio.run(agent._execute("find_element", {"name": "不存在"}))

    assert result["ok"] is True
    assert result["found"] is False


def test_find_element_unavailable_is_reported(monkeypatch):
    agent = build_agent()

    def raise_unavailable(**kwargs):
        raise AccessibilityError("AT-SPI 不可用")

    monkeypatch.setattr(
        "geass.io.accessibility.find_elements", raise_unavailable
    )

    result = asyncio.run(agent._execute("find_element", {"name": "保存"}))

    assert result["ok"] is False
    assert "AT-SPI" in result["error"]
