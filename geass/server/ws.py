"""WebSocket：屏幕帧流与命令通道。"""
from __future__ import annotations

import asyncio
import time

from fastapi import WebSocket, WebSocketDisconnect

from .auth import ws_auth
from .manual import execute_manual_input
from .state import AppState, broadcast_control
from ..skills import load_skills, sync_system_skills


def register(app) -> None:
    @app.websocket("/ws/screen")
    async def screen_ws(ws: WebSocket):
        state: AppState = ws.app.state.geass
        ok, subprotocol = ws_auth(ws)
        if not ok:
            await ws.close(code=4401)
            return
        await ws.accept(subprotocol=subprotocol)
        queue = state.streamer.subscribe()
        try:
            while True:
                receive_task = asyncio.create_task(ws.receive())
                frame_task = asyncio.create_task(queue.get())
                done, pending = await asyncio.wait(
                    {receive_task, frame_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if receive_task in done:
                    message = receive_task.result()
                    frame_task.cancel()
                    if message.get("type") == "websocket.disconnect":
                        break
                    continue
                frame = frame_task.result()
                receive_task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                await ws.send_bytes(frame)
        except WebSocketDisconnect:
            pass
        finally:
            state.streamer.unsubscribe(queue)

    @app.websocket("/ws/control")
    async def control_ws(ws: WebSocket):
        state: AppState = ws.app.state.geass
        ok, subprotocol = ws_auth(ws)
        if not ok:
            await ws.close(code=4401)
            return
        await ws.accept(subprotocol=subprotocol)
        state.control_clients.add(ws)
        for pending in state.approval_manager.pending:
            await ws.send_json(
                {
                    "type": "approval_request",
                    "id": pending.id,
                    "tool": "open_terminal",
                    "command": pending.command,
                    "reason": pending.reason,
                    "expires_in": pending.expires_in,
                }
            )
        try:
            while True:
                message = await ws.receive_json()
                await handle_control(state, ws, message)
        except WebSocketDisconnect:
            pass
        finally:
            state.control_clients.discard(ws)


async def handle_control(state: AppState, ws: WebSocket, message: dict) -> None:
    mtype = message.get("type")
    if mtype == "ping":
        await ws.send_json({"type": "pong"})
    elif mtype == "stop":
        if state.cancel_event is not None:
            state.cancel_event.set()
        state.last_activity = time.time()
        await state.approval_manager.reject_all("任务已停止")
        await broadcast_control(
            state,
            {
                "type": "agent_status",
                "state": "cancelling",
                "step": 0,
                "tool": None,
                "message": "收到停止指令",
            },
        )
    elif mtype == "command":
        text = str(message.get("text") or "").strip()
        if not text:
            await ws.send_json(
                {
                    "type": "agent_status",
                    "state": "error",
                    "step": 0,
                    "tool": None,
                    "message": "命令不能为空",
                }
            )
            return
        await start_agent(state, text)
    elif mtype == "approval":
        approval_id = str(message.get("id") or "")
        approved = bool(message.get("approved"))
        if not await state.approval_manager.resolve(approval_id, approved):
            await ws.send_json(
                {
                    "type": "error",
                    "message": "审核请求不存在或已处理",
                }
            )
    elif mtype == "manual_input":
        # 用户开始手动直控时接管：若 Agent 仍在运行则请求它退出。
        if (
            state.agent_task
            and not state.agent_task.done()
            and state.cancel_event is not None
        ):
            state.cancel_event.set()
            await broadcast_control(
                state,
                {
                    "type": "agent_status",
                    "state": "cancelling",
                    "step": 0,
                    "tool": None,
                    "message": "用户开始手动直控，Agent 任务将被接管",
                },
            )
        try:
            result = execute_manual_input(state.backend, message)
        except Exception as exc:
            result = {"ok": False, "error": f"手动输入执行失败：{exc}"}
        if not result.get("ok"):
            await ws.send_json(
                {"type": "error", "message": result.get("error", "手动输入失败")}
            )
    else:
        await ws.send_json({"type": "error", "message": f"未知消息类型：{mtype}"})


async def start_agent(state: AppState, text: str) -> None:
    if state.agent_task and not state.agent_task.done():
        await broadcast_control(
            state,
            {
                "type": "agent_status",
                "state": "busy",
                "step": 0,
                "tool": None,
                "message": "已有任务正在执行，可先发送 stop 中断",
            },
        )
        return

    state.last_activity = time.time()
    # 上一个任务若残留未处理的审核请求，先全部拒绝，避免悬挂。
    await state.approval_manager.reject_all("新任务已开始")

    # 每条命令开始时同步种子目录并重新扫描运行时 SKILL：
    # 仓库修改与空闲进化生成的新技能都无需重启服务即可生效。
    sync_system_skills(state.skill_source_dir, state.skill_root)
    state.skills = load_skills(state.skill_root, state.config.config_path)
    state.agent.skills = state.skills
    if state.evolution is not None:
        state.evolution.record_task(text)

    state.cancel_event = asyncio.Event()

    async def run_and_report() -> dict:
        try:
            result = await state.agent.run(text, cancel=state.cancel_event)
        except Exception as exc:
            result = {"state": "error", "message": str(exc)}
        await broadcast_control(state, {"type": "agent_result", **result})
        state.last_activity = time.time()
        return result

    state.agent_task = asyncio.create_task(run_and_report())
    await broadcast_control(
        state,
        {
            "type": "agent_status",
            "state": "accepted",
            "step": 0,
            "tool": None,
            "message": f"已接收命令：{text}",
        },
    )
    return state.agent_task
