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
- pyautogui 工具集：move/click/double_click/right_click/scroll/drag/type_text/key_press/open_terminal/wait/screenshot/finish；
- 可见终端会话：`open_terminal` 一键执行并捕获输出，`terminal_type` 流式输入、`terminal_read` 监控输出、`terminal_close` 关闭；
- PaddleOCR 降级：不支持图像的模型（DeepSeek 等）把屏幕识别为文本 + 文本框中心坐标（AI Studio 远程 jobs API，无需本地安装 Paddle），保留鼠标定位能力；
- SKILL 生态：扫描 `skills/*/SKILL.md`（YAML frontmatter + Markdown），`list_skills`/`read_skill` 渐进披露；
- 手机端 PWA：画面显示、命令框、语音按钮、状态面板、停止按钮；
- 异地访问助手 `scripts/remote.sh`：Tailscale 或 Cloudflare 临时隧道，手机无需与电脑同一网络；
- 局域网 + Token 认证。

**明确不做（路线图见第 10 节）：** 手动直控（手指当鼠标）、SKILL 沙箱脚本执行、Windows/Wayland 适配、WebRTC、Realtime 语音。

## 5. 模块说明

- `geass/paisley_park/` 对应实现中的 `geass/agent.py` + `geass/server/`：Agent 循环、协议、编排；
- `geass/io/backend.py`：InputBackend 抽象与 PyAutoGUI 实现，坐标归一化后在此换算为像素；
- `geass/io/terminal.py`：可见终端会话（命名管道输入 + 日志输出捕获，一键/流式两种输入方式）；
- `geass/ocr.py`：PaddleOCR AI Studio 远程后端（提交截图 → 轮询 jobs → 下载 JSONL → 解析），输出文本 + 归一化坐标转写；
- `geass/skills.py`：SKILL.md 加载、清单注入与按名读取；
- `geass/asyncutil.py`：阻塞调用（OCR/终端）与事件循环之间的守护线程桥接；
- `geass/screen.py`：屏幕抓取、缩放、JPEG 编码、帧流广播；
- `geass/server/`：REST API、WebSocket、认证、共享状态；
- `skills/`：用户技能目录，服务启动时扫描；
- `scripts/remote.sh`：异地访问助手（Tailscale / cloudflared 快速隧道）；
- `web/`：React PWA。

## 6. 接口与协议

### 6.1 HTTP / WebSocket

| 端点 | 说明 |
| --- | --- |
| `GET /api/health` | 健康检查（公开） |
| `GET /api/info` | 服务信息（需 Token） |
| `POST /api/transcribe` | 上传音频 → whisper-1 转文字（需 Token） |
| `POST /api/agent/stop` | 停止当前 Agent 任务（需 Token） |
| `WS /ws/screen` | 服务端 → 客户端二进制 JPEG 帧（token 经子协议） |
| `WS /ws/control` | 双向 JSON：`command` / `stop` / `ping`，状态事件 |

Token 通过 `X-GEASS-Token` 请求头（REST）传递；WebSocket 通过 `Sec-WebSocket-Protocol` 子协议传递（客户端发送 `["geass", token]`），避免 token 出现在 URL 与访问日志中。

### 6.2 Agent 工具与坐标约定

- 坐标一律为 0–1 归一化值，相对当前截图的左上角；服务端按真实分辨率换算，截图缩放不影响定位；
- 工具 schema 见 `geass/agent.py` 的 `TOOLS`，动作命名对齐 OpenAI computer-use 词表，便于未来迁移；
- 终端工具：`open_terminal`（开窗 + 一键命令，返回 `session_id`/`output`）、`terminal_type`（流式输入）、`terminal_read`（读取新输出）、`terminal_close`（关闭会话）；
- 技能工具：`list_skills`（清单）、`read_skill`（按名加载正文与附带文件），符合渐进披露；
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
- 视觉模式发送 JPEG 截图；`agent.vision=false` 且 OCR 可用时，改为发送 PaddleOCR 文本转写（含归一化坐标），工具集保持完整；OCR 不可用才退化为键盘-only；
- 全程消息累计保留，兼容端点可享受输入缓存折扣；
- `max_steps` 步数上限防止跑飞；
- 任意时刻 `stop` 置位取消事件，Agent 在下一次边界处退出。

## 8. 安全模型

- 键鼠操作 + `open_terminal`（按模型意图在新终端窗口执行 shell 命令，无文件读写工具）；
- `read_skill` 只读取已扫描的 `SKILL.md` 与目录清单，不提供任意文件读取；技能正文只能指引 Agent 使用已有工具；
- 局域网 + Token（**每次启动随机生成**并在控制台打印，`GEASS_TOKEN` 可显式固定）；
- 手机端随时可停止；Agent 单任务有步数上限；
- 隐私：截图会发送至配置的模型服务商；启用 OCR 时还会上传至 PaddleOCR AI Studio API，敏感窗口请自行规避；后续可加本地 OCR/脱敏。

## 9. 配置

配置按优先级合并：**环境变量 > `~/.geass/env.toml` > `config.toml` > 默认值**。统一环境变量：

- `GEASS_API_KEY`：API Key；
- `GEASS_BASE_URL`：OpenAI 兼容端点（DeepSeek 填 `https://api.deepseek.com`）；
- `GEASS_MODEL`：模型名；
- `GEASS_TOKEN`：可选，显式固定 Token（默认每次启动随机生成）；
- `GEASS_PADDLEOCR_TOKEN` / `GEASS_PADDLEOCR_MODEL` / `GEASS_PADDLEOCR_BASE_URL`：AI Studio OCR Token（兼容回退 `PADDLEOCR_MCP_AISTUDIO_ACCESS_TOKEN`）、模型与端点；
- `GEASS_CONFIG` / `GEASS_HOME`：项目配置文件路径 / 用户配置目录（默认 `~/.geass`）。

持久化：启动时用过的 `GEASS_*` 环境变量会自动写入 `~/.geass/env.toml`（权限 0600），避免每次重复配置（Token 除外，每次启动随机）；也可通过 `python -m geass.config set/show` 或 `GET/POST /api/config` 管理（运行时热更新）。

视觉兼容：`agent.vision` 控制是否给模型发截图。不支持图像输入的模型（如部分 DeepSeek）会在首次收到 400（`unknown variant image_url`）时自动降级为文本模式：只保留键盘类工具，并持久化 `vision=false`。

OCR 兜底：`agent.ocr`（默认开启）在文本模式下调用 PaddleOCR AI Studio
远程 jobs API（`agent.ocr_base_url` + `agent.ocr_token`，模型
`agent.ocr_model`，支持 `PaddleOCR-VL-1.6` / `PP-StructureV3`），把截图转成
「文本 + 文本框中心坐标」；识别成功则保留鼠标工具，失败/未配置 Token 则
退化为键盘-only。`paddleocr` 本地库已不跟进新模型，因此不再内置本地推理；
`agent.ocr_timeout` 控制单个任务（提交 + 轮询）的最长等待时间。Token 与
LLM API Key 一样写入 `~/.geass/env.toml`（0600），可用
`python -m geass.config set --ocr-token ...` 配置。

终端会话：`open_terminal` 弹出可见窗口并把命令输出捕获回填；`agent.terminal_timeout` 控制等待输出上限；会话可继续用 `terminal_type` 流式输入（`interval` 可模拟人类逐字速度）、`terminal_read` 监控增量输出。

SKILL：`agent.skills_dir`（默认项目下 `skills/`）下的每个子目录放一份 `SKILL.md`。标准格式为 YAML frontmatter（`name`、`description`）+ Markdown 正文；启动时与每条命令开始前重新扫描，把名称与描述注入系统提示，Agent 匹配后调用 `read_skill` 获取全文。

默认：`0.0.0.0:8765`、fps=15、JPEG quality=70、最大宽度 1920、模型 `gpt-5.6-terra`（可改为 `deepseek-chat` / `deepseek-v4-flash` 等）、Agent 用图长边 ≤1568、步数上限 30、OCR 模型 `PaddleOCR-VL-1.6`、OCR 等待上限 90 秒、终端输出等待 15 秒。

## 10. 路线图

- **M2 混合控制**：手动直控模式（触摸 → 鼠标/键盘，含打断与接管）；
- **M3 技能生态**：SKILL.md 加载器与渐进披露、PaddleOCR AI Studio 远程识别、基础技能（desktop-automation / terminal-automation / web-search）已落地；待做：沙箱脚本执行、Realtime 语音会话；
- **M4 平台与传输**：Windows/macOS 权限适配、Wayland（ydotool）、WebRTC 低延迟；Tailscale/Cloudflare 异地访问助手已落地；待做：会话录制回放。

## 11. 成本与性能

- 模型用图降采样（长边 ≤1568）控制图像 token 成本；
- 帧流只推最新帧、队列容量 1 自动丢帧；
- 建议用屏幕变化检测替代固定 sleep（后续迭代）；
- 默认模型 `gpt-5.6-terra`，可在配置切换 `sol`/`luna`；具体可用性与计费实施时以 OpenAI API 为准。

## 12. 已知限制

- 仅支持 Linux X11（当前实现）；Windows/macOS/Wayland 待适配；
- 可见终端优先经 `x-terminal-emulator`（gnome-terminal 显式加 `--wait`，避免 dbus 激活导致客户端立即退出被误判为失败）；启动窗口时会剔除继承的 snap GTK 环境变量——从 VS Code（snap 版）集成终端启动服务时，`GTK_PATH` 等会让 gnome-terminal 加载 snap 的 GTK 模块，把 `/snap/core20` 库路径注入链接器搜索路径，导致 `__libc_pthread_init / GLIBC_PRIVATE` 崩溃；命令完成检测默认用交互式 bash 的 `PROMPT_COMMAND` 写独立边带文件（窗口里不出现 `GEASS_P1=...` 之类的内部哨兵），无 bash 时退回 sentinel 方式；输出捕获依赖 Linux 下的 `script`（无 `script` 时用 `tee` 兜底，交互式程序体验会下降）；macOS/Windows 当前仍走旧的“只开窗、不捕获”路径；
- PaddleOCR 为可选远程服务；未配置 AI Studio Token 时非视觉模型退化为键盘-only；
- pyautogui 逐键输入对中文 IME 支持差，中文输入建议英文文本或后续用剪贴板粘贴方案；
- 手机经局域网 HTTP 访问时 Web Speech API 不可用（需安全上下文），自动走录音上传转写；
- Service Worker/PWA 安装同样需要安全上下文，局域网下退化为普通网页。

## 13. 测试与验收

- 单元：坐标换算、工具映射、配置加载、帧编解码、SKILL 加载、OCR 远程 jobs 协议解析与转写、终端输出清洗；
- 集成：mock OpenAI + fake InputBackend 跑完整循环（含视觉降级与 OCR 文本模式）；WS 认证与帧通道；
- 真机 E2E：实时画面、文字/语音命令完成"打开应用 + 输入文本"、停止中断、错误 token 拒绝；
- 验收：局域网 ≥15fps、停止响应 <1s、单任务步数/费用有上限。
