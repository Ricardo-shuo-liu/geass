# MCP 工具接口

> [返回索引](index.md) · [项目简介](../../README.zh.md)

Geass 支持导入 MCP（Model Context Protocol）服务器，把外部工具接入桌面
Agent 与终端 CIL。配置独立保存在 `~/.geass/.mcp/servers.json`（权限
0600），不进入持久记忆；原“记忆”页签与记忆系统保持不变。

## 支持类型

- **stdio**：`command + args + env + cwd`，适用于本地 `npx` / `uvx` /
  Python 脚本等 MCP server；
- **Streamable HTTP**：`url + headers`，适用于远程部署的 MCP server。

## UI 使用

手机资源面板新增 **MCP** 页签：

- 分步表单填写服务器名称、stdio/HTTP 参数，或直接粘贴 Claude/Cursor 风格
  `{"mcpServers": {...}}` JSON；
- 添加后自动执行“连接 + `list_tools`”测试：通过才标记为可用并启用；失败
  会保留为停用记录，可修改后点 **测试** 重试；
- 服务器可整体启用/停用/永久删除；展开后可逐个工具启用/停用。未通过测试的
  服务器不能启用，也不会暴露给模型。

## 命令行

```text
geass mcp add demo --transport stdio \
  --command uvx --args mcp-server-github --env GITHUB_TOKEN=xxx
geass mcp add search --transport http --url https://example.com/mcp \
  --header "Authorization: Bearer xxx"
geass mcp import ~/claude_desktop_config.json
geass mcp list
geass mcp test demo
geass mcp enable demo              # 启用整台服务器
geass mcp disable demo search_issue # 只停用某个工具
geass mcp remove demo              # 永久删除（需要确认）
```

导入失败不会删掉记录：CLI 会保留“未通过测试”的停用条目并返回非零退出码，
修复命令/网络后可用 `geass mcp test` 重新测试。

## 运行时行为

- 启用后的 MCP 工具会以 `mcp__<服务器>__<工具>` 的函数名注入 Agent/CIL；
- 同一服务器内调用串行执行，连接按需建立并缓存，停用/删除/退出时自动关闭，
  避免遗留 stdio 子进程；
- 工具返回文本会转成模型可读结果；图片等非文本内容不会转发；
- 通过导入并启用的工具视为用户已授权，首版不额外做逐次调用审批。

## 重置

`geass reset` 会连同 `.mcp/` 一起删除全部 MCP 注册；单个服务器用
`geass mcp remove NAME` 永久删除。
