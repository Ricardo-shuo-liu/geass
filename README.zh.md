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
- **语义定位**：`find_text` 用 PaddleOCR 反查文本中心坐标、`find_element` 用 Linux AT-SPI 无障碍树查控件坐标，模型按名称定位后再点击，减少凭截图猜坐标的误差
- **pyautogui 工具集**：移动、单击、双击、右键、滚动、拖动、键盘输入、组合键、等待、截图、结束任务
- **可见终端**：弹出真实终端窗口，可一键执行命令，也可像人一样逐字流式输入，并捕获/监控输出（如 `echo "hello world"`）
- **PaddleOCR 兜底**：`deepseek-v4-flash` 等不支持图像的模型不再只能盲操作，屏幕会被识别为"文本 + 归一化坐标"（走 AI Studio 远程 API，无需本地安装 Paddle），仍可点击定位
- **SKILL 接口**：运行时从 `~/.geass/.skill/` 加载（标准 frontmatter 格式），仓库里的 `skills/` 作为种子目录自动同步到 `~/.geass/.skill/.system/`；先看清单、需要时用 `read_skill` 渐进加载完整说明
- **自判难度的任务系统**：Agent 每个任务开始时自行判断简单/困难；困难任务先 `plan` 再执行，每步结合视觉截图与 `window_info` 验证结果，检测到操作无效会自动提示换方法，手机端实时显示计划卡片
- **完整 GUI 操作**：键鼠、语义定位、窗口状态与前后帧差异检测共同组成"规划 → 执行 → 验证 → 换方法"的闭环，能够完成打开应用/页面/新标签页、填表、拖拽等稍复杂的桌面任务
- **持久记忆**：`remember` / `recall` / `forget` 把用户偏好、环境事实、失败原因跨任务保存在 `~/.geass/.memory/entries.json`，新任务自动注入相关记忆
- **空闲进化**：没有任务且空闲一段时间后，模型根据记忆和最近任务自动把高频使用模式写成新 SKILL 存入 `~/.geass/.skill/`，下次任务即可使用
- **随时打断**：手机端一键停止，Agent 有步数上限，不会跑飞
- **安全边界**：`open_terminal` 的高危 shell 命令先过黑名单（sudo、`rm -rf`、格式化、关机、卸载等），命中即在手机端弹审核卡，30 秒未回应自动拒绝，通过才执行；同时保留局域网 Token 认证与随时停止

## 任务系统与记忆

Agent 不是把每句话都塞进同一个扁平循环。任务开始时由模型自己判断难度：
简单任务（单步、状态明确）直接执行；困难任务（多步骤、跨应用、需要新建页面
或验证结果）先调用 `plan` 工具，用 `difficulty="hard"`、`goal` 和 `steps`
记录计划。之后每一步都会把计划作为上下文注入，模型可以再次调用 `plan`
更新 `current_step` 标记进度；手机端会显示一张"困难/简单"计划卡片，实时
勾选已完成步骤。

这一步是核心：鼠标和键盘只能执行动作，不能证明动作生效了。因此每个
会改变屏幕的动作执行后，系统会抓取前后两帧做像素差异检测，把
`screen_changed` 连同结果回填给模型；同时提供 `window_info` 读取活动窗口
与顶层窗口列表，`find_text`/`find_element` 做语义定位。视觉截图、OCR 文本、
无障碍树、窗口信息、屏幕差异五条通道合在一起，让模型在一步没生效时能
发现并换坐标、换方法重试，而不是机械地重复点击。

`remember` / `recall` / `forget` 提供跨任务记忆：模型可以把"默认浏览器是
Firefox""这台机器常用目录""上次任务失败的原因"写进
`~/.geass/.memory/entries.json`（默认最多 200 条），下一条命令开始前自动
把最相关的 8 条注入系统提示。删除 `~/.geass/.memory` 目录即可清空；在
`config.toml` 里把 `agent.memory_enabled` 设为 `false` 可整体关闭。
相关记忆条目会随系统提示发送给你配置的模型服务商，请勿用 `remember`
保存密码等敏感信息。

对于"打开浏览器，然后新建一个页面"这类此前容易失败的任务，`browser`
只是负责"把浏览器打开"这一步的确定性原语；整体完成靠的是规划 + 验证循环：
先 `plan`，再 `browser`（`action` 取 `open` / `new_tab` / `new_window`），
Linux 下通过 `xdg-open` 或浏览器自带参数启动，随后 `wait` +
`window_info` + `screenshot` 验证页面，没生效就换方法。浏览器打开能力
属于内置 `browser` 工具，不沉淀为 SKILL；SKILL 只保留通用、底层的工作流。

## 技能进化与运行时目录

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

## 环境要求

- Linux **X11** 桌面（当前版本仅适配 X11；Windows/Wayland 在路线图中）
- conda 环境 `geass`（Python 3.10）
- 任意 **OpenAI 兼容**的模型 API（OpenAI / DeepSeek / 本地 ollama 等）：需 `API Key`
- **PaddleOCR AI Studio Token**（可选，给非视觉模型用）：见下方[配置 OCR Token](#配置-ocr-token)
- **pyatspi**（可选，Linux）：`find_element` 控件定位需要，缺失时该工具自动返回不可用（Ubuntu/Debian 用 `sudo apt install python3-pyatspi`，**不是 pip/conda 包**）
- Node.js 18+ —— **可选**：前端已经构建好（`web/dist`），只有修改前端时才需要

## 运行方法

### 1. 安装依赖

最简单的方式是运行仓库自带的一键安装脚本：

```bash
./scripts/install.sh

# 连 Linux 系统依赖一起装（会调用 sudo，按需输入密码）
./scripts/install.sh --all
```

`scripts/install.sh` 会按 `geass.yml` 创建或更新 conda 环境 `geass`，然后用
`pip install -e .` 安装项目本体，最后运行环境自检。`--all` 额外安装
`util-linux`、`xclip/xsel`、`python3-pyatspi` 等系统包，以及 `web/` 的
npm 依赖；只需要其中一部分时可分别用 `--system` / `--web`。自定义环境名
用 `./scripts/install.sh --name myenv`，保留已有环境中的额外包用 `--no-prune`。

从一台新机器开始，可以先用 `scripts/setup.sh` clone 仓库再安装：

```bash
./scripts/setup.sh --all
```

`setup.sh` 默认直接配置当前仓库；若不在仓库内，则会 clone 到
`~/geass`（可用 `--dir` 指定位置）。尚未下载仓库时，可先取脚本：

```bash
curl -fsSL https://raw.githubusercontent.com/Ricardo-shuo-liu/geass/master/scripts/setup.sh \
  -o /tmp/geass-setup.sh
bash /tmp/geass-setup.sh --all
```

如果不想用脚本，也可以手动安装：

```bash
conda activate geass
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

`pyatspi` 不发布到 PyPI/conda-forge，不能用 pip 安装。它由 Linux 发行版
提供，`find_element` 需要时用发行版包管理器安装即可：

```bash
# Ubuntu/Debian
sudo apt install python3-pyatspi

# Fedora
sudo dnf install python3-pyatspi
```

装到系统 Python 后服务会自动兼容，无需再装进 conda 环境；如果 conda
Python 与系统 Python 的版本不同，`find_element` 会自动改用系统 Python
桥接查询。没有安装时 `find_element` 会自动返回「不可用」，`find_text`
等其他定位方式不受影响。

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
./scripts/run.sh
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

## 项目结构

```text
geass/
  geass/          # 后端（纯 Python）
    agent.py      # Agent 循环与 pyautogui 工具集
    tasks.py      # 自判难度的任务计划（plan 工具的数据模型）
    memory.py     # 跨任务持久记忆（JSON 文件存储）
    evolution.py  # 空闲进化引擎：自动把高频使用模式写成 SKILL
    safety.py     # 高危命令黑名单策略
    check.py      # 环境自检命令（python -m geass.check）
    ocr.py        # PaddleOCR AI Studio 远程 API 后端
    skills.py     # SKILL 种子同步、运行时加载与渐进披露
    asyncutil.py  # 终端/OCR 阻塞调用的异步桥接
    server/       # FastAPI、WebSocket、认证、人工审核网关
    screen.py     # mss 抓屏与帧流
    io/backend.py # 输入后端抽象（PyAutoGUI 实现）
    io/accessibility.py # Linux AT-SPI 控件与窗口查找（find_element / window_info）
    io/terminal.py# 可见终端会话与输出捕获
    io/browser.py # 默认浏览器打开页面/新标签页/新窗口
  skills/         # SKILL 种子目录：启动时同步到 ~/.geass/.skill/.system（见 skills/README.md）
  web/            # React PWA（手机端薄壳）
  docs/DESIGN.md  # 完整设计文档与路线图
  config.toml     # 配置文件
  geass.yml       # 锁定的 conda 环境（给他人一键安装用）
  scripts/
    setup.sh      # clone 仓库并调用 install.sh 配置环境
    install.sh    # 按 geass.yml 一键安装/更新依赖
    run.sh        # 启动服务
    run_tests.sh  # 运行全部测试
    remote.sh     # Tailscale/Cloudflare 异地访问助手
```

## 开发与测试

```bash
pytest                     # 自动发现并运行 tests/ 下全部用例（见 pytest.ini）
./scripts/run_tests.sh     # 运行全部测试并把完整输出（含报错）记录到 test.log
python -m geass.main       # 后端 :8765
python -m geass.check      # 检查环境与配置是否就绪（密钥只显示是否配置）
cd web && npm run dev      # 前端热更新 :5173（自动代理到 8765）
```

## 已知限制

- 仅支持 Linux X11；Windows/macOS/Wayland 适配在路线图中
- 不支持视觉输入的模型（如 `deepseek-v4-flash`）：配置好 PaddleOCR AI Studio Token 就能拿到屏幕文本 + 文本框中心坐标，保留鼠标点击能力；没有 OCR 时才退化为键盘-only 工具
- PaddleOCR 截图会上传到 AI Studio API，需要自行配置 Token
- DeepSeek 等不提供语音转写接口的端点：把 `voice.fallback_model` 留空以禁用兜底转写，手机端识别仍可用
- 中文等非 ASCII 文本自动改走剪贴板粘贴；Linux 下需要 `xclip`/`xsel` 之一，缺失时退回逐键输入（IME 支持差）
- 局域网 HTTP 下 Web Speech API 与 Service Worker 不可用：语音会自动走录音上传转写，PWA 退化为普通网页
- 安全边界 v1 只审核 `open_terminal` 带命令的调用；`terminal_type` 流式输入与键鼠工具不在审核范围，理论上仍存在绕过路径，后续版本再扩展
- `find_element` 依赖 Linux 的 AT-SPI 无障碍树；Electron 或自绘界面的应用可能不暴露控件，找不到时退回截图估计坐标
- 截图会发送到你配置的模型服务商（OpenAI/DeepSeek 等），敏感内容请自行规避
- 空闲进化会在后台调用模型并产生少量 token 消耗，且会把记忆与最近任务
  发送给模型；不需要时在 `config.toml` 设置 `agent.evolution_enabled = false`

完整设计与后续路线图见 [docs/DESIGN.md](docs/DESIGN.md)。
