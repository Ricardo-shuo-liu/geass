"""进程级共享状态。"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from ..agent import Agent
from ..config import Config, save_user_env
from ..evolution import EvolutionEngine, POTStore
from ..io.backend import InputBackend, PyAutoGUIInputBackend
from ..io.terminal import TerminalManager
from ..memory import Memory
from ..ocr import PaddleOCRBackend
from ..rag import RAGManager
from ..rag.embeddings import provider_from_config
from ..scheduler import Scheduler, ScheduleStore
from ..screen import ScreenCapture, ScreenStreamer
from ..skills import (
    load_skills,
    resolve_skill_root,
    resolve_skills_dir,
    sync_system_skills,
)
from .approval import ApprovalManager
from .task_manager import BackgroundTaskManager


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
    skill_source_dir: Any = None
    skill_root: Any = None
    ocr: Any = None
    memory: Memory | None = None
    evolution: EvolutionEngine | None = None
    schedule_store: ScheduleStore | None = None
    scheduler: Scheduler | None = None
    rag: RAGManager | None = None
    pot: POTStore | None = None
    input_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    task_manager: BackgroundTaskManager | None = None
    last_activity: float = field(default_factory=time.time)
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
        kwargs: dict = {"api_key": config.api_key or "not-needed", "max_retries": 0}
        if config.agent.base_url:
            kwargs["base_url"] = config.agent.base_url
        client = AsyncOpenAI(**kwargs)

    terminal_manager = TerminalManager(default_timeout=config.agent.terminal_timeout)
    skill_source_dir = resolve_skills_dir(config.agent.skills_dir, config.config_path)
    skill_root = resolve_skill_root(config.agent.skill_root, config.config_path)
    sync_system_skills(skill_source_dir, skill_root)
    skills = load_skills(skill_root, config.config_path)
    approval_manager = ApprovalManager(default_timeout=config.security.approval_timeout)
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
    memory = (
        Memory(
            config.agent.memory_path or None,
            max_entries=config.agent.memory_max_entries,
        )
        if config.agent.memory_enabled
        else None
    )
    schedule_store = ScheduleStore(config.agent.schedule_path or None)
    rag = (
        RAGManager(
            config.agent.rag_path or None,
            provider=provider_from_config(config),
        )
        if config.agent.rag_enabled
        else None
    )
    pot = POTStore(config.agent.pot_path or None) if config.agent.pot_enabled else None

    state = AppState(
        config=config,
        capture=capture,
        streamer=streamer,
        backend=backend,
        agent=None,  # type: ignore[arg-type]
        client=client,
        terminal_manager=terminal_manager,
        skills=skills,
        skill_source_dir=skill_source_dir,
        skill_root=skill_root,
        ocr=ocr,
        memory=memory,
        schedule_store=schedule_store,
        rag=rag,
        pot=pot,
        approval_manager=approval_manager,
    )
    approval_manager.broadcast = lambda message: broadcast_control(state, message)
    state.task_manager = BackgroundTaskManager(
        state,
        max_tasks=config.agent.background_max_tasks,
        enabled=config.agent.background_enabled,
    )
    state.agent = make_agent(state)
    state.evolution = (
        EvolutionEngine(
            client=client,
            config=config.agent,
            memory=memory,
            skill_root=skill_root,
            source_dir=skill_source_dir,
            status_cb=lambda message: broadcast_control(state, message),
            activity_since=lambda: state.last_activity,
            pot=pot,
            tasks_active=lambda: _tasks_active(state),
        )
        if client is not None
        else None
    )
    state.scheduler = Scheduler(
        schedule_store,
        _run_scheduled_job(state),
        status_cb=lambda message: broadcast_control(state, message),
    )
    return state


def reload_state(state: AppState, config: Config) -> None:
    """用新配置更新运行中的状态（模型客户端、Agent、画面参数、Token）。"""
    state.config = config
    client = None
    if config.api_key or config.agent.base_url:
        kwargs: dict = {"api_key": config.api_key or "not-needed", "max_retries": 0}
        if config.agent.base_url:
            kwargs["base_url"] = config.agent.base_url
        client = AsyncOpenAI(**kwargs)
    state.client = client
    state.agent.client = client
    state.agent.config = config.agent
    state.agent.vision = state.agent.resolve_vision()
    state.agent.ocr_ready = False
    state.agent._ocr_last_attempt = 0.0
    state.agent._ocr_failures = 0
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
    state.memory = (
        Memory(
            config.agent.memory_path or None,
            max_entries=config.agent.memory_max_entries,
        )
        if config.agent.memory_enabled
        else None
    )
    state.agent.memory = state.memory
    state.schedule_store = ScheduleStore(config.agent.schedule_path or None)
    state.agent.schedule_store = state.schedule_store
    state.rag = (
        RAGManager(
            config.agent.rag_path or None,
            provider=provider_from_config(config),
        )
        if config.agent.rag_enabled
        else None
    )
    state.agent.rag = state.rag
    state.pot = POTStore(config.agent.pot_path or None) if config.agent.pot_enabled else None
    state.agent.pot = state.pot
    if state.evolution is not None:
        state.evolution.pot = state.pot
    if state.task_manager is not None:
        state.task_manager.max_tasks = config.agent.background_max_tasks
        state.task_manager.enabled = config.agent.background_enabled
    state.agent = make_agent(state)
    if state.scheduler is not None:
        state.scheduler.store = state.schedule_store
    else:
        state.scheduler = Scheduler(
            state.schedule_store,
            _run_scheduled_job(state),
            status_cb=lambda message: broadcast_control(state, message),
        )
    state.skill_source_dir = _resolve_source_dir(config)
    state.skill_root = resolve_skill_root(config.agent.skill_root, config.config_path)
    sync_system_skills(state.skill_source_dir, state.skill_root)
    state.skills = load_skills(state.skill_root, config.config_path)
    state.agent.skills = state.skills
    if state.evolution is None:
        state.evolution = (
            EvolutionEngine(
                client=client,
                config=config.agent,
                memory=state.memory,
                skill_root=state.skill_root,
                source_dir=state.skill_source_dir,
                status_cb=lambda message: broadcast_control(state, message),
                activity_since=lambda: state.last_activity,
                tasks_active=lambda: _tasks_active(state),
            )
            if client is not None
            else None
        )
    else:
        state.evolution.client = client
        state.evolution.config = config.agent
        state.evolution.memory = state.memory
        state.evolution.root = state.skill_root
        state.evolution.source_dir = state.skill_source_dir
    state.agent.security = config.security
    state.approval_manager.default_timeout = config.security.approval_timeout
    state.terminal_manager.default_timeout = config.agent.terminal_timeout
    state.last_activity = time.time()
    state.capture.max_width = config.screen.max_width
    state.capture.jpeg_quality = config.screen.jpeg_quality
    state.streamer.interval = 1.0 / max(1, config.screen.fps)


def _resolve_source_dir(config: Config):
    return resolve_skills_dir(config.agent.skills_dir, config.config_path)


def _run_scheduled_job(state: AppState):
    async def run_job(command: str) -> dict:
        from .ws import start_agent

        task = await start_agent(state, command)
        if task is None:
            return {
                "ok": False,
                "busy": True,
                "error": "已有任务在运行，稍后重试",
            }
        return await task

    return run_job


def make_agent(state: AppState, status_cb=None) -> Agent:
    """构造 Agent（前台或后台共用同一套依赖与输入锁）。"""
    return Agent(
        client=state.client,
        backend=state.backend,
        capture=state.capture,
        config=state.config.agent,
        status_cb=status_cb or (lambda message: broadcast_control(state, message)),
        vision_fallback_cb=lambda: save_user_env({"agent": {"vision": False}}),
        skills=state.skills,
        terminal=state.terminal_manager,
        ocr=state.ocr,
        security=state.config.security,
        approval_gateway=state.approval_manager.request,
        memory=state.memory,
        schedule_store=state.schedule_store,
        rag=state.rag,
        pot=state.pot,
        input_lock=state.input_lock,
        background_starter=(state.task_manager.start if state.task_manager is not None else None),
    )


def _tasks_active(state: AppState) -> bool:
    foreground_busy = state.agent_task is not None and not state.agent_task.done()
    background_busy = state.task_manager is not None and state.task_manager.tasks_active()
    return foreground_busy or background_busy
