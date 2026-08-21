"""进程级共享状态。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from ..agent import Agent
from ..config import Config, save_user_env
from ..io.backend import InputBackend, PyAutoGUIInputBackend
from ..io.terminal import TerminalManager
from ..ocr import PaddleOCRBackend
from ..screen import ScreenCapture, ScreenStreamer
from ..skills import load_skills
from .approval import ApprovalManager


@dataclass
class AppState:
    config: Config
    capture: ScreenCapture
    streamer: ScreenStreamer
    backend: InputBackend
    agent: Agent
    client: AsyncOpenAI | None
    terminal_manager: TerminalManager = field(default_factory=TerminalManager)
    skills: list = field(default_factory=list)
    ocr: Any = None
    approval_manager: ApprovalManager = field(default_factory=ApprovalManager)
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

    terminal_manager = TerminalManager(default_timeout=config.agent.terminal_timeout)
    skills = load_skills(config.agent.skills_dir, config.config_path)
    approval_manager = ApprovalManager(
        default_timeout=config.security.approval_timeout
    )
    ocr = (
        PaddleOCRBackend(
            token=config.agent.ocr_token,
            model=config.agent.ocr_model,
            base_url=config.agent.ocr_base_url,
            timeout=config.agent.ocr_timeout,
        )
        if config.agent.ocr
        else None
    )

    state = AppState(
        config=config,
        capture=capture,
        streamer=streamer,
        backend=backend,
        agent=None,  # type: ignore[arg-type]
        client=client,
        terminal_manager=terminal_manager,
        skills=skills,
        ocr=ocr,
        approval_manager=approval_manager,
    )
    approval_manager.broadcast = lambda message: broadcast_control(state, message)
    state.agent = Agent(
        client=client,
        backend=backend,
        capture=capture,
        config=config.agent,
        status_cb=lambda message: broadcast_control(state, message),
        vision_fallback_cb=lambda: save_user_env({"agent": {"vision": False}}),
        skills=skills,
        terminal=terminal_manager,
        ocr=ocr,
        security=config.security,
        approval_gateway=approval_manager.request,
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
    state.agent.ocr_checked = False
    state.agent.ocr_ready = False
    state.agent.ocr = (
        PaddleOCRBackend(
            token=config.agent.ocr_token,
            model=config.agent.ocr_model,
            base_url=config.agent.ocr_base_url,
            timeout=config.agent.ocr_timeout,
        )
        if config.agent.ocr
        else None
    )
    state.ocr = state.agent.ocr
    state.agent.security = config.security
    state.approval_manager.default_timeout = config.security.approval_timeout
    state.terminal_manager.default_timeout = config.agent.terminal_timeout
    state.skills = load_skills(config.agent.skills_dir, config.config_path)
    state.agent.skills = state.skills
    state.capture.max_width = config.screen.max_width
    state.capture.jpeg_quality = config.screen.jpeg_quality
    state.streamer.interval = 1.0 / max(1, config.screen.fps)
