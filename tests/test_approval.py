from __future__ import annotations

import asyncio

import pytest

from geass.server.approval import ApprovalManager


def run(coro):
    return asyncio.run(coro)


def test_request_approve():
    async def main():
        manager = ApprovalManager(default_timeout=30)
        task = asyncio.create_task(manager.request("sudo ls", "提权"))
        await asyncio.sleep(0)
        pending = manager.pending
        assert len(pending) == 1
        assert pending[0].command == "sudo ls"
        assert pending[0].reason == "提权"
        assert await manager.resolve(pending[0].id, True) is True
        assert await task == {"approved": True, "reason": "审核通过"}

    run(main())


def test_request_deny():
    async def main():
        manager = ApprovalManager()
        task = asyncio.create_task(manager.request("rm -rf /", "删除"))
        await asyncio.sleep(0)
        assert await manager.resolve(manager.pending[0].id, False) is True
        decision = await task
        assert decision["approved"] is False
        assert "拒绝" in decision["reason"]

    run(main())


def test_first_resolution_wins():
    async def main():
        manager = ApprovalManager()
        task = asyncio.create_task(manager.request("reboot", "重启"))
        await asyncio.sleep(0)
        approval_id = manager.pending[0].id
        assert await manager.resolve(approval_id, True) is True
        assert await manager.resolve(approval_id, False) is False
        assert (await task)["approved"] is True

    run(main())


def test_unknown_id_returns_false():
    async def main():
        manager = ApprovalManager()
        assert await manager.resolve("nope", True) is False

    run(main())


def test_timeout_auto_denies():
    async def main():
        manager = ApprovalManager(default_timeout=0.05)
        decision = await manager.request("shutdown now", "关机")
        assert decision["approved"] is False
        assert "超时" in decision["reason"]
        assert manager.pending == []

    run(main())


def test_reject_all_wakes_pending_requests():
    async def main():
        manager = ApprovalManager()
        first = asyncio.create_task(manager.request("sudo ls", "提权"))
        second = asyncio.create_task(manager.request("reboot", "重启"))
        await asyncio.sleep(0)
        assert len(manager.pending) == 2
        await manager.reject_all("任务已停止")
        assert manager.pending == []
        assert (await first)["approved"] is False
        assert (await second)["approved"] is False

    run(main())


def test_broadcast_receives_request_and_resolution():
    async def main():
        messages = []

        async def broadcast(message):
            messages.append(message)

        manager = ApprovalManager(broadcast=broadcast)
        task = asyncio.create_task(manager.request("sudo ls", "提权"))
        await asyncio.sleep(0)
        assert messages[0]["type"] == "approval_request"
        approval_id = messages[0]["id"]
        await manager.resolve(approval_id, True)
        await task
        assert messages[-1] == {
            "type": "approval_resolved",
            "id": approval_id,
            "approved": True,
        }

    run(main())
