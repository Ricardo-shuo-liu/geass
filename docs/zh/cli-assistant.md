# CLI 终端助手

> [返回索引](index.md) · [项目简介](../../README.zh.md)

CLI 是运行在电脑终端上的命令行助手（`geass cli`），与手机 GUI 控制系统
完全分离，但共享记忆、MCP、RAG、SKILL、COT/ROT 资产，目标是资产复用。

- 启动后进入 **claude-cmd 风格主菜单**：大号 ASCII Logo、方向键导航
  （↑/↓ + Enter）、emoji 图标与分组标题（会话/资产/Configuration），
  选择会话、查看资产或退出；
- **light 模式（默认）**：系统提示加载 Global-COT、1~2 个相关 ROT、SKILL
  清单、RAG 注入与记忆；工具只读资产 + 已启用 MCP 工具 + 终端命令（执行前
  确认），不做任何 GUI 键鼠操作。
- **deliberate 模式**：输入 `/deliberate` 进入，提示符变为 `Delib>`。加载
  COT，按问题选择若干 ROT 生成 2~3 个进程内 SubAgent（各绑定唯一 ROT），
  进行多轮可见辩论（TUI 标注各角色），主 Agent 汇总后与用户多轮对话；
  `/light` 或 `/exit` 退出。
- 斜杠命令：`/help /mode /deliberate /light /rot list|use /skill list|read
  /rag search /mcp list /cot show /clear /exit`。

终端界面优先使用 Rich 面板渲染，未安装 rich 时自动退回简易 REPL。
