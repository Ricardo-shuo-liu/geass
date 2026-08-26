from __future__ import annotations

import os
import subprocess
import sys


def test_cli_add_and_list(tmp_path):
    source = tmp_path / "notes"
    source.mkdir()
    (source / "a.md").write_text("打开终端的方法：按 ctrl+alt+t", encoding="utf-8")
    config = tmp_path / "config.toml"
    config.write_text(
        f'[agent]\nrag_path = "{tmp_path / ".rag"}"\n',
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["GEASS_CONFIG"] = str(config)
    env["GEASS_HOME"] = str(tmp_path / "home")

    added = subprocess.run(
        [sys.executable, "-m", "geass.rag", "add", str(source), "--name", "notes"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert added.returncode == 0, added.stderr
    assert "已锁定数据源" in added.stdout

    listed = subprocess.run(
        [sys.executable, "-m", "geass.rag", "list"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert listed.returncode == 0, listed.stderr
    assert "notes" in listed.stdout

    disabled = subprocess.run(
        [sys.executable, "-m", "geass.rag", "disable-all"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert disabled.returncode == 0, disabled.stderr
    assert "全部数据源" in disabled.stdout
