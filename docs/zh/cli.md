# 命令行

> [返回索引](index.md) · [项目简介](../../README.zh.md)

`geass`（或 `python -m geass`）是统一命令入口：

```text
geass serve      启动服务（无参数默认）
geass cli        启动 CLI 终端助手
geass export     导出 SKILL / COT / ROT 资产
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

扫码配对（可选）：

```text
geass serve --qr                  # 启动并打印一次性配对二维码
geass serve --qr --qr-ttl 600     # 自定义配对码有效期（30~3600 秒）
./scripts/run.sh --qr             # 等价写法
```

二维码内容是 `/#pair=<短期配对码>`，手机扫码后由页面自动调用 `/api/pair`
换取访问 Token；配对码默认 300 秒、仅可使用一次，过期后重新启动即可。

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

资产导出（SKILL / COT / ROT）：

```text
geass export skill desktop-automation web-search --to ~/geass-assets
geass export skill --all --to ~/geass-assets
geass export cot --to ~/geass-assets
geass export rot security --to ~/geass-assets
geass export rot --all --to ~/geass-assets
geass export all --to ~/geass-assets        # 全部 SKILL + COT + ROT
```

导出目录结构为 `skills/<name>/`、`pot/cot.md`、`pot/rot/<name>.md`，并写入
`manifest.json` 记录来源与文件清单；重复导出同一名称需要加 `--force`。
ROT 默认包含已停用项，`--enabled-only` 可只导出启用中的 ROT。
