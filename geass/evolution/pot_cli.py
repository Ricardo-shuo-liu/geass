"""``geass pot``：POT 反思系统管理命令。"""
from __future__ import annotations

import argparse

from ..config import load_config
from .pot import POTStore


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="geass pot",
        description="管理 POT：Global-COT 与 ROT 角色模板",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    cot = sub.add_parser("cot", help="查看/设置 Global-COT")
    cot_sub = cot.add_subparsers(dest="action", required=True)
    cot_sub.add_parser("show", help="显示当前 COT")
    set_parser = cot_sub.add_parser("set", help="设置 COT（读取 stdin 或 --text）")
    set_parser.add_argument("--text", help="COT 文本")

    rot = sub.add_parser("rot", help="管理 ROT")
    rot_sub = rot.add_subparsers(dest="action", required=True)
    rot_sub.add_parser("list", help="列出全部 ROT")
    show = rot_sub.add_parser("show", help="显示指定 ROT")
    show.add_argument("name")
    disable = rot_sub.add_parser("disable", help="停用 ROT")
    disable.add_argument("name")
    enable = rot_sub.add_parser("enable", help="启用 ROT")
    enable.add_argument("name")
    delete = rot_sub.add_parser("delete", help="删除 ROT")
    delete.add_argument("name")

    args = parser.parse_args()
    config = load_config(persist=False)
    store = POTStore(config.agent.pot_path or None)

    if args.command == "cot":
        if args.action == "show":
            print(store.get_cot() or "（暂无 COT）")
            return
        text = args.text or __import__("sys").stdin.read().strip()
        if not text:
            raise SystemExit("COT 内容为空")
        store.set_cot(text)
        print("已更新 Global-COT")
        return

    if args.action == "list":
        for rot in store.list_rots():
            status = "启用" if rot.enabled else "停用"
            print(f"{rot.name}  [{status}] {rot.description}")
        return
    if args.action == "show":
        rot = store.get_rot(args.name)
        if rot is None:
            raise SystemExit(f"ROT 不存在：{args.name}")
        print(f"# {rot.name}（{rot.role}）\n{rot.body}")
        return
    if args.action == "disable":
        if not store.set_rot_enabled(args.name, False):
            raise SystemExit(f"ROT 不存在：{args.name}")
        print(f"已停用：{args.name}")
        return
    if args.action == "enable":
        if not store.set_rot_enabled(args.name, True):
            raise SystemExit(f"ROT 不存在：{args.name}")
        print(f"已启用：{args.name}")
        return
    if args.action == "delete":
        if not store.delete_rot(args.name):
            raise SystemExit(f"ROT 不存在：{args.name}")
        print(f"已删除：{args.name}")


if __name__ == "__main__":
    main()
