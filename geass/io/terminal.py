"""可见终端会话管理。

目标是让 Agent 像人一样操作一个真实的、可见的终端窗口：

- `open_terminal` 弹出新窗口，可选一键执行命令并捕获输出；
- `terminal_type` 通过 FIFO 向该窗口逐字流式输入；
- `terminal_read` 读取终端自上次读取以来的新输出；
- `terminal_close` 关闭会话。

实现上，Linux 下用 `script`（或 `tee` 兜底）把终端里的 shell 接到一个
命名管道和日志文件：管道接收我们注入的按键，日志同时被终端窗口显示并
供读取，从而做到“看得到窗口、拿得到输出”。

命令结束检测默认走「不可见边带」：窗口里跑交互式 bash，`PROMPT_COMMAND`
把标记写进一个独立文件（不在终端里显示）。执行时写入命令回车后，轮询
该文件变大即认为命令完成，再回到日志里截取输出。这样窗口里只有正常的
提示符、逐字输入与输出，不会出现 `GEASS_P1=...` 之类的内部哨兵。系统
没有 bash 时才退回旧的 sentinel 方式。
"""

from __future__ import annotations

import errno
import os
import platform
import re
import secrets
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from .shell import open_terminal, terminal_env

ANSI_RE = re.compile(
    r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))|"
    r"\x1b[@-_][0-?]*[ -/]*[@-~]"
)
PROMPT_RE = re.compile(r"^\s*[$#]\s+")


class TerminalError(RuntimeError):
    """终端会话操作失败。"""


def clean_ansi(text: str) -> str:
    cleaned = ANSI_RE.sub("", text)
    return cleaned.replace("\r\n", "\n").replace("\r", "\n")


def extract_output(
    raw: str,
    command: str,
    hidden_lines: tuple[str, ...] = (),
    hidden_substrings: tuple[str, ...] = (),
) -> str:
    """从 sentinel 前的原始日志中取出命令输出。

    日志里通常会包含终端回显的命令行；把它和 sentinel 行去掉，其余
    部分作为输出返回。
    """
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    hidden = {command.strip()}
    hidden.update(line.strip() for line in hidden_lines if line.strip())
    lines = [PROMPT_RE.sub("", line).rstrip() for line in text.split("\n")]
    return "\n".join(
        line
        for line in lines
        if line
        and line not in hidden
        and not any(sub in line for sub in hidden_substrings)
        and not line.startswith("Script started")
        and not line.startswith("Script done")
    ).strip()


class TerminalSession:
    def __init__(
        self,
        session_id: str,
        root: Path,
        fifo: Path,
        log_path: Path,
        process: subprocess.Popen | None,
        terminal_cmd: str,
        marker_path: Path | None = None,
    ) -> None:
        self.id = session_id
        self.root = root
        self.fifo = fifo
        self.log_path = log_path
        self.process = process
        self.terminal_cmd = terminal_cmd
        self.marker_path = marker_path
        self.closed = False
        self._writer_fd: int | None = None
        self._read_cursor = 0
        self._lock = threading.Lock()

    @classmethod
    def start(cls) -> TerminalSession:
        root = Path(tempfile.mkdtemp(prefix="geass-term-"))
        fifo = root / "input.fifo"
        log_path = root / "output.log"
        os.mkfifo(fifo)
        session_id = secrets.token_hex(6)
        marker_path: Path | None = None
        shell_command = "sh"
        if shutil.which("bash"):
            marker_path = root / "command.marker"
            rcfile = root / "bashrc"
            rcfile.write_text(
                f"PROMPT_COMMAND='printf x >> {shlex.quote(str(marker_path))}'\nPS1='$ '\n",
                encoding="utf-8",
            )
            shell_command = f"bash --noprofile --rcfile {shlex.quote(str(rcfile))} -i"
        try:
            process, terminal_cmd = _launch_visible_terminal(fifo, log_path, shell_command)
        except Exception:
            shutil.rmtree(root, ignore_errors=True)
            raise
        session = cls(
            session_id,
            root,
            fifo,
            log_path,
            process,
            terminal_cmd,
            marker_path,
        )
        try:
            session._open_writer()
        except Exception:
            if process is not None:
                try:
                    process.terminate()
                except OSError:
                    pass
            shutil.rmtree(root, ignore_errors=True)
            raise
        return session

    def alive(self) -> bool:
        process = self.process
        return process is not None and process.poll() is None

    def _open_writer(self, timeout: float = 6.0) -> int:
        if self._writer_fd is not None:
            return self._writer_fd
        deadline = time.monotonic() + timeout
        while True:
            try:
                fd = os.open(self.fifo, os.O_WRONLY | os.O_NONBLOCK)
                self._writer_fd = fd
                return fd
            except FileNotFoundError:
                pass
            except OSError as exc:
                if exc.errno != errno.ENXIO:
                    raise TerminalError(f"无法打开终端输入通道：{exc}") from exc
            if time.monotonic() >= deadline:
                raise TerminalError("终端进程未打开输入通道")
            time.sleep(0.05)

    def _send(self, data: bytes, timeout: float = 5.0) -> None:
        if self.closed:
            raise TerminalError("终端会话已关闭")
        deadline = time.monotonic() + timeout
        while True:
            fd = self._open_writer()
            try:
                os.write(fd, data)
                return
            except OSError as exc:
                if exc.errno in (errno.ENXIO, errno.EPIPE):
                    raise TerminalError("终端输入通道已关闭（窗口可能已关闭）") from exc
                if exc.errno == errno.EAGAIN:
                    if time.monotonic() >= deadline:
                        raise TerminalError("终端输入缓冲持续已满") from exc
                    time.sleep(0.02)
                    continue
                raise TerminalError(f"写入终端失败：{exc}") from exc

    def write(self, text: str, interval: float = 0.0, press_enter: bool = False) -> int:
        """向终端写入文本；interval>0 时逐字写入，模拟人类流式输入。"""
        with self._lock:
            if interval > 0:
                for char in text:
                    self._send(char.encode("utf-8"))
                    time.sleep(interval)
            else:
                self._send(text.encode("utf-8"))
            if press_enter:
                self._send(b"\n")
        return len(text)

    def _raw_data(self) -> bytes:
        try:
            return self.log_path.read_bytes()
        except OSError:
            return b""

    def read(self) -> str:
        """读取自上次读取以来的新输出（去掉 ANSI 控制序列）。"""
        with self._lock:
            data = self._raw_data()
            chunk = data[self._read_cursor :]
            self._read_cursor = len(data)
            return clean_ansi(chunk.decode("utf-8", errors="replace"))

    def execute(self, command: str, timeout: float = 15.0) -> dict[str, Any]:
        """一键执行：写入命令并回车，等待输出结束（默认用不可见边带）。"""
        if self.marker_path is not None:
            return self._execute_with_marker(command, timeout)
        return self._execute_with_sentinel(command, timeout)

    def _marker_size(self) -> int:
        if self.marker_path is None:
            return 0
        try:
            return self.marker_path.stat().st_size
        except OSError:
            return 0

    def _execute_with_marker(self, command: str, timeout: float) -> dict[str, Any]:
        """bash + PROMPT_COMMAND 边带：窗口里不出现任何内部哨兵。"""
        with self._lock:
            deadline = time.monotonic() + timeout
            # 先等 shell 打出首个提示符（首个 PROMPT_COMMAND 写入边带），
            # 避免把启动提示误判为命令完成。
            while self._marker_size() == 0:
                if time.monotonic() >= deadline or not self.alive():
                    self._read_cursor = len(self._raw_data())
                    return {
                        "ok": False,
                        "output": "",
                        "session_id": self.id,
                        "message": (
                            "终端会话已退出"
                            if not self.alive()
                            else f"终端 shell 未就绪（等待提示符超时 {timeout:.0f}s）"
                        ),
                    }
                time.sleep(0.05)
            initial = self._marker_size()
            started = len(self._raw_data())
            self._send(command.encode("utf-8"))
            self._send(b"\n")
            deadline = time.monotonic() + timeout
            while True:
                if self._marker_size() > initial:
                    self._read_cursor = len(self._raw_data())
                    output = extract_output(
                        clean_ansi(self._raw_data()[started:].decode("utf-8", errors="replace")),
                        command,
                    )
                    return {
                        "ok": True,
                        "output": output,
                        "session_id": self.id,
                        "message": "命令执行完成",
                    }
                if time.monotonic() >= deadline:
                    self._read_cursor = len(self._raw_data())
                    output = extract_output(
                        clean_ansi(self._raw_data()[started:].decode("utf-8", errors="replace")),
                        command,
                    )
                    return {
                        "ok": False,
                        "output": output,
                        "session_id": self.id,
                        "message": (
                            "终端会话已退出"
                            if not self.alive()
                            else f"等待输出超时（{timeout:.0f}s）"
                        ),
                    }
                time.sleep(0.05)

    def _execute_with_sentinel(self, command: str, timeout: float) -> dict[str, Any]:
        """无 bash 时的兜底：用唯一 sentinel 检测命令结束。"""
        marker = f"__GEASS_DONE_{secrets.token_hex(6)}__"
        middle = len(marker) // 2
        part1, part2 = marker[:middle], marker[middle:]
        sentinel_command = (
            f"GEASS_P1='{part1}'; GEASS_P2='{part2}'; printf '%s%s\\n' \"$GEASS_P1\" \"$GEASS_P2\""
        )
        with self._lock:
            started = len(self._raw_data())
            self._send(command.encode("utf-8"))
            self._send(b"\n")
            self._send((sentinel_command + "\n").encode("utf-8"))
            deadline = time.monotonic() + timeout
            while True:
                data = self._raw_data()
                region = data[started:]
                marker_bytes = marker.encode("utf-8")
                found = region.find(marker_bytes)
                if found != -1:
                    end = found + len(marker_bytes)
                    tail = region[end:]
                    newline = tail.find(b"\n")
                    if newline != -1:
                        end += newline + 1
                    else:
                        end = len(region)
                    self._read_cursor = started + end
                    output = extract_output(
                        clean_ansi(region[:found].decode("utf-8", errors="replace")),
                        command,
                        (sentinel_command,),
                        ("GEASS_P1=", "GEASS_P2="),
                    )
                    return {
                        "ok": True,
                        "output": output,
                        "session_id": self.id,
                        "message": "命令执行完成",
                    }
                if time.monotonic() >= deadline:
                    self._read_cursor = len(data)
                    output = extract_output(
                        clean_ansi(region.decode("utf-8", errors="replace")),
                        command,
                        (sentinel_command,),
                        ("GEASS_P1=", "GEASS_P2="),
                    )
                    return {
                        "ok": False,
                        "output": output,
                        "session_id": self.id,
                        "message": (
                            "终端会话已退出"
                            if not self.alive()
                            else f"等待输出超时（{timeout:.0f}s）"
                        ),
                    }
                time.sleep(0.05)

    def close(self) -> None:
        if self.closed:
            return
        try:
            self.write("exit\n")
        except TerminalError:
            pass
        self.closed = True
        if self._writer_fd is not None:
            try:
                os.close(self._writer_fd)
            except OSError:
                pass
            self._writer_fd = None


def _launch_visible_terminal(
    fifo: Path, log_path: Path, shell_command: str = "sh"
) -> tuple[subprocess.Popen, str]:
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        raise TerminalError(
            "当前会话没有图形环境（DISPLAY/WAYLAND_DISPLAY 未设置），无法打开可见的终端窗口"
        )

    env = terminal_env()

    if shutil.which("script"):
        run_line = (
            f"exec script -q -f {shlex.quote(str(log_path))}"
            f" -c {shlex.quote(shell_command)}"
            f" < {shlex.quote(str(fifo))}"
        )
    else:
        run_line = (
            f"exec {shell_command} < {shlex.quote(str(fifo))} 2>&1 |"
            f" tee {shlex.quote(str(log_path))}"
        )

    last_error = ""
    for index, argv in enumerate(_terminal_candidates(run_line)):
        err_path = log_path.with_name(f"launch-{index}.err")
        try:
            with err_path.open("wb") as err_handle:
                process = subprocess.Popen(
                    argv,
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=err_handle,
                    env=env,
                )
        except FileNotFoundError:
            last_error = f"{argv[0]}（未安装）"
            continue
        except OSError as exc:
            last_error = f"{argv[0]} 启动失败：{exc}"
            continue
        time.sleep(0.4)
        code = process.poll()
        if code is None or code == 0:
            return process, argv[0]
        detail = ""
        try:
            lines = [line.strip() for line in err_path.read_text(errors="replace").splitlines()]
            detail = next((line for line in reversed(lines) if line), "")
        except OSError:
            pass
        last_error = f"{argv[0]} 启动后立即退出（退出码 {code}）"
        if detail:
            last_error += f"：{detail}"
    raise TerminalError(f"无法打开可见的终端窗口：{last_error}")


def _terminal_candidates(run_line: str) -> list[list[str]]:
    """按桌面环境常用程度排列的终端启动命令。

    首选 `x-terminal-emulator`（Debian/Ubuntu 的 alternatives 包装器会为
    gnome-terminal 自动附加 `--wait`，避免 dbus 激活导致客户端立即退出）；
    直接调 gnome-terminal 时也显式加 `--wait`，使进程存活到窗口关闭。
    """
    return [
        ["x-terminal-emulator", "-e", "sh", "-c", run_line],
        ["gnome-terminal", "--wait", "--", "sh", "-c", run_line],
        ["konsole", "-e", "sh", "-c", run_line],
        ["xfce4-terminal", "-x", "sh", "-c", run_line],
        ["mate-terminal", "--", "sh", "-c", run_line],
        ["xterm", "-e", "sh", "-c", run_line],
        ["wezterm", "start", "--", "sh", "-c", run_line],
        ["alacritty", "-e", "sh", "-c", run_line],
        ["kitty", "sh", "-c", run_line],
    ]


class TerminalManager:
    """进程内终端会话注册表。"""

    def __init__(self, default_timeout: float = 15.0) -> None:
        self.default_timeout = default_timeout
        self._sessions: dict[str, TerminalSession] = {}
        self._order: list[str] = []

    def open(self, command: str = "") -> dict[str, Any]:
        if platform.system() != "Linux":
            result = open_terminal(command)
            if result.get("ok"):
                result["session_id"] = None
                result["output"] = ""
            return result

        session = TerminalSession.start()
        self._sessions[session.id] = session
        self._order.append(session.id)
        message = "已打开新的可见终端窗口"
        output = ""
        ok = True
        if command.strip():
            result = session.execute(command, self.default_timeout)
            message = f"已在新的可见终端窗口执行：{command}"
            output = result.get("output", "")
            if not result.get("ok"):
                message = result.get("message", message)
                ok = False
        return {
            "ok": ok,
            "message": message,
            "session_id": session.id,
            "output": output,
        }

    def get(self, session_id: str | None) -> TerminalSession:
        if session_id is None:
            for sid in reversed(self._order):
                session = self._sessions.get(sid)
                if session is not None and not session.closed:
                    return session
            raise TerminalError("当前没有打开的终端会话")
        session = self._sessions.get(str(session_id))
        if session is None or session.closed:
            raise TerminalError(f"终端会话不存在或已关闭：{session_id}")
        return session

    def close(self, session_id: str | None) -> dict[str, Any]:
        try:
            session = self.get(session_id)
        except TerminalError as exc:
            return {"ok": False, "error": str(exc)}
        session.close()
        return {"ok": True, "message": f"已关闭终端会话 {session.id}"}

    def close_all(self) -> None:
        for session in list(self._sessions.values()):
            try:
                session.close()
            except Exception:
                continue
