"""CLI 终端界面：优先 Rich 面板，缺失时回退 ANSI 简易 REPL。"""

from __future__ import annotations

try:
    from rich.console import Console
    from rich.panel import Panel

    HAVE_RICH = True
except ImportError:
    HAVE_RICH = False

SLASH_COMMANDS = [
    "/help",
    "/mode",
    "/deliberate",
    "/light",
    "/rot list",
    "/rot use ",
    "/skill list",
    "/skill read ",
    "/rag search ",
    "/mcp list",
    "/cot show",
    "/clear",
    "/exit",
]


class TUI:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.mode = "light"
        self.rot_names: list[str] = []
        self.model = ""
        self._console = Console() if HAVE_RICH else None
        self._readline_ready = False

    def _ensure_readline(self) -> None:
        if self._readline_ready:
            return
        self._readline_ready = True
        try:
            import readline

            def completer(text: str, state: int):
                candidates = [command for command in SLASH_COMMANDS if command.startswith(text)]
                return candidates[state] if state < len(candidates) else None

            readline.set_completer(completer)
            readline.set_completer_delims("")
            readline.parse_and_bind("tab: complete")
        except ImportError:
            pass

    def _status_text(self) -> str:
        rots = ", ".join(self.rot_names) or "自动选择"
        return (
            f"模式: {'Delib' if self.mode == 'deliberate' else 'light'} · "
            f"模型: {self.model or '-'} · ROT: {rots}"
        )

    def render_header(self) -> None:
        if self._console is not None:
            self._console.print(Panel(self._status_text(), title="Geass CIL", border_style="cyan"))
        else:
            print(f"[CIL] {self._status_text()}")

    def say(self, role: str, text: str) -> None:
        self.messages.append((role, text))
        if self._console is not None:
            self._console.print(f"[bold cyan]{role}[/bold cyan] {text}")
        else:
            print(f"{role}: {text}")

    def ask(self, prompt: str = "") -> str:
        self._ensure_readline()
        prefix = "Delib> " if self.mode == "deliberate" else "light> "
        try:
            return input(prefix + prompt)
        except (EOFError, KeyboardInterrupt):
            return "/exit"

    def confirm(self, text: str) -> bool:
        try:
            return input(f"{text} [y/N] ").strip().lower() in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    def clear(self) -> None:
        self.messages.clear()

    def update_status(self, mode: str, rot_names: list[str] | None = None, model: str = "") -> None:
        self.mode = mode
        if rot_names is not None:
            self.rot_names = rot_names
        if model:
            self.model = model
