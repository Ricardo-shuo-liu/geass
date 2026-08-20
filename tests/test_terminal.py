from __future__ import annotations

import os
import shlex
import shutil
import subprocess

import pytest

from geass.io.terminal import (
    TerminalManager,
    TerminalSession,
    TerminalError,
    _launch_visible_terminal,
    _terminal_candidates,
    clean_ansi,
    extract_output,
)
from geass.io.shell import terminal_env


def test_clean_ansi_removes_escape_sequences():
    raw = "\x1b[01;32mhello\x1b[0m world\r\nplain\n"

    assert clean_ansi(raw) == "hello world\nplain\n"


def test_extract_output_drops_echoed_command_and_sentinel():
    raw = 'echo "hello world"\r\nhello world\r\n'

    assert extract_output(raw, 'echo "hello world"') == "hello world"


def test_extract_output_handles_windows_newlines():
    raw = "ls\r\nREADME.md\r\n"

    assert extract_output(raw, "ls") == "README.md"


def test_extract_output_strips_shell_prompts():
    raw = '$ echo "hello world"\r\nhello world\r\n$ '

    assert extract_output(raw, 'echo "hello world"') == "hello world"


def test_manager_rejects_missing_session():
    manager = TerminalManager()

    result = manager.close("does-not-exist")

    assert result["ok"] is False
    assert "不存在" in result["error"]


def test_terminal_candidates_use_wait_for_gnome():
    candidates = _terminal_candidates("echo hi")

    assert candidates[0][0] == "x-terminal-emulator"
    gnome = next(argv for argv in candidates if argv[0] == "gnome-terminal")
    assert "--wait" in gnome
    assert "--" in gnome
    assert gnome[-1] == "echo hi"


def test_launch_requires_graphical_session(monkeypatch, tmp_path):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    with pytest.raises(TerminalError, match="图形环境"):
        _launch_visible_terminal(
            tmp_path / "input.fifo", tmp_path / "output.log"
        )


def test_terminal_env_strips_snap_pollution(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":1")
    monkeypatch.setenv("SNAP_NAME", "code")
    monkeypatch.setenv(
        "GTK_PATH", "/snap/code/254/usr/lib/x86_64-linux-gnu/gtk-3.0"
    )
    monkeypatch.setenv(
        "LD_LIBRARY_PATH", "/snap/core20/current/lib:/usr/local/lib"
    )
    monkeypatch.setenv("KEEP_ME", "yes")

    env = terminal_env()

    assert env["DISPLAY"] == ":1"
    assert env["KEEP_ME"] == "yes"
    assert "SNAP_NAME" not in env
    assert "GTK_PATH" not in env
    assert env["LD_LIBRARY_PATH"] == "/usr/local/lib"


def test_terminal_env_drops_pure_snap_ld_path(monkeypatch):
    monkeypatch.setenv(
        "LD_LIBRARY_PATH", "/snap/core20/current/lib:/var/lib/snapd/lib/gl"
    )

    env = terminal_env()

    assert "LD_LIBRARY_PATH" not in env


@pytest.mark.skipif(shutil.which("script") is None, reason="需要 util-linux script")
def test_session_execute_captures_output(tmp_path):
    fifo = tmp_path / "input.fifo"
    log_path = tmp_path / "output.log"
    os.mkfifo(fifo)
    read_fd = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    process = subprocess.Popen(
        ["script", "-q", "-f", str(log_path), "-c", "sh"],
        stdin=read_fd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    session = TerminalSession(
        session_id="test",
        root=tmp_path,
        fifo=fifo,
        log_path=log_path,
        process=process,
        terminal_cmd="script",
    )

    try:
        session._open_writer()
        result = session.execute('echo "hello world"', timeout=5)
        assert result["ok"] is True
        assert "hello world" in result["output"]
        assert 'echo "hello world"' not in result["output"]
    finally:
        session.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        os.close(read_fd)


@pytest.mark.skipif(
    shutil.which("script") is None or shutil.which("bash") is None,
    reason="需要 util-linux script 与 bash",
)
def test_session_execute_with_invisible_marker(tmp_path):
    fifo = tmp_path / "input.fifo"
    log_path = tmp_path / "output.log"
    marker_path = tmp_path / "command.marker"
    rcfile = tmp_path / "bashrc"
    os.mkfifo(fifo)
    rcfile.write_text(
        f"PROMPT_COMMAND='printf x >> {shlex.quote(str(marker_path))}'\n"
        "PS1='$ '\n",
        encoding="utf-8",
    )
    read_fd = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    process = subprocess.Popen(
        [
            "script",
            "-q",
            "-f",
            str(log_path),
            "-c",
            f"bash --noprofile --rcfile {shlex.quote(str(rcfile))} -i",
        ],
        stdin=read_fd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    session = TerminalSession(
        session_id="test-marker",
        root=tmp_path,
        fifo=fifo,
        log_path=log_path,
        process=process,
        terminal_cmd="script",
        marker_path=marker_path,
    )

    try:
        session._open_writer()
        result = session.execute('echo "hello world"', timeout=8)
        assert result["ok"] is True
        assert "hello world" in result["output"]
        assert "GEASS" not in result["output"]
        assert "PROMPT_COMMAND" not in result["output"]
        assert "printf x" not in result["output"]
    finally:
        session.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        os.close(read_fd)
