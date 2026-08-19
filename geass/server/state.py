"""进程级共享状态。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from ..agent import Agent
from ..config import Config, save_user_env
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
    if config.api_key or config.agent.base_url:
        kwargs: dict = {"api_key": config.api_key or "not-needed"}
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
        vision_fallback_cb=lambda: save_user_env({"agent": {"vision": False}}),
    )
    return state


def reload_state(state: AppState, config: Config) -> None:
    """用新配置更新运行中的状态（模型客户端、Agent、画面参数、Token）。"""
    state.config = config
    client = None
    if config.api_key or config.agent.base_url:
        kwargs: dict = {"api_key": config.api_key or "not-needed"}
        if config.agent.base_url:
            kwargs["base_url"] = config.agent.base_url
        client = AsyncOpenAI(**kwargs)
    state.client = client
    state.agent.client = client
    state.agent.config = config.agent
    state.agent.vision = config.agent.vision
    state.capture.max_width = config.screen.max_width
    state.capture.jpeg_quality = config.screen.jpeg_quality
    state.streamer.interval = 1.0 / max(1, config.screen.fps)
