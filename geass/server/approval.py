"""危险命令的人工审核网关：挂起 Agent，等待手机端允许或拒绝。

`Agent` 执行命中黑名单的 `open_terminal` 命令前会调用
`ApprovalManager.request()`；该方法向所有控制端广播 `approval_request`，
然后等待任意一个客户端回 `approval` 消息，超时自动拒绝。先到的决定生效，
拒绝/超时/任务停止统一广播 `approval_resolved`，让其他客户端关掉弹窗。
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class PendingApproval:
    id: str
    command: str
    reason: str
    expires_in: float


class ApprovalManager:
    def __init__(
        self,
        default_timeout: float = 30.0,
        broadcast: BroadcastFn | None = None,
    ) -> None:
        self.default_timeout = default_timeout
        self.broadcast = broadcast
        self._pending: dict[str, tuple[asyncio.Future, PendingApproval]] = {}

    @property
    def pending(self) -> list[PendingApproval]:
        """当前仍在等待审核的请求（按创建顺序）。"""
        return [pending for _, pending in self._pending.values()]

    async def _broadcast(self, message: dict[str, Any]) -> None:
        if self.broadcast is None:
            return
        try:
            await self.broadcast(message)
        except Exception:
            logger.warning("广播审核事件失败", exc_info=True)

    async def request(self, command: str, reason: str = "") -> dict[str, Any]:
        """挂起当前任务，等待用户决定；返回 ``{"approved": bool, "reason": str}``。"""
        loop = asyncio.get_running_loop()
        approval_id = secrets.token_hex(6)
        # 配置层保证 >=5s；这里仅防御非法值，测试可用更短超时。
        expires_in = max(0.1, float(self.default_timeout))
        pending = PendingApproval(
            id=approval_id,
            command=str(command),
            reason=str(reason or "命中安全规则"),
            expires_in=expires_in,
        )
        future: asyncio.Future = loop.create_future()
        self._pending[approval_id] = (future, pending)
        await self._broadcast(
            {
                "type": "approval_request",
                "id": approval_id,
                "tool": "open_terminal",
                "command": pending.command,
                "reason": pending.reason,
                "expires_in": expires_in,
            }
        )
        try:
            approved = await asyncio.wait_for(
                asyncio.shield(future), timeout=expires_in
            )
        except asyncio.TimeoutError:
            self._pending.pop(approval_id, None)
            await self._broadcast(
                {
                    "type": "approval_resolved",
                    "id": approval_id,
                    "approved": False,
                }
            )
            return {
                "approved": False,
                "reason": f"命令审核超时（{expires_in:.0f}s），已自动拒绝",
            }
        return {
            "approved": bool(approved),
            "reason": "审核通过" if approved else "用户拒绝了该命令",
        }

    async def resolve(self, approval_id: str, approved: bool) -> bool:
        """处理客户端回传的允许/拒绝；请求不存在或已处理返回 False。"""
        entry = self._pending.pop(str(approval_id), None)
        if entry is None:
            return False
        future, pending = entry
        if future.done():
            return False
        future.set_result(bool(approved))
        await self._broadcast(
            {
                "type": "approval_resolved",
                "id": pending.id,
                "approved": bool(approved),
            }
        )
        return True

    async def reject_all(self, reason: str = "任务已停止") -> None:
        """拒绝全部挂起请求，避免 Agent 在停止/切换任务时悬挂。"""
        for approval_id in list(self._pending):
            entry = self._pending.get(approval_id)
            if entry is None:
                continue
            future, pending = entry
            if future.done():
                continue
            future.set_result(False)
            self._pending.pop(approval_id, None)
            await self._broadcast(
                {
                    "type": "approval_resolved",
                    "id": pending.id,
                    "approved": False,
                    "reason": reason,
                }
            )
