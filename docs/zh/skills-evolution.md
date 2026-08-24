# 技能进化与运行时目录

> [返回索引](index.md) · [项目简介](../../README.zh.md)

SKILL 不再直接从仓库目录读取。仓库里的 `skills/` 只是种子：服务启动时（以及
每条命令开始前）会把它同步到运行时目录的 `~/.geass/.skill/.system/`；Agent
实际读取的是 `~/.geass/.skill/`（`~` 是用户家目录，和 `~/.geass/env.toml`、
`~/.geass/.memory` 同目录层级）。可用 `agent.skill_root` 改为任意路径。

`~/.geass/.skill/` 的结构：

```text
~/.geass/.skill/
  .system/        # 从仓库 skills/ 同步来的系统技能
  <evolved-name>/ # 空闲进化自动生成的技能
  .evolution/     # 任务历史与进化事件日志（tasks.jsonl / history.jsonl）
```

进化引擎在后台运行：当 `agent.evolution_idle_seconds`（默认 300 秒）内没有
收到命令、也没有任务在执行时，它把持久记忆和最近任务历史交给模型，由模型
判断是否值得新增一个底层、通用的 SKILL；生成后写入
`~/.geass/.skill/<name>/SKILL.md`，
下一条命令开始前就会被加载，手机端也会收到"进化生成新技能"的提示。两次进化
之间至少间隔 `agent.evolution_interval`（默认 1800 秒），自动生成数量上限为
`agent.evolution_max_skills`（默认 20）。相关配置见下方配置表。
