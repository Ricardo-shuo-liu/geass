# Geass

> [English](README.md) · 中文

> **吾以 Geass 之名命令你 —— 去完成我的指令。**
>
> 项目的名字与思想来自漫画/动画《Code Geass 反叛的鲁鲁修》中的"Geass（绝对命令）"能力：鲁鲁修对目标下达命令，对方就会无条件执行。

Geass 把这个概念变成现实：**你的电脑被"施加 Geass"，手机则是下达命令的人。** 在手机上用文字或语音说一句话，视觉 Agent 就看着电脑屏幕、通过 pyautogui 模拟键鼠自动完成任务，全程画面实时回传，你随时可以叫停。

> 附：核心接口层代号 **Paisley-Park**（致敬《JOJO 的奇妙冒险》中"为人指路"的替身），即手机与电脑之间的命令与画面中枢。

## 功能说明

- **实时屏幕**：电脑桌面实时推送到手机（局域网，默认 15fps，可调帧率与画质）
- **异地访问**：Tailscale 或 Cloudflare 临时隧道助手，手机与电脑不再需要同一网络
- **文字命令**：聊天式输入，例如"打开记事本并输入 hello world"
- **语音命令**：手机端 Web Speech API 直接识别；效果不佳或不可用时自动录音上传，由 whisper-1 兜底转写
- **视觉 Agent**：自建"截图 → 视觉模型 → 执行 → 再看结果"循环，能看懂界面、逐步骤操作
- **pyautogui 工具集**：移动、单击、双击、右键、滚动、拖动、键盘输入、组合键、等待、截图、结束任务
- **可见终端**：弹出真实终端窗口，可一键执行命令，也可像人一样逐字流式输入，并捕获/监控输出（如 `echo "hello world"`）
- **PaddleOCR 兜底**：`deepseek-v4-flash` 等不支持图像的模型不再只能盲操作，屏幕会被识别为"文本 + 归一化坐标"（走 AI Studio 远程 API，无需本地安装 Paddle），仍可点击定位
- **SKILL 接口**：自动发现 `skills/*/SKILL.md`（标准 frontmatter 格式），先看清单、需要时用 `read_skill` 渐进加载完整说明
- **随时打断**：手机端一键停止，Agent 有步数上限，不会跑飞
- **安全**：局域网 Token 认证，WebSocket 经子协议传递 token（不出现在 URL/日志中）；shell 仅经 `open_terminal` 工具按模型意图执行

## 环境要求

- Linux **X11** 桌面（当前版本仅适配 X11；Windows/Wayland 在路线图中）
- conda 环境 `geass`（Python 3.10）
- 任意 **OpenAI 兼容**的模型 API（OpenAI / DeepSeek / 本地 ollama 等）：需 `API Key`
- **PaddleOCR AI Studio Token**（可选，给非视觉模型用）：见下方[配置 OCR Token](#配置-ocr-token)
- Node.js 18+ —— **可选**：前端已经构建好（`web/dist`），只有修改前端时才需要

## 运行方法

### 1. 安装依赖

```bash
conda activate geass
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

也可以直接用仓库自带的 `geass.yml` 一键重建完整环境（Python 3.10、Linux
x86_64，已锁定全部第三方依赖版本）——这是把项目交给别人时最省事的方式：

```bash
conda env create -f geass.yml
conda activate geass
pip install -e .
```

`geass.yml` 只锁定第三方依赖，**刻意不安装 Geass 项目本身**（它没有发布到
PyPI），所以最后一步必须在仓库目录里执行 `pip install -e .`。文件里的
pip/conda 源指向清华镜像，若速度慢或无法访问可换成 `conda-forge`。另外
conda 管不到的系统依赖（X11 桌面、util-linux 的 `script`、终端模拟器）仍需
自行具备。

### 2. 配置 API Key / 端点 / 模型

一条命令搞定（按 **API_KEY、BASE_URL、MODEL** 的顺序），例如 DeepSeek：

```bash
python -m geass.config set sk-xxx https://api.deepseek.com deepseek-v4-flash
```

也可以只设置其中一项，例如 `python -m geass.config set sk-xxx`；DeepSeek
文本模型再加 `--vision false`。配置好 PaddleOCR Token 后（配置项 `agent.ocr`
默认开启），Agent 会把屏幕转成带坐标的文本继续操作。配置会写入
`~/.geass/env.toml`，之后启动无需再设置。

（可选）等价的环境变量写法，或直接在 `config.toml` 的 `[agent]` 里配置：

```toml
[agent]
model = "deepseek-v4-flash"
base_url = "https://api.deepseek.com"
vision = false
```

> 环境变量：`GEASS_API_KEY` / `GEASS_BASE_URL` / `GEASS_MODEL` / `GEASS_TOKEN`。

### 3. 配置 OCR Token

屏幕识别使用 **PaddleOCR AI Studio 远程 jobs API**，无需本地安装
`paddlepaddle` / `paddleocr`（该库已不再内置 `PaddleOCR-VL-1.6` /
`PP-StructureV3` 等新模型）。Token 的配置方式与 LLM API Key 完全一致：

```bash
python -m geass.config set --ocr-token YOUR_TOKEN --ocr-model PaddleOCR-VL-1.6
```

Token 写入 `~/.geass/env.toml`（权限 0600），不进仓库。等价环境变量：
`GEASS_PADDLEOCR_TOKEN` / `GEASS_PADDLEOCR_MODEL` /
`GEASS_PADDLEOCR_BASE_URL`（Token 也兼容 MCP 配置里的
`PADDLEOCR_MCP_AISTUDIO_ACCESS_TOKEN`）。运行时会直接调用
`POST https://paddleocr.aistudio-app.com/api/v2/ocr/jobs` 并轮询下载 JSONL
结果；PaddleOCR MCP 的 JSON 配置只是获取 Token 的另一种来源，运行时不依赖 MCP。

### 4. 启动服务

```bash
./run.sh
```

启动后控制台会打印：

```text
Geass 服务已启动
手机访问:  http://localhost:8765
访问 Token: xxxxxxxxxx
```

### 5. 手机连接

1. 手机与电脑连接**同一个 Wi-Fi**（也可用下面的异地访问方式）；
2. 手机浏览器打开控制台地址（把 `localhost` 换成电脑的局域网 IP，例如 `http://192.168.1.10:8765`）；
3. 输入 Token 后即可看到实时屏幕，直接打字或按 🎤 说话下达命令。

> 局域网 IP 可用 `ip addr` 或 `hostname -I` 查看。
> **每次启动都会生成新的随机 Token** 并打印在启动终端里，旧 Token 随即失效。

### 6. 异地访问（不在同一 Wi-Fi）

不再要求手机与电脑同一网络。服务运行期间，另开一个终端执行：

```bash
./scripts/remote.sh
```

脚本会自动选择通道并打印手机要打开的地址：

- **Tailscale**（推荐，地址长期稳定）：电脑与手机都安装 Tailscale 并登录
  同一账号，然后访问 `http://<tailscale-ip>:8765`，重启后地址不变；
- **Cloudflare 临时隧道**（免注册、手机无需装任何东西）：首次使用会下载
  `cloudflared` 到 `~/.local/bin`，然后打印 `https://*.trycloudflare.com`
  地址。该地址每次重启会变化，且 HTTPS 让语音与 PWA 在异地网络也能用。

也可以显式指定：

```bash
./scripts/remote.sh --provider tailscale     # 或 cloudflared
```

服务始终要求启动时打印的访问 Token，仅拿到网址无法控制电脑。

### （可选）修改前端后重新构建

```bash
# 无 Node 时先安装：
conda install -n geass -c conda-forge nodejs

cd web
npm install --registry=https://registry.npmmirror.com
npm run build
```

## 配置说明

个人配置（含 API Key）优先写入仓库外的 `~/.geass/env.toml`，仓库内的 `config.toml` 只保留中性默认值，方便提交 GitHub。**访问 Token 每次启动随机生成**，不写入任何文件：

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `server.host` / `server.port` | `0.0.0.0` / `8765` | 监听地址 |
| `server.token` | 每次启动随机 | 可选：显式设置则固定 Token |
| `screen.fps` | `15` | 屏幕推流帧率 |
| `screen.jpeg_quality` | `70` | 画面 JPEG 质量 |
| `screen.max_width` | `1920` | 推流画面最大宽度 |
| `agent.model` | `gpt-5.6-terra` | Agent 视觉模型（可换 `sol`/`luna`） |
| `agent.base_url` | 空 | OpenAI 兼容端点；DeepSeek 填 `https://api.deepseek.com` |
| `agent.vision` | `true` | 模型是否支持图像输入；不支持视觉的模型（如 `deepseek-v4-flash`）置 `false`，否则会自动降级为纯文本模式 |
| `agent.ocr` | `true` | 非视觉模型是否启用 PaddleOCR（远程 API），把屏幕识别为文本 + 归一化坐标 |
| `agent.ocr_token` | 空 | AI Studio 访问 Token；用 `python -m geass.config set --ocr-token ...` 设置 |
| `agent.ocr_model` | `PaddleOCR-VL-1.6` | OCR 模型：`PaddleOCR-VL-1.6` 或 `PP-StructureV3` |
| `agent.ocr_base_url` | `https://paddleocr.aistudio-app.com` | OCR jobs API 端点 |
| `agent.ocr_timeout` | `90` | 单个识别任务（提交 + 轮询）的最长等待秒数 |
| `agent.terminal_timeout` | `15` | `open_terminal` 等待命令输出的秒数 |
| `agent.skills_dir` | `skills` | SKILL 目录（相对项目根目录） |
| `agent.max_steps` | `30` | 单个任务的最大步数 |
| `agent.image_max_edge` | `1568` | 发给模型的截图长边上限（控成本） |
| `voice.fallback_model` | `whisper-1` | 语音兜底转写模型 |

环境变量：

| 变量 | 说明 |
| --- | --- |
| `GEASS_API_KEY` | API Key |
| `GEASS_BASE_URL` | 覆盖 `agent.base_url` |
| `GEASS_MODEL` | 覆盖 `agent.model` |
| `GEASS_TOKEN` | 可选：固定 Token（否则每次启动随机） |
| `GEASS_PADDLEOCR_TOKEN` | AI Studio OCR Token（兼容回退 `PADDLEOCR_MCP_AISTUDIO_ACCESS_TOKEN`） |
| `GEASS_PADDLEOCR_MODEL` | 覆盖 `agent.ocr_model` |
| `GEASS_PADDLEOCR_BASE_URL` | 覆盖 `agent.ocr_base_url` |
| `GEASS_CONFIG` / `GEASS_HOME` | 项目配置文件路径 / 用户配置目录（默认 `~/.geass`） |

### 配置持久化与管理

配置按优先级合并：**环境变量 > `~/.geass/env.toml` > `config.toml` > 默认值**。

- 启动时用过的 `GEASS_*` 环境变量会自动存入 `~/.geass/env.toml`（文件权限 0600），无需每次配置；
- 命令行管理：`python -m geass.config show` 查看（密钥脱敏）；`python -m geass.config set sk-... https://api.deepseek.com deepseek-v4-flash --vision false` 写入（位置参数依次为 API_KEY、BASE_URL、MODEL）；OCR：`python -m geass.config set --ocr-token ... --ocr-model PaddleOCR-VL-1.6`；
- 运行时接口：`GET /api/config`（脱敏查看）、`POST /api/config`（JSON 更新，如 `{"model":"...","base_url":"...","api_key":"...","vision":false}`），更新后立即生效并持久化。

## 项目结构

```text
geass/
  geass/          # 后端（纯 Python）
    agent.py      # Agent 循环与 pyautogui 工具集
    ocr.py        # PaddleOCR AI Studio 远程 API 后端
    skills.py     # SKILL.md 加载器与渐进披露
    asyncutil.py  # 终端/OCR 阻塞调用的异步桥接
    server/       # FastAPI、WebSocket、认证
    screen.py     # mss 抓屏与帧流
    io/backend.py # 输入后端抽象（PyAutoGUI 实现）
    io/terminal.py# 可见终端会话与输出捕获
  skills/         # 用户提供的 SKILL.md 技能（见 skills/README.md）
  web/            # React PWA（手机端薄壳）
  docs/DESIGN.md  # 完整设计文档与路线图
  config.toml     # 配置文件
  geass.yml       # 锁定的 conda 环境（给他人一键安装用）
```

## 开发与测试

```bash
pytest                     # 自动发现并运行 tests/ 下全部用例（见 pytest.ini）
./run_tests.sh             # 运行全部测试并把完整输出（含报错）记录到 test.log
python -m geass.main       # 后端 :8765
cd web && npm run dev      # 前端热更新 :5173（自动代理到 8765）
```

## 已知限制

- 仅支持 Linux X11；Windows/macOS/Wayland 适配在路线图中
- 不支持视觉输入的模型（如 `deepseek-v4-flash`）：配置好 PaddleOCR AI Studio Token 就能拿到屏幕文本 + 文本框中心坐标，保留鼠标点击能力；没有 OCR 时才退化为键盘-only 工具
- PaddleOCR 截图会上传到 AI Studio API，需要自行配置 Token
- DeepSeek 等不提供语音转写接口的端点：把 `voice.fallback_model` 留空以禁用兜底转写，手机端识别仍可用
- pyautogui 逐键输入对中文 IME 支持差，中文输入建议英文或后续用剪贴板方案
- 局域网 HTTP 下 Web Speech API 与 Service Worker 不可用：语音会自动走录音上传转写，PWA 退化为普通网页
- 截图会发送到你配置的模型服务商（OpenAI/DeepSeek 等），敏感内容请自行规避

完整设计与后续路线图见 [docs/DESIGN.md](docs/DESIGN.md)。
