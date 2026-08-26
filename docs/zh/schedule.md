# 定时任务

> [返回索引](index.md) · [项目简介](../../README.zh.md)

定时任务主要走**对话创建**：直接输入“今晚五点打开终端”这类命令，Agent
识别出时间意图后调用 `schedule` 工具登记，到点后复用与手动命令完全相同的
Agent 流程执行，不额外走模型规划；创建与执行状态会实时推送到手机端日志。
前端不提供专门的定时窗口，取消或查看任务可通过对话让 Agent 处理，或直接
调用下方 REST 接口。

## 持久化与确认

由 Agent 判断任务是否需要长期保存：

- **临时任务**（`persist=false`）：只保存在内存中，适合一次性近期动作；
  服务重启后自动丢失；
- **长期任务**（`persist=true`）：写入
  `~/.geass/.schedule/jobs.json`，服务重启后继续执行。

当 Agent 判断需要长期保存时，必须先向用户询问是否长期保存；用户同意后，
再向用户确认一次命令与执行时间，之后才带 `confirm=true` 完成创建。
未经用户确认不会写入磁盘。

## 行为

- 长期任务持久化在 `~/.geass/.schedule/jobs.json`（目录可用
  `agent.schedule_path` 覆盖），服务重启后仍保留；临时任务重启即失；
- 到点若已有 Agent 任务在运行，该定时任务会延迟 5 秒重试，而不是直接失败；
- 待执行的任务可在手机端取消；执行完成后记录 `done` 或 `error` 状态与结果。

## 接口

- `GET /api/schedule`：列出任务（供集成/调试）；
- `POST /api/schedule`：`{"command": "...", "run_at": epoch秒,
  "persistent": true/false}` 添加；
- `DELETE /api/schedule/{id}`：取消；
- 状态事件经 `/ws/control` 以 `schedule_status` 推送。

时间在手机端由本地时间换算为 epoch 秒；服务端按时间戳触发，不受时区显示
影响。
