from __future__ import annotations

import pytest

from geass.io import browser
from geass.io.browser import BrowserError


def test_invalid_action_rejected():
    with pytest.raises(BrowserError):
        browser.open_page("close")


def test_linux_open_uses_xdg_open(monkeypatch):
    launched: list[list[str]] = []
    monkeypatch.setattr(browser, "platform", _platform("Linux"))
    monkeypatch.setattr(browser, "_display_ready", lambda: True)
    monkeypatch.setattr(
        browser,
        "_detached",
        lambda argv: launched.append(argv) or object(),
    )

    result = browser.open_page("open", "https://example.com")

    assert result["ok"] is True
    assert launched == [["xdg-open", "https://example.com"]]


def test_linux_new_tab_uses_installed_browser(monkeypatch):
    launched: list[list[str]] = []
    monkeypatch.setattr(browser, "platform", _platform("Linux"))
    monkeypatch.setattr(browser, "_display_ready", lambda: True)
    monkeypatch.setattr(browser, "_installed_browsers", lambda: ["firefox"])
    monkeypatch.setattr(
        browser,
        "_detached",
        lambda argv: launched.append(argv) or object(),
    )

    result = browser.open_page("new_tab", "")

    assert result["ok"] is True
    assert launched == [["firefox", "--new-tab", "about:blank"]]


def test_linux_new_tab_falls_back_to_xdg_open(monkeypatch):
    launched: list[list[str]] = []
    monkeypatch.setattr(browser, "platform", _platform("Linux"))
    monkeypatch.setattr(browser, "_display_ready", lambda: True)
    monkeypatch.setattr(browser, "_installed_browsers", lambda: [])
    monkeypatch.setattr(
        browser,
        "_detached",
        lambda argv: launched.append(argv) or object(),
    )

    result = browser.open_page("new_window", "https://example.com")

    assert result["ok"] is True
    assert launched == [["xdg-open", "https://example.com"]]


def test_linux_requires_graphical_session(monkeypatch):
    monkeypatch.setattr(browser, "platform", _platform("Linux"))
    monkeypatch.setattr(browser, "_display_ready", lambda: False)

    with pytest.raises(BrowserError, match="图形环境"):
        browser.open_page("open")


def test_macos_new_window_uses_open_n(monkeypatch):
    launched: list[list[str]] = []
    monkeypatch.setattr(browser, "platform", _platform("Darwin"))
    monkeypatch.setattr(
        browser,
        "_detached",
        lambda argv: launched.append(argv) or object(),
    )

    result = browser.open_page("new_window", "https://example.com")

    assert result["ok"] is True
    assert launched == [["open", "-n", "-u", "https://example.com"]]


def test_windows_open_uses_start(monkeypatch):
    launched: list[list[str]] = []
    monkeypatch.setattr(browser, "platform", _platform("Windows"))
    monkeypatch.setattr(
        browser,
        "_detached",
        lambda argv: launched.append(argv) or object(),
    )

    result = browser.open_page("open", "https://example.com")

    assert result["ok"] is True
    assert launched == [["cmd", "/c", "start", "", "https://example.com"]]


def _platform(name: str):
    class Platform:
        @staticmethod
        def system() -> str:
            return name

    return Platform
