from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import geass.dispatch as dispatch_module
import geass.main as main_module

from .conftest import make_config


def build_env(monkeypatch, *, public_url: str = ""):
    config = make_config()
    config.server.token = "server-token"
    config.server.public_url = public_url
    state = SimpleNamespace(
        mcp=None,
        capture=SimpleNamespace(monitor_count=lambda: 1),
    )
    started: dict[str, object] = {}
    monkeypatch.setattr(main_module, "load_config", lambda persist=True: config)
    monkeypatch.setattr(main_module, "build_state", lambda _config: state)
    monkeypatch.setattr(main_module, "create_app", lambda _state: object())
    monkeypatch.setattr(main_module, "lan_ips", lambda: ["192.168.1.10"])
    monkeypatch.setattr(main_module, "default_route_ip", lambda: None)
    monkeypatch.setattr(
        main_module.uvicorn,
        "run",
        lambda app, host, port, log_level: started.update({"app": app, "host": host, "port": port}),
    )
    return config, state, started


def test_serve_without_qr_keeps_manual_flow(monkeypatch, capsys):
    _config, state, started = build_env(monkeypatch)

    main_module.main([])

    output = capsys.readouterr().out
    assert "访问 Token: server-token" in output
    assert "扫码配对" not in output
    assert started["port"] == 8765
    assert not hasattr(state, "pairing")


def test_serve_with_qr_prints_lan_pairing_link(monkeypatch, capsys):
    config, state, _started = build_env(monkeypatch)

    main_module.main(["--qr"])

    output = capsys.readouterr().out
    assert "扫码配对" in output
    link_line = next(line for line in output.splitlines() if "配对链接:" in line)
    link = link_line.split("配对链接:", 1)[1].strip()
    assert link.startswith("http://192.168.1.10:8765/#pair=")
    assert config.server.token not in link
    assert state.pairing.pending_count() == 1


def test_public_url_is_used_for_qr(monkeypatch, capsys):
    _config, _state, _started = build_env(monkeypatch, public_url="https://geass.example.com/")

    main_module.main(["--qr"])

    output = capsys.readouterr().out
    link_line = next(line for line in output.splitlines() if "配对链接:" in line)
    assert link_line.split("配对链接:", 1)[1].strip().startswith("https://geass.example.com/#pair=")


def test_qr_ttl_is_validated(monkeypatch):
    build_env(monkeypatch)

    with pytest.raises(SystemExit):
        main_module.main(["--qr", "--qr-ttl", "5"])


def test_qr_ttl_is_applied(monkeypatch, capsys):
    _config, state, _started = build_env(monkeypatch)

    main_module.main(["--qr", "--qr-ttl", "60"])

    assert state.pairing.ttl == 60
    assert "60 秒内有效" in capsys.readouterr().out


def test_qr_host_override(monkeypatch, capsys):
    build_env(monkeypatch)

    main_module.main(["--qr", "--qr-host", "10.0.0.5"])

    output = capsys.readouterr().out
    link_line = next(line for line in output.splitlines() if "配对链接:" in line)
    assert link_line.split("配对链接:", 1)[1].strip().startswith("http://10.0.0.5:8765/#pair=")


def test_default_route_ip_is_preferred(monkeypatch):
    monkeypatch.setattr(main_module, "lan_ips", lambda: ["172.17.0.1", "192.168.1.10"])
    monkeypatch.setattr(main_module, "default_route_ip", lambda: "192.168.1.10")
    config = make_config()

    base, reachable = main_module.qr_base_url(config)

    assert reachable is True
    assert base == "http://192.168.1.10:8765"


def test_render_terminal_qr_returns_text():
    text = main_module.render_terminal_qr("https://example.com/#pair=abc")

    assert text
    assert "\x1b[" in text or "█" in text


def test_dispatch_passes_serve_flags(monkeypatch):
    recorded: list[list[str]] = []

    def fake_main() -> None:
        recorded.append(list(sys.argv[1:]))

    monkeypatch.setattr(main_module, "main", fake_main)

    dispatch_module.main(["serve", "--qr", "--qr-ttl", "60"])
    dispatch_module.main(["--qr"])

    assert recorded == [["--qr", "--qr-ttl", "60"], ["--qr"]]
