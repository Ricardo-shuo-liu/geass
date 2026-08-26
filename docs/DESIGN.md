# Geass 设计文档

> 本文档是 Geass 的权威设计依据，可直接修订；修订后的内容作为后续实现的输入。
> 面向用户的详细说明见 [zh/index.md](zh/index.md)（中文）与
> [en/index.md](en/index.md)（英文）；
> 项目 README 只保留简介、功能概览与快速开始。

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
- SKILL 生态：仓库 `skills/` 仅作种子，同步到运行时 `<skill_root>/.system`；
  运行时从 `<skill_root>`（默认 `~/.geass/.skill`）加载，`list_skills`/
  `read_skill` 渐进披露；
- 空闲进化系统：无任务且空闲超过阈值时，后台模型根据记忆与最近任务历史
  自动编写通用 SKILL 写入运行时目录，下次任务生效；
- 手动直控：PWA 触屏 + 网页渲染的虚拟鼠标触摸板/虚拟键盘，经
  `manual_input` 直接落到 InputBackend，不经过模型，可打断并接管 Agent；
- 定时任务：对话中由模型识别时间意图并调用 `schedule` 工具，后台到点复用
  Agent 流程执行；临时任务仅存内存、长期任务需用户确认后持久化，支持
  取消、忙碌重试与状态推送；
- RAG 检索增强：`geass/rag/` 独立包，锁定本地文件/文件夹数据源、递归读取
  分块、向量（可插拔 OpenAI 兼容 embeddings，faiss 可选）或本地词法检索，
  任务开始自动注入最相关片段并提供按需检索工具；
- 自判难度的任务系统：模型在任务开始时自行判断 easy/hard，困难任务先调用
  `plan` 记录目标与步骤；执行循环持续注入计划并可更新 `current_step`，
  每个改变屏幕的动作回填 `screen_changed` 差异检测结果，手机端展示计划卡片；
- 完整 GUI 工作流：`browser` 等动作原语与视觉截图、窗口状态、前后帧差异
  组成"规划 → 执行 → 验证 → 换方法"闭环，处理打开应用/页面/标签页、
  填表、拖拽等稍复杂任务；
- 持久记忆：`remember`/`recall`/`forget` 把跨任务信息写入
  `~/.geass/.memory`，任务开始前注入相关条目；
- 手机端 PWA：画面显示、命令框、语音按钮、状态面板、停止按钮；
- 异地访问助手 `scripts/remote.sh`：Tailscale 或 Cloudflare 临时隧道，手机无需与电脑同一网络；
- 局域网 + Token 认证。

**明确不做（路线图见第 10 节）：** 手动直控（手指当鼠标）、SKILL 沙箱脚本执行、Windows/Wayland 适配、WebRTC、Realtime 语音。

## 5. 模块说明

- `geass/paisley_park/` 对应实现中的 `geass/agent.py` + `geass/server/`：Agent 循环、协议、编排；
- `geass/tasks.py`：任务计划数据模型（difficulty/goal/steps/current_step），
  由 `plan` 工具驱动；
- `geass/memory.py`：JSON 文件持久记忆（原子写入、关键字检索、容量上限）；
- `geass/evolution.py`：空闲进化引擎（活动时间检测、任务历史、模型生成
  SKILL、事件日志与状态广播）；
- `geass/scheduler.py`：定时任务存储（`~/.geass/.schedule/jobs.json`）与
  后台触发循环（到期执行、忙碌 5 秒重试、状态事件）；
- `geass/rag/`：RAG 包（store 存储与同名镜像、chunker 分块过滤、
  embeddings 可插拔 Provider、lexical 词法检索、index 向量索引、CLI）；
- `geass/safety.py`：高危 shell 命令黑名单策略（不区分大小写正则匹配，返回是否拦截与原因）；
- `geass/check.py`：`python -m geass.check` 环境自检（密钥只显示是否配置）；
- `geass/io/backend.py`：InputBackend 抽象与 PyAutoGUI 实现，坐标归一化后在此换算为像素；
- `geass/io/accessibility.py`：Linux AT-SPI 无障碍树控件查找（供 `find_element` 使用）；conda Python 缺少兼容的 `gi/PyGObject` 时自动切换 `_atspi_bridge.py` 的系统 Python 桥接；
- `geass/io/_atspi_bridge.py`：独立 AT-SPI 桥接脚本，只依赖标准库和系统 Python 自带的 `pyatspi`；
- `geass/io/terminal.py`：可见终端会话（命名管道输入 + 日志输出捕获，一键/流式两种输入方式）；
- `geass/io/browser.py`：默认浏览器打开页面/新建标签页/新建窗口，Linux
  优先浏览器自带参数，失败回退 `xdg-open`；
- `geass/ocr.py`：PaddleOCR AI Studio 远程后端（提交截图 → 轮询 jobs → 下载 JSONL → 解析），输出文本 + 归一化坐标转写；
- `geass/skills.py`：种子目录同步（`sync_system_skills`）、运行时加载、
  清单注入与按名读取；
- `geass/asyncutil.py`：阻塞调用（OCR/终端）与事件循环之间的守护线程桥接；
- `geass/screen.py`：屏幕抓取、缩放、JPEG 编码、帧流广播；
- `geass/server/`：REST API、WebSocket、认证、共享状态与 `approval.py` 人工审核网关；
- `geass/server/manual.py`：手动直控协议（归一化坐标/按键 → InputBackend）；
- `skills/`：用户技能目录，服务启动时扫描；
- `scripts/setup.sh`：初始化入口，必要时 clone 仓库后交给 `install.sh`；
- `scripts/install.sh`：按 `geass.yml` 创建/更新 conda 环境、安装项目本体，可顺带安装系统依赖与 web/npm 依赖；
- `scripts/run.sh` / `scripts/run_tests.sh`：启动服务 / 运行测试；
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
| `GET /api/schedule` | 列出定时任务（需 Token） |
| `POST /api/schedule` | 添加定时任务 `{command, run_at}`（需 Token） |
| `DELETE /api/schedule/{id}` | 取消定时任务（需 Token） |
| `WS /ws/screen` | 服务端 → 客户端二进制 JPEG 帧（token 经子协议） |
| `WS /ws/control` | 双向 JSON：`command` / `stop` / `ping` / `approval` / `manual_input`，状态与审核事件 |

Token 通过 `X-GEASS-Token` 请求头（REST）传递；WebSocket 通过 `Sec-WebSocket-Protocol` 子协议传递（客户端发送 `["geass", token]`），避免 token 出现在 URL 与访问日志中。

安全审核协议（均走 `/ws/control`）：

- 服务端 → 客户端：`approval_request {type, id, tool, command, reason, expires_in}`、`approval_resolved {type, id, approved}`；
- 客户端 → 服务端：`approval {type, id, approved}`；
- 服务端在有挂起请求的新客户端接入时重发 `approval_request`；先到的决定生效，`stop` 或新任务会拒绝全部挂起请求。

手动直控协议（走 `/ws/control`，坐标同样为 0~1 归一化）：

- 客户端 → 服务端：`manual_input {action, ...}`；action 支持
  `move`/`click`/`double_click`/`right_click`/`drag`/`scroll`/`key`/`type`；
- 服务端直接换算像素并调用 InputBackend，不回模型；失败时返回 `error`；
- 若 Agent 任务正在运行，首个 `manual_input` 会置位取消事件，实现接管。

### 6.2 Agent 工具与坐标约定

- 坐标一律为 0–1 归一化值，相对当前截图的左上角；服务端按真实分辨率换算，截图缩放不影响定位；
- 工具 schema 见 `geass/agent.py` 的 `TOOLS`，动作命名对齐 OpenAI computer-use 词表，便于未来迁移；
- 键鼠经 `InputBackend` 落到 pyautogui：ASCII 逐键输入，中文等非 ASCII 文本走剪贴板粘贴（Linux 需要 `xclip`/`xsel`），按键名有跨平台别名归一化；
- 语义定位工具：`find_text`（PaddleOCR 反查文本，返回文本框中心归一化坐标）、`find_element`（AT-SPI 按控件名/角色查找，返回控件中心归一化坐标）；系统提示要求「点击前先用语义定位拿坐标、能用键盘就用键盘」，避免模型凭空估计坐标；
- 终端工具：`open_terminal`（开窗 + 一键命令，返回 `session_id`/`output`）、`terminal_type`（流式输入）、`terminal_read`（读取新输出）、`terminal_close`（关闭会话）；
- 技能工具：`list_skills`（清单）、`read_skill`（按名加载正文与附带文件），符合渐进披露；
- 任务与记忆工具：`plan`（记录/更新计划与难度）、`browser`（打开页面/新标签页/新窗口）、
  `remember`/`recall`/`forget`（持久记忆读写删）；
- 窗口验证工具：`window_info` 读取活动窗口与可见顶层窗口列表（AT-SPI），
  与视觉截图一起确认"新窗口/新页面是否真的打开"；
- 动作反馈：click/key/drag/scroll/type 等工具执行前后各抓一帧做像素差异，
  结果里附带 `screen_changed`/`screen_change_ratio`；未变化时提示模型换方法；
- 系统提示固定规则：每次动作后重新观察截图、只做任务范围内操作、
  困难任务先 `plan` 再执行、浏览器任务优先 `browser`、完成时调用 `finish`。

## 7. Agent 数据流

```text
用户命令 ─▶ 记忆注入 + 初始截图 ─▶ OpenAI 兼容模型(视觉+工具) ─▶ tool_call(s)
                                                    │
                                    执行(pyautogui) │ 结果回填
                                                    ▼
                             新截图 + 继续指令 ─▶ 模型 …… ─▶ finish
```

- 底层走 **Chat Completions + 工具调用**（而非 OpenAI 专属 Responses API），因此 OpenAI、DeepSeek 或任意兼容端点都能用；
- 困难任务模型先调用 `plan`；其后每一步的用户指令会附带计划与进度标记，
  模型可再次 `plan` 更新 `current_step`，简单任务可跳过规划直接执行；
- 系统提示在命令开始前注入 `memory` 中最相关的最近条目（默认 8 条），
  执行中可用 `remember`/`recall`/`forget` 读写删记忆；
- 验证与恢复是循环的主体：鼠标/键盘只执行动作，动作是否生效由视觉截图、
  OCR 文本、`window_info` 窗口状态和前后帧差异共同确认；差异检测提示
  `screen_changed=false` 时模型应换坐标或换方法，而不是盲目重试；
- 视觉模式发送 JPEG 截图；`agent.vision=false` 且 OCR 可用时，改为发送 PaddleOCR 文本转写（含归一化坐标），工具集保持完整；OCR 不可用才退化为键盘-only；
- 全程消息累计保留，兼容端点可享受输入缓存折扣；
- `max_steps` 步数上限防止跑飞；
- 任意时刻 `stop` 置位取消事件，Agent 在下一次边界处退出。

## 8. 安全模型

- 键鼠操作 + `open_terminal`（按模型意图在新终端窗口执行 shell 命令，无文件读写工具）；
- **安全边界**：`open_terminal` 的非空命令先过内置黑名单（提权、递归删除、磁盘/分区、关机重启、systemctl、SIGKILL、账户、破坏性 git、下载即执行、反弹 shell、卸载软件），命中即暂停 Agent 并广播 `approval_request`，手机端允许才执行；拒绝/超时（默认 30 秒）把错误回填给模型，让其改换方式；`[security]` 可关闭或替换正则列表；
- `read_skill` 只读取已扫描的 `SKILL.md` 与目录清单，不提供任意文件读取；技能正文只能指引 Agent 使用已有工具；
- 局域网 + Token（**每次启动随机生成**并在控制台打印，`GEASS_TOKEN` 可显式固定）；
- 手机端随时可停止；Agent 单任务有步数上限；
- 隐私：截图会发送至配置的模型服务商；启用 OCR 时还会上传至 PaddleOCR AI Studio API，敏感窗口请自行规避；持久记忆的匹配条目也会注入系统提示并发送给模型，请勿用 `remember` 保存密码等敏感信息；后续可加本地 OCR/脱敏。

## 9. 配置

配置按优先级合并：**环境变量 > `~/.geass/env.toml` > `config.toml` > 默认值**。统一环境变量：

- `GEASS_API_KEY`：API Key；
- `GEASS_BASE_URL`：OpenAI 兼容端点（DeepSeek 填 `https://api.deepseek.com`）；
- `GEASS_MODEL`：模型名；
- `GEASS_VISION_WHITELIST`：逗号分隔的视觉模型白名单（覆盖 `agent.vision_whitelist`）；
- `GEASS_TOKEN`：可选，显式固定 Token（默认每次启动随机生成）；
- `GEASS_PADDLEOCR_TOKEN` / `GEASS_PADDLEOCR_MODEL` / `GEASS_PADDLEOCR_BASE_URL`：AI Studio OCR Token（兼容回退 `PADDLEOCR_MCP_AISTUDIO_ACCESS_TOKEN`）、模型与端点；
- `GEASS_CONFIG` / `GEASS_HOME`：项目配置文件路径 / 用户配置目录（默认 `~/.geass`）。

持久化：启动时用过的 `GEASS_*` 环境变量会自动写入 `~/.geass/env.toml`（权限 0600），避免每次重复配置（Token 除外，每次启动随机）；也可通过 `python -m geass.config set/show` 或 `GET/POST /api/config` 管理（运行时热更新）。

视觉兼容：`agent.vision` 控制是否给模型发截图；`agent.vision_whitelist`（或 `GEASS_VISION_WHITELIST`）填写后优先于 `vision`：当前模型在名单内才发截图，不在名单内的模型自动走文本模式并与 PaddleOCR 配对。白名单为空时回退到 `vision` 布尔开关。不支持图像输入的模型（如部分 DeepSeek）仍会在首次收到 400（`unknown variant image_url`）时自动降级为文本模式并持久化 `vision=false`。

OCR 兜底：`agent.ocr`（默认开启）在文本模式下调用 PaddleOCR AI Studio
远程 jobs API（`agent.ocr_base_url` + `agent.ocr_token`，模型
`agent.ocr_model`，支持 `PaddleOCR-VL-1.6` / `PP-StructureV3`），把截图转成
「文本 + 文本框中心坐标」；识别成功则保留鼠标工具，失败/未配置 Token 则
退化为键盘-only。`paddleocr` 本地库已不跟进新模型，因此不再内置本地推理；
`agent.ocr_timeout` 控制单个任务（提交 + 轮询）的最长等待时间。Token 与
LLM API Key 一样写入 `~/.geass/env.toml`（0600），可用
`python -m geass.config set --ocr-token ...` 配置。

安全边界：`security.enabled`（默认开启）、`security.approval_timeout`（默认 30 秒，最低 5 秒）、`security.patterns`（自定义黑名单正则数组，留空用内置默认、填写则整体替换）。命中规则的 `open_terminal` 命令在服务端挂起并广播 `approval_request`，手机端回 `approval` 后继续；拒绝或超时作为工具错误回填，模型可换方式或 `finish`。

终端会话：`open_terminal` 弹出可见窗口并把命令输出捕获回填；`agent.terminal_timeout` 控制等待输出上限；会话可继续用 `terminal_type` 流式输入（`interval` 可模拟人类逐字速度）、`terminal_read` 监控增量输出。

SKILL：`agent.skills_dir`（默认项目下 `skills/`）只是种子目录，每个子目录放一份 `SKILL.md`（YAML frontmatter + Markdown 正文）；启动时与每条命令开始前同步到 `agent.skill_root`（默认 `~/.geass/.skill`）的 `.system/`，Agent 从运行时根目录重新扫描，把名称与描述注入系统提示，匹配后调用 `read_skill` 获取全文。自动进化生成的技能放在运行时根目录（`.system/` 之外），同名时覆盖系统技能。

进化：`agent.evolution_enabled`（默认 true）、`agent.evolution_idle_seconds`
（默认 300，最低 30）、`agent.evolution_interval`（默认 1800，最低 60）、
`agent.evolution_max_skills`（默认 20，1~100）。后台引擎每 10 秒轮询
`state.last_activity`；空闲达标后把最多 50 条记忆与最近 40 条任务历史交给
模型（优先 `response_format=json_object`，失败退回自由文本 JSON），模型
输出 `create/name/description/body`，校验并落盘到
`<skill_root>/<name>/SKILL.md`。任务历史与进化事件记录在
`<skill_root>/.evolution/`（`tasks.jsonl` / `history.jsonl`）。

记忆：`agent.memory_enabled`（默认 true）、`agent.memory_path`（默认
`~/.geass/.memory`）、`agent.memory_max_entries`（默认 200）、
`agent.memory_context_entries`（默认 8）。记忆目录与 `env.toml` 同级，
条目保存在 `entries.json`，写入采用临时文件 + 原子替换；系统提示只注入与
本任务相关的最近条目。

RAG：`agent.rag_enabled`（默认 true）、`agent.rag_inject_enabled`（默认 true）、
`agent.rag_inject_min_score`（默认 0.25）、`agent.rag_inject_hits`（默认 5）、
`agent.rag_inject_chars`（默认 3000）、`agent.rag_path`（默认
`~/.geass/.rag`）；嵌入：`agent.embedding_enabled`（默认 true）、
`agent.embedding_base_url`（默认空=词法）、`agent.embedding_model`（默认
`text-embedding-3-small`）。数据源按相对路径镜像，模型指纹不匹配时
`needs_reindex` 并降级词法。

默认：`0.0.0.0:8765`、fps=15、JPEG quality=70、最大宽度 1920、模型 `gpt-5.6-terra`（可改为 `deepseek-chat` / `deepseek-v4-flash` 等）、视觉白名单为空（回退 `vision=true`）、Agent 用图长边 ≤1568、步数上限 30、OCR 模型 `PaddleOCR-VL-1.6`、OCR 等待上限 90 秒、终端输出等待 15 秒、安全边界开启且审核超时 30 秒、记忆开启、进化开启且空闲 300 秒触发、定时任务目录 `~/.geass/.schedule`。

## 10. 路线图

- **M2 混合控制**：手动直控模式（PWA 触屏 + 虚拟键鼠、打断与接管）已落地；
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
- 中文等非 ASCII 输入走剪贴板粘贴，Linux 依赖 `xclip`/`xsel`；缺失时退回逐键输入，IME 支持差；
- 手机经局域网 HTTP 访问时 Web Speech API 不可用（需安全上下文），自动走录音上传转写；
- Service Worker/PWA 安装同样需要安全上下文，局域网下退化为普通网页；
- 安全边界 v1 只审核 `open_terminal` 带命令的调用；`terminal_type` 流式输入与键鼠工具不在审核范围，理论上仍可绕过（后续版本扩展）。
- `find_element` 与 `window_info` 依赖 Linux 的 AT-SPI；Electron/自绘应用可能不暴露控件树或窗口标题，找不到时模型退回截图估计坐标；Ubuntu/Debian 的 `python3-pyatspi` 需由 apt 安装（不是 pip 包），当 conda 环境的 Python 版本与系统 Python 不同时，会经系统 Python 桥接进程查询。
- `browser` 在 Linux 上最可靠：`new_tab`/`new_window` 优先探测
  Chrome/Chromium/Firefox 等常见浏览器 CLI，找不到才回退 `xdg-open`；
  macOS/Windows 的新建窗口语义为尽力而为，可能退化为新标签页。
- 运行时 SKILL 根目录默认在家目录的 `~/.geass/.skill/`（与 `env.toml`、
  `.memory` 同级，位于仓库之外）；可用 `agent.skill_root` 指向其他位置。
- 空闲进化会在后台调用模型并产生 token 消耗，同时把记忆与最近任务历史
  发送给模型；设置 `agent.evolution_enabled=false` 可关闭。
- 手动直控代表用户本人操作，因此绕过 `open_terminal` 审核与 Agent 步数
  上限；该通道仍受同一 Token 认证保护。

## 13. 测试与验收

- 单元：坐标换算、工具映射、pyautogui 后端（中文粘贴、按键别名、异常包装）、语义定位（find_text/find_element 与 AT-SPI 遍历）、配置加载、帧编解码、前后帧差异检测、SKILL 种子同步与运行时加载、OCR 远程 jobs 协议解析与转写、终端输出清洗、黑名单匹配与审核网关的允许/拒绝/超时/先到先决、环境自检、任务计划解析与渲染、记忆读写/检索/持久化/容量上限、进化引擎的空闲触发/生成/跳过/命名/上限/任务历史、定时任务存储/到期执行/忙碌重试/REST 增删查、RAG 分块/过滤/对账/词法/余弦/嵌入探测/指纹降级/CLI；
- 集成：mock OpenAI + fake InputBackend 跑完整循环（含视觉降级与 OCR 文本模式、plan/browser/window_info/memory 工具、屏幕差异反馈，以及审核拒绝后继续循环）；WS 认证、帧通道与审核请求/响应往返；进化引擎生成后下次扫描可见；
- 真机 E2E：实时画面、文字/语音命令完成"打开应用 + 输入文本"、停止中断、错误 token 拒绝；
- 验收：局域网 ≥15fps、停止响应 <1s、单任务步数/费用有上限。
