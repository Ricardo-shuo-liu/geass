# POT 反思系统

> [返回索引](index.md) · [项目简介](../../README.zh.md)

POT = 反思（Reflect）→ 提炼（Distill）→ 模板（Template）：

- **Global-COT**：从历史交流痕迹中提炼的通用问题解决范式，常驻注入提示词；
- **ROT**：按某个角色视角形成的思考方式模板（类似 SKILL），按相关性自动选择
  1~2 个注入，也可手动固定；
- **trace**：每次任务的命令/计划/工具序列/结果保存在 `~/.geass/.pot/trace.jsonl`
  （上限 200 条），供空闲反思使用。

空闲时进化引擎自动反思 trace，模型输出 JSON 更新 COT 或生成新 ROT，落盘到
`~/.geass/.pot/`。管理命令：

```bash
geass pot cot show
geass pot rot list
geass pot rot show <name>
geass pot rot disable|enable|delete <name>
```

Agent 也提供 `pot_list` / `pot_use` 工具；配置项见
[configuration.md](configuration.md) 的 `pot_*`。
