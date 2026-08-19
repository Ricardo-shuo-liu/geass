# Geass 设计文档

> 本文档是 Geass 的权威设计依据，可直接修订；修订后的内容作为后续实现的输入。

## 1. 项目定位

Geass 是一个"手机指挥电脑"的系统：

- 电脑作为服务器运行 Agent，手机作为遥控器；
- 用户在手机上实时看到电脑屏幕，通过**文字或语音**下达命令；
- OpenAI 视觉 Agent 观察屏幕，调用 pyautogui 键鼠工具完成操作；
- 与 OpenClaw 相比，不依赖大量专用 API，而是把 pyautogui 作为一个通用"skill"暴露给 Agent，直接看懂并操作屏幕。

核心功能接口层命名为 **Paisley-Park**：命令入口、Agent 循环、动作执行与画面回传的统一编排中枢。

## 2. 与 OpenClaw 的对比

| 维度 | OpenClaw | Geass |
| --- | --- | --- |
| 控制方式 | 命令驱动 + 大量工具 API | 命令驱动 + 通用键鼠工具（pyautogui） |
| 屏幕反馈 | 截图式 | 实时帧流 + Agent 逐步骤截图 |
| 语音 | 视实现而定 | 端侧识别 + whisper-1 兜底 |
| 平台 | 以本地 agent 为主 | 手机 PWA，跨平台输入抽象 |

## 3. 总体架构

```text
┌────────────────┐        HTTPS/WS         ┌──────────────────────────────┐
│   手机 PWA      │ ──────────────────────▶ │        Geass 服务端           │
│  React + TS    │ ◀────────────────────── │  FastAPI + uvicorn           │
│  画面/命令/语音 │    JPEG 帧流 + 状态事件  │                              │
└────────────────┘                        │  ┌────────────────────────┐  │
                                          │  │  Paisley-Park 编排层   │  │
                                          │  │  命令→Agent 循环→动作  │  │
                                          │  └───────────┬────────────┘  │
                                          │              │               │
                                          │  ┌───────────▼────────────┐  │
                                          │  │  OpenAI SDK（视觉模型）  │  │
                                          │  └───────────┬────────────┘  │
                                          │              │ 工具调用        │
                                          │  ┌───────────▼────────────┐  │
                                          │  │ InputBackend 抽象层     │  │
                                          │  │ PyAutoGUI（X11/Win/mac）│  │
                                          │  └────────────────────────┘  │
                                          │              │               │
                                          │        ┌─────▼─────┐        │
                                          │        │ 桌面系统    │        │
                                          │        └───────────┘        │
                                          └──────────────────────────────┘
```

## 4. MVP 范围（当前实现）

**包含：**

- 实时屏幕帧流（mss 抓屏 → JPEG → WebSocket，默认 15fps）；
- 文字命令 + 语音命令（Web Speech API 优先，whisper-1 兜底转写）；
- OpenAI 兼容接口的自建 Agent 循环（截图 → 视觉模型 → 工具调用 → pyautogui 执行 → 回填 → 循环）；
- pyautogui 工具集：move/click/double_click/right_click/scroll/drag/type_text/key_press/wait/screenshot/finish；
- 手机端 PWA：画面显示、命令框、语音按钮、状态面板、停止按钮；
- 局域网 + Token 认证。

**明确不做（路线图见第 10 节）：** 手动直控（手指当鼠标）、通用 SKILL.md 加载器、PaddleOCR、Windows/Wayland 适配、WebRTC、Realtime 语音。

## 5. 模块说明

- `geass/paisley_park/` 对应实现中的 `geass/agent.py` + `geass/server/`：Agent 循环、协议、编排；
- `geass/io/backend.py`：InputBackend 抽象与 PyAutoGUI 实现，坐标归一化后在此换算为像素；
- `geass/screen.py`：屏幕抓取、缩放、JPEG 编码、帧流广播；
- `geass/server/`：REST API、WebSocket、认证、共享状态；
- `web/`：React PWA。

## 6. 接口与协议

### 6.1 HTTP / WebSocket

| 端点 | 说明 |
| --- | --- |
| `GET /api/health` | 健康检查（公开） |
| `GET /api/info` | 服务信息（需 Token） |
| `POST /api/transcribe` | 上传音频 → whisper-1 转文字（需 Token） |
| `POST /api/agent/stop` | 停止当前 Agent 任务（需 Token） |
| `WS /ws/screen?token=` | 服务端 → 客户端二进制 JPEG 帧 |
| `WS /ws/control?token=` | 双向 JSON：`command` / `stop` / `ping`，状态事件 |

Token 通过 `X-GEASS-Token` 请求头（REST）或 query 参数（WS）传递。

### 6.2 Agent 工具与坐标约定

- 坐标一律为 0–1 归一化值，相对当前截图的左上角；服务端按真实分辨率换算，截图缩放不影响定位；
- 工具 schema 见 `geass/agent.py` 的 `TOOLS`，动作命名对齐 OpenAI computer-use 词表，便于未来迁移；
- 系统提示固定规则：每次动作后重新观察截图、只做任务范围内操作、完成时调用 `finish`。

## 7. Agent 数据流

```text
用户命令 ─▶ 初始截图 ─▶ OpenAI 兼容模型(视觉+工具) ─▶ tool_call(s)
                                                    │
                                    执行(pyautogui) │ 结果回填
                                                    ▼
                             新截图 + 继续指令 ─▶ 模型 …… ─▶ finish
```

- 底层走 **Chat Completions + 工具调用**（而非 OpenAI 专属 Responses API），因此 OpenAI、DeepSeek 或任意兼容端点都能用；
- 全程消息累计保留，兼容端点可享受输入缓存折扣；
- `max_steps` 步数上限防止跑飞；
- 任意时刻 `stop` 置位取消事件，Agent 在下一次边界处退出。

## 8. 安全模型

- MVP 工具仅键鼠操作，无 shell/文件读写；
- 局域网 + Token（服务端控制台显示，`GEASS_TOKEN` 可固定）；
- 手机端随时可停止；Agent 单任务有步数上限；
- 隐私：截图会发送至 OpenAI，敏感窗口请自行规避；后续可加本地 OCR/脱敏。

## 9. 配置

见 `config.toml`，环境变量：

- `GEASS_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY`：API Key（按此优先级取值）；
- `GEASS_BASE_URL` / `OPENAI_BASE_URL`：覆盖 `agent.base_url`（OpenAI 兼容端点，DeepSeek 填 `https://api.deepseek.com`）；
- `GEASS_TOKEN`：覆盖配置中的 token；
- `GEASS_CONFIG`：指定配置文件路径。

默认：`0.0.0.0:8765`、fps=15、JPEG quality=70、最大宽度 1920、模型 `gpt-5.6-terra`（可改为 `deepseek-chat` 等）、Agent 用图长边 ≤1568、步数上限 30。

## 10. 路线图

- **M2 混合控制**：手动直控模式（触摸 → 鼠标/键盘，含打断与接管）；
- **M3 技能生态**：兼容 OpenClaw/agentskills 的 `SKILL.md` 加载器、渐进披露、沙箱脚本执行；接入 PaddleOCR（PP-OCRv5）本地识别；Realtime 语音会话；
- **M4 平台与传输**：Windows/macOS 权限适配、Wayland（ydotool）、WebRTC 低延迟、Tailscale 异地访问、会话录制回放。

## 11. 成本与性能

- 模型用图降采样（长边 ≤1568）控制图像 token 成本；
- 帧流只推最新帧、队列容量 1 自动丢帧；
- 建议用屏幕变化检测替代固定 sleep（后续迭代）；
- 默认模型 `gpt-5.6-terra`，可在配置切换 `sol`/`luna`；具体可用性与计费实施时以 OpenAI API 为准。

## 12. 已知限制

- 仅支持 Linux X11（当前实现）；Windows/macOS/Wayland 待适配；
- pyautogui 逐键输入对中文 IME 支持差，中文输入建议英文文本或后续用剪贴板粘贴方案；
- 手机经局域网 HTTP 访问时 Web Speech API 不可用（需安全上下文），自动走录音上传转写；
- Service Worker/PWA 安装同样需要安全上下文，局域网下退化为普通网页。

## 13. 测试与验收

- 单元：坐标换算、工具映射、配置加载、帧编解码；
- 集成：mock OpenAI + fake InputBackend 跑完整循环；WS 认证与帧通道；
- 真机 E2E：实时画面、文字/语音命令完成"打开应用 + 输入文本"、停止中断、错误 token 拒绝；
- 验收：局域网 ≥15fps、停止响应 <1s、单任务步数/费用有上限。
