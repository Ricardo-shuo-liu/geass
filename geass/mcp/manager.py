"""MCP 服务器注册表与运行时。

注册数据保存在 ``~/.geass/.mcp/servers.json``（0600，原子写入），
与 Geass 的持久记忆完全独立。运行时按需启动 MCP client，并对同一
服务器内的调用做串行保护，避免 stdio 子进程或 HTTP 会话并发复用。
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import logging
import os
import re
import time
import uuid
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MCP_STORE_VERSION = 1
CALL_TIMEOUT = 30.0
_SLUG_KEEP = re.compile(r"[^A-Za-z0-9_-]+")
_MAX_FUNCTION_NAME = 64


def default_mcp_path() -> Path:
    home = Path(os.environ.get("GEASS_HOME", str(Path.home())))
    return home / ".geass" / ".mcp" / "servers.json"


def _slug(value: str) -> str:
    text = _SLUG_KEEP.sub("_", str(value).strip()).strip("_")
    return text or "tool"


def _short_hash(value: str, length: int = 8) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def function_name(server_name: str, tool_name: str) -> str:
    """生成 OpenAI 函数名：mcp__<server>__<tool>，必要时稳定截断/哈希。"""
    raw = f"mcp__{_slug(server_name)}__{_slug(tool_name)}"
    if len(raw) <= _MAX_FUNCTION_NAME:
        return raw
    suffix = "_" + _short_hash(server_name + "\0" + tool_name)
    keep = _MAX_FUNCTION_NAME - len(suffix)
    return raw[:keep].rstrip("_") + suffix


def sanitize_parameters(schema: Any) -> dict[str, Any] | None:
    """把 MCP input_schema 转成 OpenAI 可接受的参数 schema。

    只做最小兼容处理：必须为 object，并移除 OpenAI 不认识的顶层字段。
    无法转换时返回 None，由调用方跳过该工具。
    """
    if not isinstance(schema, dict):
        schema = {"type": "object", "properties": {}}
    if schema.get("type") not in (None, "object"):
        return None
    cleaned = {
        "type": "object",
        "properties": schema.get("properties") or {},
    }
    if isinstance(schema.get("required"), list):
        cleaned["required"] = schema["required"]
    if "additionalProperties" in schema:
        cleaned["additionalProperties"] = bool(schema["additionalProperties"])
    return cleaned


@dataclass
class ToolRecord:
    id: str
    name: str
    description: str
    input_schema: dict[str, Any]
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ServerRecord:
    id: str
    name: str
    transport: str
    enabled: bool = False
    verified: bool = False
    last_test_at: float | None = None
    last_error: str | None = None
    command: str = ""
    args: list[str] = field(default_factory=list)
    cwd: str = ""
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    tools: list[ToolRecord] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServerRecord:
        tools = []
        for item in data.get("tools") or []:
            tools.append(
                ToolRecord(
                    id=str(item.get("id") or ""),
                    name=str(item.get("name") or ""),
                    description=str(item.get("description") or ""),
                    input_schema=item.get("input_schema") or {},
                    enabled=bool(item.get("enabled", True)),
                )
            )
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            name=str(data.get("name") or ""),
            transport=str(data.get("transport") or "stdio"),
            enabled=bool(data.get("enabled", False)),
            verified=bool(data.get("verified", False)),
            last_test_at=data.get("last_test_at"),
            last_error=data.get("last_error"),
            command=str(data.get("command") or ""),
            args=[str(item) for item in (data.get("args") or [])],
            cwd=str(data.get("cwd") or ""),
            env={str(k): str(v) for k, v in (data.get("env") or {}).items()},
            url=str(data.get("url") or ""),
            headers={str(k): str(v) for k, v in (data.get("headers") or {}).items()},
            tools=tools,
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
        )

    def validate(self) -> str | None:
        if not self.name.strip():
            return "服务器名称不能为空"
        if self.transport == "stdio" and not self.command.strip():
            return "stdio 服务器需要 command"
        if self.transport == "http" and not self.url.strip():
            return "HTTP 服务器需要 url"
        if self.transport not in ("stdio", "http"):
            return f"不支持的传输方式：{self.transport}"
        return None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def public_dict(self) -> dict[str, Any]:
        """返回给 UI/CLI 的安全视图：不暴露 env/header 的值。"""
        return {
            "id": self.id,
            "name": self.name,
            "transport": self.transport,
            "enabled": self.enabled,
            "verified": self.verified,
            "last_test_at": self.last_test_at,
            "last_error": self.last_error,
            "command": self.command,
            "args": list(self.args),
            "cwd": self.cwd,
            "env_keys": sorted(self.env),
            "url": self.url if self.transport == "http" else "",
            "header_keys": sorted(self.headers),
            "tools": [tool.to_dict() for tool in self.tools],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


Connector = Callable[[ServerRecord], Any]


async def _sdk_connect(record: ServerRecord) -> tuple[Any, AsyncExitStack]:
    """创建并进入 MCP 2.x client；返回 (client, exit_stack)。"""
    try:
        from mcp import Client, StdioServerParameters
    except ImportError as exc:  # pragma: no cover - 依赖缺失时路径
        raise RuntimeError("MCP SDK 未安装，请先安装 mcp>=2.1.1") from exc

    stack = AsyncExitStack()
    if record.transport == "stdio":
        params = StdioServerParameters(
            command=record.command,
            args=list(record.args),
            env=dict(record.env) or None,
            cwd=record.cwd or None,
        )
        client = await stack.enter_async_context(Client(params, read_timeout_seconds=CALL_TIMEOUT))
        return client, stack

    from mcp.client.streamable_http import streamable_http_client

    try:
        http_lib = importlib.import_module("httpx2")
    except ImportError:  # pragma: no cover - mcp 2.x 正常会带 httpx2
        http_lib = importlib.import_module("httpx")

    http_client = http_lib.AsyncClient(
        headers=dict(record.headers),
        timeout=http_lib.Timeout(CALL_TIMEOUT, read=300.0),
        follow_redirects=True,
    )
    await stack.enter_async_context(http_client)
    transport = streamable_http_client(record.url, http_client=http_client)
    client = await stack.enter_async_context(Client(transport, read_timeout_seconds=CALL_TIMEOUT))
    return client, stack


class _ConnectionWorker:
    """在单个 asyncio 任务中持有 MCP client 并串行执行调用。

    mcp SDK 的 AsyncExitStack / TaskGroup 要求进入与退出发生在同一任务；
    把连接与调用都收敛到这一个任务里，停用/删除/退出时才能安全地由任意
    调用方触发关闭，而不会出现 “cancel scope 属于其他任务” 的错误。
    """

    def __init__(self, manager: MCPManager, record: ServerRecord) -> None:
        self.manager = manager
        self.record = record
        self.queue: asyncio.Queue[tuple[Any, asyncio.Future[Any]] | None] = asyncio.Queue()
        self.ready = asyncio.Event()
        self.error: BaseException | None = None
        self.task: asyncio.Task[None] | None = None
        self._client: Any = None
        self._stack: AsyncExitStack | None = None
        self._active_future: asyncio.Future[Any] | None = None

    async def run(self) -> None:
        try:
            client, stack = await self.manager.connector(self.record)
        except BaseException as exc:  # 连接失败：让等待方看到错误后重试
            self.error = exc
            self.ready.set()
            return
        self._client = client
        self._stack = stack
        self.ready.set()
        try:
            while True:
                item = await self.queue.get()
                if item is None:
                    break
                call, future = item
                if future.cancelled():
                    continue
                self._active_future = future
                try:
                    result = await call(self._client)
                except BaseException as exc:
                    if isinstance(exc, asyncio.CancelledError):
                        if not future.done():
                            future.set_exception(RuntimeError("MCP 连接已关闭"))
                    elif not future.done():
                        future.set_exception(exc)
                else:
                    if not future.done():
                        future.set_result(result)
                finally:
                    self._active_future = None
        finally:
            stack = self._stack
            self._stack = None
            if stack is not None:
                try:
                    await stack.aclose()
                except Exception:
                    logger.warning("关闭 MCP 连接失败：%s", self.record.name, exc_info=True)

    async def stop(self, cancel_pending: bool = False) -> None:
        task = self.task
        if task is None or task.done():
            return
        closed = RuntimeError("MCP 连接已关闭")
        while True:
            try:
                item = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is not None and not item[1].done():
                item[1].set_exception(closed)
        if cancel_pending:
            task.cancel()
        else:
            try:
                self.queue.put_nowait(None)
            except Exception:
                task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class MCPManager:
    """MCP 注册表 + 每服务器一个常驻连接任务。

    ``connector`` 只用于测试注入；生产环境默认使用 ``_sdk_connect``。
    """

    def __init__(
        self,
        path: str | Path | None = None,
        connector: Connector | None = None,
    ) -> None:
        self.path = Path(path) if path else default_mcp_path()
        self.connector = connector or _sdk_connect
        self._servers: dict[str, ServerRecord] = {}
        self._workers: dict[str, _ConnectionWorker] = {}
        self._closing_tasks: set[asyncio.Task[None]] = set()
        self._load()

    # ---------- 持久化 ----------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("MCP 注册文件损坏，已忽略：%s", self.path)
            return
        for item in data.get("servers") or []:
            record = ServerRecord.from_dict(item)
            if record.name:
                self._servers[record.name] = record

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass
        payload = {
            "version": MCP_STORE_VERSION,
            "servers": [record.to_dict() for record in self._servers.values()],
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    # ---------- 查询 ----------

    def get(self, name: str) -> ServerRecord | None:
        return self._servers.get(name)

    def servers(self) -> list[ServerRecord]:
        return list(self._servers.values())

    def list_public(self) -> list[dict[str, Any]]:
        return [record.public_dict() for record in self.servers()]

    def list_summary(self) -> list[dict[str, Any]]:
        summary: list[dict[str, Any]] = []
        for record in self.servers():
            summary.append(
                {
                    "id": record.id,
                    "name": record.name,
                    "transport": record.transport,
                    "enabled": record.enabled,
                    "verified": record.verified,
                    "last_test_at": record.last_test_at,
                    "last_error": record.last_error,
                    "command": record.command,
                    "url": record.url if record.transport == "http" else "",
                    "env_keys": sorted(record.env),
                    "header_keys": sorted(record.headers),
                    "tools": [
                        {
                            "id": tool.id,
                            "name": tool.name,
                            "description": tool.description,
                            "enabled": tool.enabled,
                        }
                        for tool in record.tools
                    ],
                }
            )
        return summary

    def has_function(self, name: str) -> bool:
        return self._spec(name) is not None

    def _function_map(self) -> dict[str, tuple[ServerRecord, ToolRecord]]:
        """建立去重后的函数名 -> (服务器, 工具) 映射。

        ``function_name()`` 只负责清洗/截断；当不同服务器或工具清洗后的
        slug 相同而产生冲突时，追加稳定短哈希做二级消歧，保证导出给模型
        的函数名全局唯一。
        """
        mapping: dict[str, tuple[ServerRecord, ToolRecord]] = {}
        records = sorted(self._servers.values(), key=lambda item: (item.name.casefold(), item.id))
        for record in records:
            for tool in sorted(record.tools, key=lambda item: item.name):
                candidate = function_name(record.name, tool.name)
                if candidate in mapping:
                    suffix = "_" + _short_hash(f"{record.id}\0{tool.id}")
                    candidate = candidate[: _MAX_FUNCTION_NAME - len(suffix)].rstrip("_") + suffix
                    while candidate in mapping:
                        suffix = "_" + _short_hash(f"{record.id}\0{tool.id}\0{candidate}")
                        candidate = (
                            candidate[: _MAX_FUNCTION_NAME - len(suffix)].rstrip("_") + suffix
                        )
                mapping[candidate] = (record, tool)
        return mapping

    def _spec(self, function: str) -> tuple[ServerRecord, ToolRecord] | None:
        return self._function_map().get(function)

    def schemas(self) -> list[dict[str, Any]]:
        """返回当前可暴露给模型的 OpenAI function 列表。"""
        result: list[dict[str, Any]] = []
        for function, (record, tool) in self._function_map().items():
            if not record.enabled or not record.verified:
                continue
            if not tool.enabled:
                continue
            parameters = sanitize_parameters(tool.input_schema)
            if parameters is None:
                logger.warning(
                    "MCP 工具 schema 无法转换，跳过：%s/%s",
                    record.name,
                    tool.name,
                )
                continue
            result.append(
                {
                    "type": "function",
                    "name": function,
                    "description": tool.description,
                    "parameters": parameters,
                }
            )
        return result

    # ---------- 增删改 ----------

    def add(self, name: str, transport: str, **kwargs: Any) -> ServerRecord:
        name = str(name).strip()
        if not name:
            raise ValueError("服务器名称不能为空")
        key = name.casefold()
        if any(existing.name.casefold() == key for existing in self._servers.values()):
            raise ValueError(f"MCP 服务器已存在：{name}")
        record = ServerRecord(
            id=uuid.uuid4().hex,
            name=name,
            transport=transport,
            command=str(kwargs.get("command") or ""),
            args=[str(item) for item in (kwargs.get("args") or [])],
            cwd=str(kwargs.get("cwd") or ""),
            env={str(k): str(v) for k, v in (kwargs.get("env") or {}).items()},
            url=str(kwargs.get("url") or ""),
            headers={str(k): str(v) for k, v in (kwargs.get("headers") or {}).items()},
        )
        error = record.validate()
        if error:
            raise ValueError(error)
        self._servers[name] = record
        self._save()
        return record

    def remove(self, name: str) -> bool:
        record = self._servers.pop(name, None)
        if record is None:
            return False
        self._save()
        self._schedule_stop_worker(name)
        return True

    async def remove_async(self, name: str) -> bool:
        if self._servers.pop(name, None) is None:
            return False
        self._save()
        await self._stop_worker(name)
        return True

    def set_enabled(self, name: str, enabled: bool) -> bool:
        record = self.get(name)
        if record is None:
            return False
        if enabled and not record.verified:
            return False
        record.enabled = enabled
        record.updated_at = time.time()
        self._save()
        if not enabled:
            self._schedule_stop_worker(name)
        return True

    async def set_enabled_async(self, name: str, enabled: bool) -> bool:
        record = self.get(name)
        if record is None:
            return False
        if enabled and not record.verified:
            return False
        record.enabled = enabled
        record.updated_at = time.time()
        self._save()
        if not enabled:
            await self._stop_worker(name)
        return True

    def set_tool_enabled(self, name: str, tool: str, enabled: bool) -> bool:
        record = self.get(name)
        if record is None:
            return False
        for item in record.tools:
            if item.id == tool or item.name == tool:
                item.enabled = enabled
                record.updated_at = time.time()
                self._save()
                return True
        return False

    async def add_and_test(self, name: str, transport: str, **kwargs: Any) -> ServerRecord:
        self.add(name, transport, **kwargs)
        await self.test(name)
        record = self.get(name)
        if record is None:  # pragma: no cover - 不会发生
            raise ValueError(f"MCP 服务器不存在：{name}")
        return record

    async def test(self, name: str) -> ServerRecord:
        record = self.get(name)
        if record is None:
            raise ValueError(f"MCP 服务器不存在：{name}")
        # 先关掉旧的常驻连接，保证重测/修复后从新连接开始。
        await self._stop_worker(name)
        record.last_test_at = time.time()
        record.last_error = None
        was_verified = record.verified
        try:
            tools = await self._remote_tools(record)
        except Exception as exc:
            record.last_error = str(exc)
            record.verified = False
            record.enabled = False
            record.updated_at = time.time()
            self._save()
            return record
        record.verified = True
        if not was_verified:
            record.enabled = True
        record.tools = self._merge_tools(record.tools, tools, server_enabled=record.enabled)
        record.updated_at = time.time()
        self._save()
        return record

    def _merge_tools(
        self,
        old: list[ToolRecord],
        remote: list[dict[str, Any]],
        server_enabled: bool,
    ) -> list[ToolRecord]:
        previous = {item.name: item.enabled for item in old}
        merged: list[ToolRecord] = []
        for item in remote:
            tool_name = str(item.get("name") or "")
            if not tool_name:
                continue
            tool_id = f"{_slug(tool_name)}-{_short_hash(tool_name)}"
            enabled = previous.get(tool_name, server_enabled)
            merged.append(
                ToolRecord(
                    id=tool_id,
                    name=tool_name,
                    description=str(item.get("description") or item.get("title") or ""),
                    input_schema=item.get("input_schema") or {},
                    enabled=enabled,
                )
            )
        return merged

    # ---------- 运行 ----------

    async def _remote_tools(self, record: ServerRecord) -> list[dict[str, Any]]:
        client, stack = await self.connector(record)
        try:
            tools: list[dict[str, Any]] = []
            cursor: str | None = None
            while True:
                result = await client.list_tools(cursor=cursor)
                for tool in result.tools:
                    tools.append(
                        {
                            "name": tool.name,
                            "title": getattr(tool, "title", None),
                            "description": getattr(tool, "description", ""),
                            "input_schema": tool.input_schema,
                        }
                    )
                next_cursor = getattr(result, "next_cursor", None)
                if next_cursor is None:
                    break
                cursor = next_cursor
            return tools
        finally:
            await stack.aclose()

    async def call(self, function: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        spec = self._spec(function)
        if spec is None:
            return None
        record, tool = spec
        if not record.enabled or not record.verified or not tool.enabled:
            return {"ok": False, "error": f"MCP 工具已停用或未验证：{function}"}
        try:
            worker = await self._acquire_worker(record)
        except Exception as exc:
            logger.warning("MCP 连接失败 %s：%s", record.name, exc)
            return {"ok": False, "error": f"MCP 连接失败：{exc}"}

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        worker.queue.put_nowait(
            (
                lambda client: client.call_tool(tool.name, arguments),
                future,
            )
        )
        try:
            result = await asyncio.wait_for(future, timeout=CALL_TIMEOUT)
        except asyncio.TimeoutError:
            await self._stop_worker(record.name)
            return {
                "ok": False,
                "error": f"MCP 工具 {tool.name} 调用超时（{CALL_TIMEOUT:.0f}s）",
            }
        except Exception as exc:
            await self._stop_worker(record.name)
            logger.warning("MCP 调用失败 %s/%s：%s", record.name, tool.name, exc)
            return {"ok": False, "error": f"MCP 工具调用失败：{exc}"}
        if getattr(result, "is_error", False):
            return {
                "ok": False,
                "error": self._render_content(result) or "MCP 工具返回错误",
            }
        text = self._render_content(result)
        return {"ok": True, "message": text or "MCP 工具执行完成", "result": text}

    async def _acquire_worker(self, record: ServerRecord) -> _ConnectionWorker:
        worker = self._workers.get(record.name)
        if worker is None or worker.task is None or worker.task.done():
            worker = _ConnectionWorker(self, record)
            worker.task = asyncio.create_task(worker.run())
            self._workers[record.name] = worker
        try:
            await asyncio.wait_for(worker.ready.wait(), timeout=CALL_TIMEOUT + 5)
        except asyncio.TimeoutError as exc:
            self._workers.pop(record.name, None)
            if worker.task is not None and not worker.task.done():
                worker.task.cancel()
                try:
                    await worker.task
                except asyncio.CancelledError:
                    pass
            raise RuntimeError(f"MCP 连接超时（{CALL_TIMEOUT:.0f}s）") from exc
        if worker.error is not None:
            self._workers.pop(record.name, None)
            raise RuntimeError(str(worker.error)) from worker.error
        if worker._client is None:  # pragma: no cover - ready 且无错误时必有 client
            raise RuntimeError(f"MCP 连接尚未就绪：{record.name}")
        return worker

    def _schedule_stop_worker(self, name: str) -> None:
        worker = self._workers.pop(name, None)
        if worker is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(worker.stop(cancel_pending=True))
        self._closing_tasks.add(task)
        task.add_done_callback(self._closing_tasks.discard)

    async def _stop_worker(self, name: str) -> None:
        worker = self._workers.pop(name, None)
        if worker is not None:
            await worker.stop(cancel_pending=True)

    async def aclose(self) -> None:
        for name in list(self._workers):
            await self._stop_worker(name)
        closing = list(self._closing_tasks)
        self._closing_tasks.clear()
        if closing:
            await asyncio.gather(*closing, return_exceptions=True)

    @staticmethod
    def _render_content(result: Any) -> str:
        structured = getattr(result, "structured_content", None)
        if structured is not None:
            try:
                return json.dumps(structured, ensure_ascii=False)
            except (TypeError, ValueError):
                return str(structured)
        parts: list[str] = []
        for block in getattr(result, "content", None) or []:
            kind = getattr(block, "type", None)
            if kind == "text" and hasattr(block, "text"):
                parts.append(str(block.text))
            elif kind == "resource":
                parts.append("（MCP 返回资源引用）")
            elif kind == "image":
                parts.append("（MCP 返回图片，未转发给模型）")
            else:
                parts.append("（MCP 返回非文本内容）")
        return "\n".join(part for part in parts if part)


def server_from_mcp_servers_entry(name: str, entry: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """把 Claude/Cursor 风格 mcpServers 条目转成 add() 参数。"""
    transport = str(entry.get("type") or ("http" if entry.get("url") else "stdio"))
    if transport in ("http", "streamable-http", "streamable_http"):
        transport = "http"
    elif transport == "stdio":
        transport = "stdio"
    else:
        raise ValueError(f"不支持的 MCP transport：{transport}")
    kwargs: dict[str, Any] = {
        "command": str(entry.get("command") or ""),
        "args": [str(item) for item in (entry.get("args") or [])],
        "cwd": str(entry.get("cwd") or ""),
        "env": {str(k): str(v) for k, v in (entry.get("env") or {}).items()},
        "url": str(entry.get("url") or ""),
        "headers": {str(k): str(v) for k, v in (entry.get("headers") or {}).items()},
    }
    return transport, kwargs
