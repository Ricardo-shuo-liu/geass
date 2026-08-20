---
name: terminal-automation
description: 当用户要求在终端执行命令、监控命令输出、以人类速度流式输入或管理长驻进程时使用
---

# terminal-automation

## 目标

打开可见终端并可靠地执行、输入与监控命令，像人一样操作终端会话。

## 工具约定

- `open_terminal`：弹出新的可见终端窗口；`command` 填命令则一键执行并
  等待输出，留空则只打开空白终端。返回 `session_id` 和捕获到的 `output`；
- `terminal_type`：向会话流式逐字输入（`interval` 控制每字符间隔，
  `press_enter=true` 输入后回车）；
- `terminal_read`：读取该会话自上次读取以来的新输出；
- `terminal_close`：关闭会话。

## 工作流

### 一次性命令

1. `open_terminal` 直接带上 `command`（如 `echo "hello world"`）；
2. 检查返回的 `output` 是否包含预期内容或错误信息；
3. 输出为空/不完整时，用返回的 `session_id` 调 `terminal_read` 再读一次；
4. 成功后按需 `terminal_close` 清理，再调用 `finish`。

### 模拟人类流式输入

1. `open_terminal` 不带 `command` 打开空白会话；
2. `terminal_type` 传 `text`，`interval` 取 0.02~0.1 秒模拟打字，
   需要提交时 `press_enter=true`；
3. `terminal_read` 确认回显与执行结果，再继续下一步输入。

### 长驻 / 慢速命令监控

1. `open_terminal` 启动命令（如编译、服务、下载）；
2. 循环 `wait` 1~3 秒 + `terminal_read` 观察增量输出；
3. 出现关键行（错误、完成标志、进度 100%）后判断成功/失败；
4. 交互式程序可 `terminal_type` 回答问题；不再需要时 `terminal_close`。

## 验收标准

- 命令输出经过验证后才算成功，不只看到「命令已执行」；
- 出错时读取 stderr/错误关键字，并在 `finish` 里说明；
- 打开的会话要么继续用于后续步骤，要么显式 `terminal_close`。

## 注意事项

- 不要用组合键手动模拟「打开终端」，一律走 `open_terminal`；
- 涉及 rm、格式化等不可逆操作前，先读当前目录并确认目标路径；
- 长命令在单条消息里发完，避免拆成多段被自动补回车。
