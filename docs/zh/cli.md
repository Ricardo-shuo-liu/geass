# 命令行

> [返回索引](index.md) · [项目简介](../../README.zh.md)

`geass`（或 `python -m geass`）是统一命令入口：

```text
geass serve      启动服务（无参数默认）
geass cli        启动 CLI 终端助手
geass rag        管理 RAG 数据源
geass mcp        管理 MCP 工具服务器
geass config     查看/修改配置
geass check      环境自检
geass pot        管理 POT（COT/ROT）
geass reset      重置运行数据与用户配置（两次确认）
geass commands   查看全部命令
```

`geass reset` 会删除 `~/.geass/` 下的 `.memory/.skill/.rag/.mcp/.schedule/.pot/`
与 `env.toml`，恢复默认状态；必须连续两次输入 `reset` 才执行，原始文件与
仓库文件不受影响。

MCP 常用命令（详细见 [MCP 工具](mcp.md)）：

```text
geass mcp add demo --transport stdio --command uvx --args mcp-server-github
geass mcp import mcpServers.json
geass mcp list
geass mcp test demo
geass mcp enable demo            # 服务器级
geass mcp disable demo add       # 工具级
geass mcp remove demo            # 永久删除，需确认
```
