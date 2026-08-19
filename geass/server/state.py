"""进程级共享状态。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from ..agent import Agent
from ..config import Config
from ..io.backend import InputBackend, PyAutoGUIInputBackend
from ..screen import ScreenCapture, ScreenStreamer


@dataclass
class AppState:
    config: Config
    capture: ScreenCapture
    streamer: ScreenStreamer
    backend: InputBackend
    agent: Agent
    client: AsyncOpenAI | None
    control_clients: set = field(default_factory=set)
    agent_task: asyncio.Task | None = None
    cancel_event: asyncio.Event | None = None


async def broadcast_control(state: AppState, message: dict[str, Any]) -> None:
    for ws in list(state.control_clients):
        try:
            await ws.send_json(message)
        except Exception:
            state.control_clients.discard(ws)


def build_state(config: Config) -> AppState:
    capture = ScreenCapture(
        max_width=config.screen.max_width, jpeg_quality=config.screen.jpeg_quality
    )
    streamer = ScreenStreamer(capture, fps=config.screen.fps)
    backend = PyAutoGUIInputBackend()
    client = None
    if config.openai_api_key or config.agent.base_url:
        kwargs: dict = {"api_key": config.openai_api_key or "not-needed"}
        if config.agent.base_url:
            kwargs["base_url"] = config.agent.base_url
        client = AsyncOpenAI(**kwargs)

    state = AppState(
        config=config,
        capture=capture,
        streamer=streamer,
        backend=backend,
        agent=None,  # type: ignore[arg-type]
        client=client,
    )
    state.agent = Agent(
        client=client,
        backend=backend,
        capture=capture,
        config=config.agent,
        status_cb=lambda message: broadcast_control(state, message),
    )
    return state
