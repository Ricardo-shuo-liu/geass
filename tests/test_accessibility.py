from __future__ import annotations

import sys
import types

import pytest

import geass.io.accessibility as accessibility
from geass.io.accessibility import AccessibilityError, find_elements


class FakeExtents:
    def __init__(self, x: int, y: int, w: int, h: int) -> None:
        self.x = x
        self.y = y
        self.width = w
        self.height = h


class FakeComponent:
    def __init__(self, extents: FakeExtents) -> None:
        self.extents = extents

    def getExtents(self, coord_type: int) -> FakeExtents:
        return self.extents


class FakeNode:
    def __init__(
        self,
        name: str,
        role: str,
        children: list["FakeNode"] | None = None,
        extents: FakeExtents | None = None,
    ) -> None:
        self._name = name
        self._role = role
        self._children = children or []
        self._extents = extents

    @property
    def name(self) -> str:
        return self._name

    def getRoleName(self) -> str:
        return self._role

    @property
    def childCount(self) -> int:
        return len(self._children)

    def getChildAtIndex(self, index: int) -> "FakeNode":
        return self._children[index]

    def queryComponent(self) -> FakeComponent:
        if self._extents is None:
            raise RuntimeError("no component")
        return FakeComponent(self._extents)


def install_fake_pyatspi(monkeypatch, root: FakeNode) -> None:
    registry = types.SimpleNamespace()

    def get_desktop(index: int) -> FakeNode:
        return root

    registry.getDesktop = get_desktop  # type: ignore[attr-defined]
    module = types.SimpleNamespace(Registry=registry, DESKTOP_COORDS=0)
    monkeypatch.setitem(sys.modules, "pyatspi", module)


def test_missing_pyatspi_raises_friendly_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyatspi", None)

    with pytest.raises(AccessibilityError, match="pyatspi"):
        find_elements(name="保存")


def test_gi_mismatch_falls_back_to_system_bridge(monkeypatch):
    def unavailable() -> None:
        raise AccessibilityError("gi 与 conda Python 不兼容", bridge_fallback=True)

    monkeypatch.setattr(accessibility, "_load_pyatspi", unavailable)
    monkeypatch.setattr(
        accessibility,
        "_find_via_bridge",
        lambda **kwargs: [
            {
                "name": "保存",
                "role": "push button",
                "x": 100,
                "y": 100,
                "w": 80,
                "h": 40,
            }
        ],
    )

    assert find_elements(name="保存")[0]["name"] == "保存"


def test_is_available_uses_bridge_for_gi_mismatch(monkeypatch):
    def unavailable() -> None:
        raise AccessibilityError("gi 与 conda Python 不兼容", bridge_fallback=True)

    monkeypatch.setattr(accessibility, "_load_pyatspi", unavailable)
    monkeypatch.setattr(
        accessibility,
        "_run_bridge",
        lambda payload, timeout: {"ok": True},
    )

    assert accessibility.is_available() is True


def test_finds_element_and_returns_screen_box(monkeypatch):
    save = FakeNode(
        "保存",
        "push button",
        extents=FakeExtents(100, 100, 80, 40),
    )
    root = FakeNode("", "frame", children=[save])
    install_fake_pyatspi(monkeypatch, root)

    matches = find_elements(name="保存")

    assert matches == [
        {"name": "保存", "role": "push button", "x": 100, "y": 100, "w": 80, "h": 40}
    ]


def test_role_filter_and_case_insensitive_name(monkeypatch):
    root = FakeNode(
        "",
        "frame",
        children=[
            FakeNode("File", "menu item"),
            FakeNode("保存", "push button", extents=FakeExtents(0, 0, 10, 10)),
        ],
    )
    install_fake_pyatspi(monkeypatch, root)

    assert find_elements(name="保", role="button")[0]["name"] == "保存"
    assert find_elements(name="保", role="text") == []


def test_empty_name_rejected():
    with pytest.raises(AccessibilityError, match="不能为空"):
        find_elements(name="  ")
