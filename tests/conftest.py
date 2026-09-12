from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from PIL import Image

from geass.agent import Agent
from geass.config import AgentConfig, Config
from geass.io.backend import InputBackend
from geass.screen import ScreenCapture, ScreenStreamer
from geass.server.masks import MaskManager
from geass.server.state import AppState
from geass.server.trust import TrustManager


class FakeBackend(InputBackend):
    def __init__(self, size: tuple[int, int] = (1920, 1080)) -> None:
        self.size_ = size
        self.calls: list[tuple[str, tuple, dict]] = []

    def screen_size(self) -> tuple[int, int]:
        return self.size_

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))

    def move(self, x, y, duration=None):
        self._record("move", x, y)

    def click(self, x, y, button="left"):
        self._record("click", x, y, button)

    def double_click(self, x, y):
        self._record("double_click", x, y)

    def right_click(self, x, y):
        self._record("right_click", x, y)

    def scroll(self, dx, dy):
        self._record("scroll", dx, dy)

    def drag(self, x1, y1, x2, y2):
        self._record("drag", x1, y1, x2, y2)

    def type_text(self, text):
        self._record("type_text", text)

    def key_press(self, combo):
        self._record("key_press", combo)


class FakeCapture:
    def __init__(self, jpeg: bytes = b"\xff\xd8fakejpeg\xff\xd9") -> None:
        self.jpeg = jpeg
        self.image = Image.new("RGB", (100, 80), (255, 255, 255))

    def capture_jpeg(self, max_edge: int | None = None) -> bytes:
        return self.jpeg

    def capture_image(self, max_edge: int | None = None) -> Image.Image:
        return self.image


class FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: str) -> None:
        self.id = call_id
        self.type = "function"
        self.function = SimpleNamespace(name=name, arguments=arguments)


class FakeMessage:
    def __init__(self, content: str = "", tool_calls: list | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls


class FakeChoice:
    def __init__(self, message: FakeMessage) -> None:
        self.message = message


class FakeResponse:
    def __init__(self, message: FakeMessage | None = None, content: str = "") -> None:
        if message is None:
            message = FakeMessage(content=content)
        self.choices = [FakeChoice(message)]


class FakeOpenAI:
    def __init__(self, script: list[FakeResponse]) -> None:
        self.script = list(script)
        self.requests: list[dict[str, Any]] = []

        class Completions:
            def __init__(self, parent: "FakeOpenAI") -> None:
                self.parent = parent

            async def create(self, **kwargs: Any) -> FakeResponse:
                self.parent.requests.append(kwargs)
                item = self.parent.script.pop(0)
                if isinstance(item, Exception):
                    raise item
                return item

        class Chat:
            def __init__(self, parent: "FakeOpenAI") -> None:
                self.completions = Completions(parent)

        self.chat = Chat(self)


def make_config() -> Config:
    config = Config()
    config.server.token = "test-token"
    config.agent = AgentConfig(model="gpt-test", max_steps=5, image_max_edge=1568)
    return config


def make_state(
    config: Config | None = None,
    backend: InputBackend | None = None,
    capture: ScreenCapture | None = None,
    client: Any = None,
) -> AppState:
    config = config or make_config()
    isolated = Path(tempfile.mkdtemp(prefix="geass-test-state-"))
    backend = backend or FakeBackend()
    capture = capture or FakeCapture()  # type: ignore[assignment]
    streamer = ScreenStreamer(capture, fps=15)  # type: ignore[arg-type]
    agent = Agent(
        client=client,
        backend=backend,
        capture=capture,  # type: ignore[arg-type]
        config=config.agent,
    )
    return AppState(
        config=config,
        capture=capture,  # type: ignore[arg-type]
        streamer=streamer,
        backend=backend,
        agent=agent,
        client=client,
        trust=TrustManager(isolated / "trust.json"),
        masks=MaskManager(isolated / "masks.json"),
    )
