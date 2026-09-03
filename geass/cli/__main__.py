"""``python -m geass.cli``：启动 CLI 终端助手。"""

from __future__ import annotations

import asyncio

from openai import AsyncOpenAI

from ..config import load_config
from ..evolution import POTStore
from ..mcp import MCPManager
from ..memory import Memory
from ..rag import RAGManager
from ..rag.embeddings import provider_from_config
from ..skills import load_skills
from .session import CILSession
from .tui import TUI


def main() -> None:
    config = load_config(persist=False)
    if not (config.api_key or config.agent.base_url):
        raise SystemExit("未配置 API Key / base_url，无法启动 CIL")
    kwargs: dict = {"api_key": config.api_key or "not-needed"}
    if config.agent.base_url:
        kwargs["base_url"] = config.agent.base_url
    client = AsyncOpenAI(**kwargs)
    skills = load_skills(config.agent.skill_root, config.config_path)
    memory = (
        Memory(
            config.agent.memory_path or None,
            max_entries=config.agent.memory_max_entries,
        )
        if config.agent.memory_enabled
        else None
    )
    rag = (
        RAGManager(
            config.agent.rag_path or None,
            provider=provider_from_config(config),
        )
        if config.agent.rag_enabled
        else None
    )
    pot = POTStore(config.agent.pot_path or None) if config.agent.pot_enabled else None
    mcp = MCPManager()

    def make_session() -> CILSession:
        return CILSession(
            client=client,
            config=config.agent,
            memory=memory,
            rag=rag,
            mcp=mcp,
            skills=skills,
            pot=pot,
            tui=TUI(),
        )

    def handle_action(action: str) -> None:
        if action == "chat":
            asyncio.run(make_session().run())
        elif action == "skills":
            for skill in skills:
                print(f"- {skill.name}: {skill.description}")
        elif action == "rag":
            if rag is None:
                print("RAG 未启用")
            else:
                for source in rag.list_sources():
                    print(
                        f"- {source['name']} [{source['mode']}] "
                        f"{source['files']} 文件 / {source['chunks']} 分块"
                    )
        elif action == "mcp":
            records = mcp.servers()
            if not records:
                print("暂无 MCP 工具（可执行 geass mcp add/import 添加）")
            for record in records:
                status = "启用" if record.enabled else "停用"
                verified = "已测试" if record.verified else "测试失败"
                print(
                    f"- {record.name} [{status}/{verified}] "
                    f"{record.transport} · {len(record.tools)} 个工具"
                )
        elif action == "pot":
            if pot is None:
                print("POT 未启用")
            else:
                print("Global-COT:\n" + (pot.get_cot() or "（暂无）"))
                for rot in pot.list_rots():
                    print(f"- {rot.name}: {rot.description}")
        elif action == "memory":
            if memory is None:
                print("记忆未启用")
            else:
                for entry in memory.recall("", limit=10):
                    print(f"- {entry['key']}: {entry['value']}")
        elif action == "config":
            print(f"模型: {config.agent.model}")
            print(f"base_url: {config.agent.base_url or '（OpenAI 默认）'}")
            print(
                f"RAG: {'开' if config.agent.rag_enabled else '关'} · "
                f"POT: {'开' if config.agent.pot_enabled else '关'} · "
                f"记忆: {'开' if config.agent.memory_enabled else '关'}"
            )
        elif action == "help":
            print("Geass CLI：终端助手，与手机 GUI 分离但共享资产。")
            print("geass commands 查看全部命令；/deliberate 进入思辨模式。")

    try:
        from .menu import MenuApp

        MenuApp(on_action=handle_action).run()
    except ImportError:
        asyncio.run(make_session().run())


if __name__ == "__main__":
    main()
