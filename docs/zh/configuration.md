# 配置说明

> [返回索引](index.md) · [项目简介](../../README.zh.md)

个人配置（含 API Key）优先写入仓库外的 `~/.geass/env.toml`，仓库内的 `config.toml` 只保留中性默认值，方便提交 GitHub。**访问 Token 每次启动随机生成**，不写入任何文件：

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `server.host` / `server.port` | `0.0.0.0` / `8765` | 监听地址 |
| `server.token` | 每次启动随机 | 可选：显式设置则固定 Token |
| `screen.fps` | `15` | 屏幕推流帧率 |
| `screen.jpeg_quality` | `70` | 画面 JPEG 质量 |
| `screen.max_width` | `1920` | 推流画面最大宽度 |
| `security.enabled` | `true` | 高危 shell 命令人工审核开关 |
| `security.approval_timeout` | `30` | 审核等待手机端回应的秒数，超时自动拒绝（最低 5 秒） |
| `security.patterns` | 空 | 自定义黑名单正则数组；留空用内置默认，填写后整体替换默认 |
| `agent.model` | `gpt-5.6-terra` | Agent 视觉模型（可换 `sol`/`luna`） |
| `agent.base_url` | 空 | OpenAI 兼容端点；DeepSeek 填 `https://api.deepseek.com` |
| `agent.vision` | `true` | 模型是否支持图像输入；不支持视觉的模型（如 `deepseek-v4-flash`）置 `false`，否则会自动降级为纯文本模式 |
| `agent.vision_whitelist` | 空 | 支持图像输入的模型白名单（逗号分隔）；填写后以白名单为准：模型在名单内直接发截图，不在名单内自动与 PaddleOCR 配对 |
| `agent.ocr` | `true` | 非视觉模型是否启用 PaddleOCR（远程 API），把屏幕识别为文本 + 归一化坐标 |
| `agent.ocr_token` | 空 | AI Studio 访问 Token；用 `python -m geass.config set --ocr-token ...` 设置 |
| `agent.ocr_model` | `PaddleOCR-VL-1.6` | OCR 模型：`PaddleOCR-VL-1.6` 或 `PP-StructureV3` |
| `agent.ocr_base_url` | `https://paddleocr.aistudio-app.com` | OCR jobs API 端点 |
| `agent.ocr_timeout` | `90` | 单个识别任务（提交 + 轮询）的最长等待秒数 |
| `agent.terminal_timeout` | `15` | `open_terminal` 等待命令输出的秒数 |
| `agent.skills_dir` | `skills` | 种子 SKILL 目录（相对项目根目录），同步到 `~/.geass/.skill/.system/` |
| `agent.skill_root` | 空 | 运行时 SKILL 根目录；留空用 `~/.geass/.skill` |
| `agent.memory_enabled` | `true` | 是否启用持久记忆（`remember`/`recall`/`forget`） |
| `agent.memory_path` | 空 | 记忆目录路径；留空用 `~/.geass/.memory`（条目在 `entries.json`） |
| `agent.memory_max_entries` | `200` | 记忆最多保留的条目数 |
| `agent.memory_context_entries` | `8` | 每条任务注入系统提示的相关记忆条数 |
| `agent.evolution_enabled` | `true` | 是否启用空闲进化系统 |
| `agent.evolution_idle_seconds` | `300` | 空闲多少秒后触发进化（最低 30 秒） |
| `agent.evolution_interval` | `1800` | 两次进化的最小间隔秒数（最低 60 秒） |
| `agent.evolution_max_skills` | `20` | 自动生成技能的数量上限（1~100） |
| `agent.max_steps` | `30` | 单个任务的最大步数 |
| `agent.image_max_edge` | `1568` | 发给模型的截图长边上限（控成本） |
| `voice.fallback_model` | `whisper-1` | 语音兜底转写模型 |

环境变量：

| 变量 | 说明 |
| --- | --- |
| `GEASS_API_KEY` | API Key |
| `GEASS_BASE_URL` | 覆盖 `agent.base_url` |
| `GEASS_MODEL` | 覆盖 `agent.model` |
| `GEASS_VISION_WHITELIST` | 逗号分隔的视觉模型白名单，覆盖 `agent.vision_whitelist` |
| `GEASS_TOKEN` | 可选：固定 Token（否则每次启动随机） |
| `GEASS_PADDLEOCR_TOKEN` | AI Studio OCR Token（兼容回退 `PADDLEOCR_MCP_AISTUDIO_ACCESS_TOKEN`） |
| `GEASS_PADDLEOCR_MODEL` | 覆盖 `agent.ocr_model` |
| `GEASS_PADDLEOCR_BASE_URL` | 覆盖 `agent.ocr_base_url` |
| `GEASS_CONFIG` / `GEASS_HOME` | 项目配置文件路径 / 用户配置目录（默认 `~/.geass`） |

### 配置持久化与管理

配置按优先级合并：**环境变量 > `~/.geass/env.toml` > `config.toml` > 默认值**。

- 启动时用过的 `GEASS_*` 环境变量会自动存入 `~/.geass/env.toml`（文件权限 0600），无需每次配置；
- 命令行管理：`python -m geass.config show` 查看（密钥脱敏）；`python -m geass.config set sk-... https://api.deepseek.com deepseek-v4-flash --vision false` 写入（位置参数依次为 API_KEY、BASE_URL、MODEL）；OCR：`python -m geass.config set --ocr-token ... --ocr-model PaddleOCR-VL-1.6`；视觉白名单：`--vision-whitelist gpt-5.6-terra,sol`；记忆：`--memory-enabled false` / `--memory-path ...`；技能与进化：`--skill-root ...` / `--evolution-enabled false` / `--evolution-idle-seconds 600`；安全边界：`--security-enabled false` / `--approval-timeout 60`；
- 运行时接口：`GET /api/config`（脱敏查看）、`POST /api/config`（JSON 更新，如 `{"model":"...","base_url":"...","api_key":"...","vision":false}`），更新后立即生效并持久化。
