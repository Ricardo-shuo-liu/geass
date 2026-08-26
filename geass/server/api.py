"""REST 接口：健康检查、信息、配置、语音兜底转写、停止 Agent。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from ..config import load_config, mask_secret, save_user_env
from ..memory import default_memory_path
from ..safety import default_patterns
from ..skills import resolve_skill_root
from .auth import require_token
from .state import reload_state


class ConfigUpdate(BaseModel):
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    vision: bool | None = None
    ocr: bool | None = None
    ocr_token: str | None = None
    ocr_model: str | None = None
    ocr_base_url: str | None = None
    vision_whitelist: str | None = None
    memory_enabled: bool | None = None
    memory_path: str | None = None
    skill_root: str | None = None
    evolution_enabled: bool | None = None
    security_enabled: bool | None = None
    approval_timeout: float | None = None


class ScheduleAdd(BaseModel):
    command: str
    run_at: float
    persistent: bool = True


def config_summary(state) -> dict[str, Any]:
    return {
        "model": state.config.agent.model,
        "base_url": state.config.agent.base_url or "",
        "vision": state.config.agent.vision,
        "ocr": state.config.agent.ocr,
        "ocr_model": state.config.agent.ocr_model,
        "ocr_base_url": state.config.agent.ocr_base_url,
        "ocr_token": mask_secret(state.config.agent.ocr_token),
        "ocr_configured": bool(state.config.agent.ocr_token),
        "skills_dir": state.config.agent.skills_dir,
        "skill_root": state.config.agent.skill_root
        or str(resolve_skill_root(None)),
        "evolution_enabled": state.config.agent.evolution_enabled,
        "evolution_idle_seconds": state.config.agent.evolution_idle_seconds,
        "evolution_interval": state.config.agent.evolution_interval,
        "evolution_max_skills": state.config.agent.evolution_max_skills,
        "memory_enabled": state.config.agent.memory_enabled,
        "memory_path": state.config.agent.memory_path
        or str(default_memory_path()),
        "memory_max_entries": state.config.agent.memory_max_entries,
        "api_key": mask_secret(state.config.api_key),
        "api_configured": bool(state.client),
        "voice_fallback_model": state.config.voice.fallback_model,
        "vision_whitelist": list(state.config.agent.vision_whitelist),
        "security_enabled": state.config.security.enabled,
        "security_approval_timeout": state.config.security.approval_timeout,
        "security_patterns_count": len(
            state.config.security.patterns or default_patterns()
        ),
    }


def register(app) -> None:
    router = APIRouter()

    @router.get("/api/health")
    async def health():
        return {"ok": True, "service": "geass"}

    @router.get("/api/info", dependencies=[Depends(require_token)])
    async def info(request: Request):
        state = request.app.state.geass
        try:
            screen_size = state.backend.screen_size()
        except Exception:
            screen_size = None
        return {
            "version": "0.1.0",
            "model": state.config.agent.model,
            "base_url": state.config.agent.base_url or "（OpenAI 默认）",
            "vision": state.config.agent.vision,
            "screen_size": screen_size,
            "agent_busy": bool(state.agent_task and not state.agent_task.done()),
            "api_configured": state.client is not None,
        }

    @router.get("/api/config", dependencies=[Depends(require_token)])
    async def get_config(request: Request):
        return config_summary(request.app.state.geass)

    @router.post("/api/config", dependencies=[Depends(require_token)])
    async def update_config(request: Request, payload: ConfigUpdate):
        state = request.app.state.geass
        updates: dict[str, dict[str, Any]] = {"agent": {}, "security": {}}
        for key in ("model", "base_url", "api_key"):
            value = getattr(payload, key)
            if value:
                updates["agent"][key] = value
        for key in ("ocr_token", "ocr_model", "ocr_base_url"):
            value = getattr(payload, key)
            if value:
                updates["agent"][key] = value
        if payload.vision is not None:
            updates["agent"]["vision"] = payload.vision
        if payload.ocr is not None:
            updates["agent"]["ocr"] = payload.ocr
        if payload.vision_whitelist is not None:
            updates["agent"]["vision_whitelist"] = [
                item.strip()
                for item in payload.vision_whitelist.split(",")
                if item.strip()
            ]
        if payload.memory_enabled is not None:
            updates["agent"]["memory_enabled"] = payload.memory_enabled
        if payload.memory_path is not None:
            updates["agent"]["memory_path"] = payload.memory_path.strip()
        if payload.skill_root is not None:
            updates["agent"]["skill_root"] = payload.skill_root.strip()
        if payload.evolution_enabled is not None:
            updates["agent"]["evolution_enabled"] = payload.evolution_enabled
        if payload.security_enabled is not None:
            updates["security"]["enabled"] = payload.security_enabled
        if payload.approval_timeout is not None:
            updates["security"]["approval_timeout"] = max(
                5.0, float(payload.approval_timeout)
            )
        if not updates["agent"] and not updates["security"]:
            raise HTTPException(status_code=400, detail="没有可更新的字段")

        save_user_env(updates)
        new_config = load_config(state.config.config_path, persist=False)
        reload_state(state, new_config)
        return config_summary(state)

    @router.post("/api/transcribe", dependencies=[Depends(require_token)])
    async def transcribe(request: Request, file: UploadFile = File(...)):
        state = request.app.state.geass
        if state.client is None:
            raise HTTPException(status_code=503, detail="未配置 API Key，无法转写")
        if not state.config.voice.fallback_model:
            raise HTTPException(
                status_code=503, detail="语音兜底转写已禁用（fallback_model 为空）"
            )

        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="音频为空")

        filename = file.filename or "audio.webm"
        content_type = file.content_type or "audio/webm"

        try:
            result = await state.client.audio.transcriptions.create(
                model=state.config.voice.fallback_model,
                file=(filename, data, content_type),
            )
            text = result.text
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"转写失败：{exc}")
        return {"text": text}

    @router.post("/api/agent/stop", dependencies=[Depends(require_token)])
    async def stop_agent(request: Request):
        state = request.app.state.geass
        if state.cancel_event is not None:
            state.cancel_event.set()
        return {"ok": True}

    @router.get("/api/schedule", dependencies=[Depends(require_token)])
    async def list_schedule(request: Request):
        state = request.app.state.geass
        if state.schedule_store is None:
            raise HTTPException(status_code=503, detail="定时系统不可用")
        return {
            "jobs": [job.to_dict() for job in state.schedule_store.list()]
        }

    @router.post("/api/schedule", dependencies=[Depends(require_token)])
    async def add_schedule(request: Request, payload: ScheduleAdd):
        state = request.app.state.geass
        if state.schedule_store is None:
            raise HTTPException(status_code=503, detail="定时系统不可用")
        try:
            job = state.schedule_store.add(
                payload.command,
                payload.run_at,
                persistent=payload.persistent,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"job": job.to_dict()}

    @router.delete("/api/schedule/{job_id}", dependencies=[Depends(require_token)])
    async def cancel_schedule(request: Request, job_id: str):
        state = request.app.state.geass
        if state.schedule_store is None:
            raise HTTPException(status_code=503, detail="定时系统不可用")
        if not state.schedule_store.remove(job_id):
            raise HTTPException(status_code=404, detail="定时任务不存在或已处理")
        return {"ok": True}

    app.include_router(router)
