"""无 socket 的 ASGI WebSocket 测试驱动：在同一事件循环内直连 app。"""

from __future__ import annotations

import asyncio
import json
from typing import Any


class WSRejected(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"websocket rejected with code {code}")
        self.code = code


class WSClient:
    def __init__(
        self,
        app: Any,
        path: str,
        query_string: bytes = b"",
        headers: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        self.app = app
        self.scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": path,
            "raw_path": path.encode() + (b"?" + query_string if query_string else b""),
            "query_string": query_string,
            "headers": headers or [],
            "client": ("test", 12345),
            "server": ("testserver", 80),
            "subprotocols": [],
        }
        self.to_app: asyncio.Queue[dict] = asyncio.Queue()
        self.from_app: asyncio.Queue[dict] = asyncio.Queue()
        self.task: asyncio.Task | None = None
        self.accepted = False

    async def __aenter__(self) -> "WSClient":
        async def receive() -> dict:
            return await self.to_app.get()

        async def send(message: dict) -> None:
            await self.from_app.put(message)

        # starlette 1.x 要求先收到 websocket.connect 才会 accept
        await self.to_app.put({"type": "websocket.connect"})
        self.task = asyncio.create_task(self.app(self.scope, receive, send))
        first = await asyncio.wait_for(self.from_app.get(), 5)
        if first.get("type") == "websocket.accept":
            self.accepted = True
            return self
        raise WSRejected(int(first.get("code", 1000)))

    async def send_json(self, data: dict) -> None:
        await self.to_app.put(
            {"type": "websocket.receive", "text": json.dumps(data, ensure_ascii=False)}
        )

    async def receive_json(self) -> dict:
        message = await asyncio.wait_for(self.from_app.get(), 5)
        assert message.get("type") == "websocket.send"
        return json.loads(message.get("text") or "null")

    async def close(self) -> None:
        await self.to_app.put({"type": "websocket.disconnect", "code": 1000})
        if self.task is not None:
            await asyncio.wait_for(self.task, 5)

    async def __aexit__(self, *exc_info) -> None:
        if self.accepted:
            await self.close()
        elif self.task is not None:
            await asyncio.wait_for(self.task, 5)
