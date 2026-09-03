"""``geass mcp``：管理 MCP 工具服务器。"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from .manager import MCPManager, server_from_mcp_servers_entry


def _kv(items: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"无效的 K=V：{item}")
        key, value = item.split("=", 1)
        result[key.strip()] = value
    return result


def _header_items(items: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        if ":" not in item:
            raise SystemExit(f"无效的 Header（需要 Key: Value）：{item}")
        key, value = item.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def _print_record(record: Any, prefix: str = "") -> None:
    status = "启用" if record.enabled else "停用"
    verified = "已测试" if record.verified else "测试失败"
    print(
        f"{prefix}{record.name}  [{status}/{verified}] "
        f"{record.transport} · {len(record.tools)} 个工具"
    )
    if record.last_error:
        print(f"  {record.last_error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="geass mcp",
        description="管理 Geass MCP 工具（配置保存在 ~/.geass/.mcp/servers.json）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="添加并自动测试一个 MCP 服务器")
    add.add_argument("name")
    add.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    add.add_argument("--command", dest="command_value", help="stdio：可执行命令")
    add.add_argument("--args", action="append", default=[], dest="args_items", metavar="ARG")
    add.add_argument("--env", action="append", default=[], dest="env_items", metavar="K=V")
    add.add_argument("--cwd", help="stdio：子进程工作目录")
    add.add_argument("--url", help="http：Streamable HTTP 地址")
    add.add_argument("--header", action="append", default=[], dest="header_items", metavar="H:V")

    import_parser = sub.add_parser("import", help="从 Claude/Cursor 风格 JSON 导入 mcpServers")
    import_parser.add_argument("file", help="JSON 文件路径")

    sub.add_parser("list", help="列出全部 MCP 服务器")

    test = sub.add_parser("test", help="重新连接测试服务器")
    test.add_argument("name")

    enable = sub.add_parser("enable", help="启用服务器；给工具名时只启用这些工具")
    enable.add_argument("name")
    enable.add_argument("tools", nargs="*", metavar="TOOL")

    disable = sub.add_parser("disable", help="停用服务器；给工具名时只停用这些工具")
    disable.add_argument("name")
    disable.add_argument("tools", nargs="*", metavar="TOOL")

    remove = sub.add_parser("remove", help="永久删除服务器注册")
    remove.add_argument("name")
    remove.add_argument("--yes", action="store_true", help="跳过二次确认")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    manager = MCPManager()

    if args.command == "list":
        records = manager.servers()
        if not records:
            print("暂无 MCP 服务器")
            return
        for record in records:
            _print_record(record)
        return

    if args.command == "test":
        record = asyncio.run(manager.test(args.name))
        _print_record(record)
        if not record.verified:
            raise SystemExit(1)
        return

    if args.command == "add":
        kwargs: dict[str, Any] = {
            "command": args.command_value,
            "args": args.args_items,
            "env": _kv(args.env_items),
            "cwd": args.cwd or "",
            "url": args.url or "",
            "headers": _header_items(args.header_items),
        }
        try:
            record = asyncio.run(manager.add_and_test(args.name, args.transport, **kwargs))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        _print_record(record)
        if not record.verified:
            raise SystemExit(1)
        return

    if args.command == "import":
        path = Path(args.file)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"无法读取 JSON：{exc}") from exc
        entries = data.get("mcpServers") or data
        if not isinstance(entries, dict):
            raise SystemExit("JSON 中找不到 mcpServers 对象")
        failed = 0
        for name, entry in entries.items():
            try:
                transport, kwargs = server_from_mcp_servers_entry(name, entry)
                record = asyncio.run(manager.add_and_test(name, transport, **kwargs))
            except ValueError as exc:
                failed += 1
                print(f"导入失败：{name} -> {exc}")
                continue
            _print_record(record, prefix="- ")
            if not record.verified:
                failed += 1
        if failed:
            raise SystemExit(f"{failed} 个服务器未通过测试（记录已保留，可修复后 geass mcp test）")
        return

    if args.command in ("enable", "disable"):
        enabled = args.command == "enable"
        item = manager.get(args.name)
        if item is None:
            raise SystemExit(f"MCP 服务器不存在：{args.name}")
        if args.tools:
            for tool in args.tools:
                if not manager.set_tool_enabled(args.name, tool, enabled):
                    raise SystemExit(f"服务器 {args.name} 中找不到工具：{tool}")
            print(f"已{'启用' if enabled else '停用'}工具：{'、'.join(args.tools)}")
            return
        if enabled and not item.verified:
            raise SystemExit(f"服务器 {args.name} 未通过测试，不能启用")
        if not manager.set_enabled(args.name, enabled):
            raise SystemExit(f"MCP 服务器不存在：{args.name}")
        print(f"已{'启用' if enabled else '停用'}：{args.name}")
        return

    if args.command == "remove":
        if not args.yes:
            first = input(f"将永久删除 MCP 服务器「{args.name}」，输入 remove 继续：")
            if first.strip() != "remove":
                print("已取消。")
                return
            second = input("再次输入 remove 确认删除：")
            if second.strip() != "remove":
                print("已取消。")
                return
        if not manager.remove(args.name):
            raise SystemExit(f"MCP 服务器不存在：{args.name}")
        print(f"已永久删除：{args.name}")


if __name__ == "__main__":
    main()
