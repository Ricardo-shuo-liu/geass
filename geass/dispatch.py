"""Geass 统一命令入口：geass [serve|cli|rag|config|check|pot|reset|commands|help]。"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

COMMANDS = {
    "serve": "启动 Geass 服务（无参数时默认执行）",
    "cli": "启动 CLI 终端助手（light/deliberate 双模式）",
    "rag": "管理 RAG 数据源（add/list/remove/enable/disable/reindex）",
    "config": "查看/修改配置（python -m geass.config 的别名）",
    "check": "环境自检",
    "pot": "管理 POT 反思产物（COT/ROT）",
    "reset": "重置全部运行数据与用户配置（需要两次确认）",
    "commands": "列出全部命令与说明",
    "help": "查看全部命令与说明（等价于 commands）",
}


def geass_home() -> Path:
    return Path(os.environ.get("GEASS_HOME", str(Path.home())))


def reset_main() -> None:
    home_dir = geass_home() / ".geass"
    targets = [".memory", ".skill", ".rag", ".schedule", ".pot"]
    print("即将删除以下内容（原始文件与仓库文件不受影响）：")
    for name in targets:
        print(f"  - {home_dir / name}")
    print(f"  - {home_dir / 'env.toml'}")
    if input("输入 reset 继续：").strip() != "reset":
        print("已取消。")
        return
    if input("再次输入 reset 确认删除：").strip() != "reset":
        print("已取消。")
        return
    for name in targets:
        shutil.rmtree(home_dir / name, ignore_errors=True)
    try:
        (home_dir / "env.toml").unlink()
    except FileNotFoundError:
        pass
    print("已重置为默认状态。")


def commands_main() -> None:
    for name, description in COMMANDS.items():
        print(f"geass {name:<10} {description}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="geass",
        description="Geass 命令入口；不带子命令时启动服务",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=list(COMMANDS),
        help="子命令",
    )
    args, remaining = parser.parse_known_args(argv)
    command = args.command or "serve"
    if command == "serve":
        # 避免 geass.main 的参数守卫把子命令名当作多余参数
        sys.argv = [sys.argv[0]]
        from .main import main as serve_main

        serve_main()
        return
    if command == "cli":
        from .cli.__main__ import main as cli_main

        cli_main()
        return
    if command == "rag":
        from .rag.__main__ import main as rag_main

        sys.argv = [sys.argv[0], *remaining]
        rag_main()
        return
    if command == "config":
        from .config import main as config_main

        sys.argv = [sys.argv[0], *remaining]
        config_main()
        return
    if command == "check":
        from .check import main as check_main

        check_main()
        return
    if command == "pot":
        from .evolution.pot_cli import main as pot_main

        sys.argv = [sys.argv[0], *remaining]
        pot_main()
        return
    if command == "reset":
        reset_main()
        return
    if command in ("commands", "help"):
        commands_main()


if __name__ == "__main__":
    main()
