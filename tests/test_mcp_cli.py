from __future__ import annotations

import json

import pytest

from geass.mcp import __main__ as mcp_cli
from geass.mcp.manager import MCPManager

from .test_mcp_registry import connector_for, sample_tools


def test_cli_add_list_enable_disable_remove(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GEASS_HOME", str(tmp_path))
    fail = {}
    manager = MCPManager(connector=connector_for(sample_tools(), fail))

    def fake_manager(path=None, connector=None):
        return manager

    monkeypatch.setattr(mcp_cli, "MCPManager", fake_manager)

    mcp_cli.main(["add", "demo", "--transport", "stdio", "--command", "echo", "--env", "A=1"])
    out = capsys.readouterr().out
    assert "demo" in out
    assert manager.get("demo") is not None
    assert manager.get("demo").verified is True

    mcp_cli.main(["disable", "demo"])
    assert manager.get("demo").enabled is False
    mcp_cli.main(["enable", "demo"])
    assert manager.get("demo").enabled is True

    mcp_cli.main(["disable", "demo", "add"])
    assert manager.get("demo").tools[0].enabled is False
    mcp_cli.main(["enable", "demo", "add"])
    assert manager.get("demo").tools[0].enabled is True

    mcp_cli.main(["remove", "demo", "--yes"])
    assert manager.get("demo") is None


def test_cli_failed_import_keeps_record_and_exits_nonzero(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GEASS_HOME", str(tmp_path))
    fail = {"bad": True}
    manager = MCPManager(connector=connector_for(sample_tools(), fail))
    monkeypatch.setattr(mcp_cli, "MCPManager", lambda path=None, connector=None: manager)

    with pytest.raises(SystemExit):
        mcp_cli.main(["add", "bad", "--transport", "http", "--url", "http://x/mcp"])

    assert manager.get("bad") is not None
    assert manager.get("bad").verified is False
    assert "bad" in capsys.readouterr().out

    with pytest.raises(SystemExit):
        mcp_cli.main(["enable", "bad"])


def test_cli_import_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GEASS_HOME", str(tmp_path))
    fail = {"remote": True}
    manager = MCPManager(connector=connector_for(sample_tools(), fail))
    monkeypatch.setattr(mcp_cli, "MCPManager", lambda path=None, connector=None: manager)
    config = tmp_path / "mcp.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "local": {"command": "echo", "args": ["a"], "env": {"K": "V"}},
                    "remote": {"url": "http://localhost/mcp", "headers": {"A": "B"}},
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        mcp_cli.main(["import", str(config)])

    assert manager.get("local").verified is True
    assert manager.get("local").command == "echo"
    assert manager.get("remote") is not None
    assert manager.get("remote").verified is False
