"""REST 接口：健康检查、信息、配置、语音兜底转写、停止 Agent。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from ..config import load_config, mask_secret, save_user_env
from .auth import require_token
from .state import reload_state


class ConfigUpdate(BaseModel):
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    vision: bool | None = None


def config_summary(state) -> dict[str, Any]:
    return {
        "model": state.config.agent.model,
        "base_url": state.config.agent.base_url or "",
        "vision": state.config.agent.vision,
        "api_key": mask_secret(state.config.api_key),
        "api_configured": bool(state.client),
        "voice_fallback_model": state.config.voice.fallback_model,
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
        updates: dict[str, dict[str, Any]] = {"agent": {}}
        for key in ("model", "base_url", "api_key"):
            value = getattr(payload, key)
            if value:
                updates["agent"][key] = value
        if payload.vision is not None:
            updates["agent"]["vision"] = payload.vision
        if not updates["agent"]:
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

    app.include_router(router)
