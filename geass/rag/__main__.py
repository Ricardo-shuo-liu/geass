"""``python -m geass.rag`` 命令行：管理 RAG 数据源。"""
from __future__ import annotations

import argparse
import sys

from ..config import load_config
from .embeddings import provider_from_config
from . import RAGManager


def _manager() -> RAGManager:
    config = load_config(persist=False)
    provider = provider_from_config(config)
    return RAGManager(config.agent.rag_path or None, provider=provider)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m geass.rag",
        description="管理 Geass RAG 数据源（只读写 ~/.geass/.rag，不改动原始文件）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    add_parser = sub.add_parser("add", help="锁定数据源（文件夹递归，重复执行对账重导入）")
    add_parser.add_argument("path", help="文件或文件夹路径")
    add_parser.add_argument("--name", help="数据源别名")
    add_parser.add_argument(
        "--ext",
        help="允许的后缀，逗号分隔（如 .md,.txt；默认内置白名单）",
    )

    sub.add_parser("list", help="查看全部数据源与类型")

    remove_parser = sub.add_parser("remove", help="删除整个数据源的 RAG 镜像")
    remove_parser.add_argument("source", help="数据源名称或 id")

    remove_file_parser = sub.add_parser("remove-file", help="删除某个文件的分块镜像")
    remove_file_parser.add_argument("source", help="数据源名称或 id")
    remove_file_parser.add_argument("rel_path", help="源内相对路径")

    enable_parser = sub.add_parser("enable", help="启用数据源")
    enable_parser.add_argument("source")
    disable_parser = sub.add_parser("disable", help="停用数据源（保留数据）")
    disable_parser.add_argument("source")
    sub.add_parser("disable-all", help="停用全部数据源（保留数据）")
    sub.add_parser("enable-all", help="启用全部数据源")

    reindex_parser = sub.add_parser("reindex", help="重建索引（嵌入模型变化后需要）")
    reindex_parser.add_argument("source")

    args = parser.parse_args()
    manager = _manager()

    if args.command == "add":
        exts = (
            [item.strip() for item in args.ext.split(",") if item.strip()]
            if args.ext
            else None
        )
        try:
            result = manager.add_source(args.path, name=args.name, exts=exts)
        except ValueError as exc:
            raise SystemExit(str(exc))
        print(result["message"])
        return

    if args.command == "list":
        sources = manager.list_sources()
        if not sources:
            print("暂无 RAG 数据源")
            return
        for source in sources:
            mode = source["mode"] + ("（需重建）" if source["needs_reindex"] else "")
            status = "启用" if source["enabled"] else "停用"
            print(
                f"{source['name']}  [{status}] {mode}  "
                f"{source['files']} 文件 / {source['chunks']} 分块  "
                f"类型: {', '.join(source['exts']) or '-'}"
            )
        return

    if args.command == "remove":
        if not manager.remove_source(args.source):
            raise SystemExit(f"数据源不存在：{args.source}")
        print(f"已删除数据源：{args.source}")
        return

    if args.command == "remove-file":
        if not manager.remove_file(args.source, args.rel_path):
            raise SystemExit(f"找不到 {args.source} 中的 {args.rel_path}")
        print(f"已删除 {args.source}/{args.rel_path} 的 RAG 镜像")
        return

    if args.command == "enable":
        if not manager.set_enabled(args.source, True):
            raise SystemExit(f"数据源不存在：{args.source}")
        print(f"已启用：{args.source}")
        return

    if args.command == "disable":
        if not manager.set_enabled(args.source, False):
            raise SystemExit(f"数据源不存在：{args.source}")
        print(f"已停用：{args.source}")
        return

    if args.command == "disable-all":
        changed = manager.set_all_enabled(False)
        print(f"已停用全部数据源（{changed} 个变更）")
        return

    if args.command == "enable-all":
        changed = manager.set_all_enabled(True)
        print(f"已启用全部数据源（{changed} 个变更）")
        return

    if args.command == "reindex":
        result = manager.reindex(args.source)
        if not result.get("ok"):
            raise SystemExit(str(result.get("error") or "重建失败"))
        print(result["message"])
        return


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"RAG 命令失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
