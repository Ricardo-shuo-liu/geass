"""WebSocket：屏幕帧流与命令通道。"""
from __future__ import annotations

import asyncio

from fastapi import WebSocket, WebSocketDisconnect

from .auth import ws_auth
from .state import AppState, broadcast_control


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

    state.cancel_event = asyncio.Event()

    async def run_and_report() -> None:
        try:
            result = await state.agent.run(text, cancel=state.cancel_event)
        except Exception as exc:
            result = {"state": "error", "message": str(exc)}
        await broadcast_control(state, {"type": "agent_result", **result})

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
