# Geass

> **吾以 Geass 之名命令你 —— 去完成我的指令。**
>
> 项目的名字与思想来自漫画/动画《Code Geass 反叛的鲁鲁修》中的"Geass（绝对命令）"能力：鲁鲁修对目标下达命令，对方就会无条件执行。

Geass 把这个概念变成现实：**你的电脑被"施加 Geass"，手机则是下达命令的人。** 在手机上用文字或语音说一句话，视觉 Agent 就看着电脑屏幕、通过 pyautogui 模拟键鼠自动完成任务，全程画面实时回传，你随时可以叫停。

> 附：核心接口层代号 **Paisley-Park**（致敬《JOJO 的奇妙冒险》中"为人指路"的替身），即手机与电脑之间的命令与画面中枢。

## 功能说明

- **实时屏幕**：电脑桌面实时推送到手机（局域网，默认 15fps，可调帧率与画质）
- **文字命令**：聊天式输入，例如"打开记事本并输入 hello world"
- **语音命令**：手机端 Web Speech API 直接识别；效果不佳或不可用时自动录音上传，由 whisper-1 兜底转写
- **视觉 Agent**：自建"截图 → 视觉模型 → 执行 → 再看结果"循环，能看懂界面、逐步骤操作
- **pyautogui 工具集**：移动、单击、双击、右键、滚动、拖动、键盘输入、组合键、等待、截图、结束任务
- **随时打断**：手机端一键停止，Agent 有步数上限，不会跑飞
- **安全**：局域网 Token 认证（服务端控制台显示，可固定）；MVP 只暴露键鼠操作，无 shell/文件权限

## 环境要求

- Linux **X11** 桌面（当前版本仅适配 X11；Windows/Wayland 在路线图中）
- conda 环境 `geass`（Python 3.10）
- 任意 **OpenAI 兼容**的模型 API（OpenAI / DeepSeek / 本地 ollama 等）：需 `API Key`，DeepSeek 用户填 `DEEPSEEK_API_KEY`
- Node.js 18+ —— **可选**：前端已经构建好（`web/dist`），只有修改前端时才需要

## 运行方法

### 1. 安装依赖

```bash
conda activate geass
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2. 配置 API Key

OpenAI 用户：

```bash
export OPENAI_API_KEY=sk-...
```

DeepSeek 用户：

```bash
export DEEPSEEK_API_KEY=sk-...
export GEASS_BASE_URL=https://api.deepseek.com
```

然后在 `config.toml` 的 `[agent]` 里把模型改为你的模型名，例如：

```toml
[agent]
model = "deepseek-chat"
base_url = "https://api.deepseek.com"
```

> `base_url`、`model` 均支持传入；环境变量优先级高于配置文件。三者任选：`GEASS_API_KEY` > `OPENAI_API_KEY` > `DEEPSEEK_API_KEY`。

### 3. 启动服务

```bash
cd /home/ricaedo/geass
python -m geass.main
```

启动后控制台会打印：

```text
Geass 服务已启动
手机访问:  http://localhost:8765
访问 Token: xxxxxxxxxx
```

### 4. 手机连接

1. 手机与电脑连接**同一个 Wi-Fi**；
2. 手机浏览器打开控制台地址（把 `localhost` 换成电脑的局域网 IP，例如 `http://192.168.1.10:8765`）；
3. 输入 Token 后即可看到实时屏幕，直接打字或按 🎤 说话下达命令。

> 局域网 IP 可用 `ip addr` 或 `hostname -I` 查看。

### （可选）修改前端后重新构建

```bash
# 无 Node 时先安装：
conda install -n geass -c conda-forge nodejs

cd web
npm install --registry=https://registry.npmmirror.com
npm run build
```

## 配置说明

编辑 `config.toml`（首次启动会自动生成随机 Token，也可用环境变量 `GEASS_TOKEN` 固定）：

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `server.host` / `server.port` | `0.0.0.0` / `8765` | 监听地址 |
| `server.token` | 自动生成 | 手机访问 Token |
| `screen.fps` | `15` | 屏幕推流帧率 |
| `screen.jpeg_quality` | `70` | 画面 JPEG 质量 |
| `screen.max_width` | `1920` | 推流画面最大宽度 |
| `agent.model` | `gpt-5.6-terra` | Agent 视觉模型（可换 `sol`/`luna`） |
| `agent.base_url` | 空 | OpenAI 兼容端点；DeepSeek 填 `https://api.deepseek.com` |
| `agent.max_steps` | `30` | 单个任务的最大步数 |
| `agent.image_max_edge` | `1568` | 发给模型的截图长边上限（控成本） |
| `voice.fallback_model` | `whisper-1` | 语音兜底转写模型 |

环境变量：

| 变量 | 说明 |
| --- | --- |
| `GEASS_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` | API Key（按优先级取值） |
| `GEASS_BASE_URL` / `OPENAI_BASE_URL` | 覆盖 `agent.base_url` |
| `GEASS_TOKEN` | 覆盖访问 Token |

## 项目结构

```text
geass/
  geass/          # 后端（纯 Python）
    agent.py      # Agent 循环与 pyautogui 工具集
    server/       # FastAPI、WebSocket、认证
    screen.py     # mss 抓屏与帧流
    io/backend.py # 输入后端抽象（PyAutoGUI 实现）
  web/            # React PWA（手机端薄壳）
  docs/DESIGN.md  # 完整设计文档与路线图
  config.toml     # 配置文件
```

## 开发与测试

```bash
pytest                     # 运行测试（25 个用例）
python -m geass.main       # 后端 :8765
cd web && npm run dev      # 前端热更新 :5173（自动代理到 8765）
```

## 已知限制

- 仅支持 Linux X11；Windows/macOS/Wayland 适配在路线图中
- DeepSeek 等不提供语音转写接口的端点：把 `voice.fallback_model` 留空以禁用兜底转写，手机端识别仍可用
- pyautogui 逐键输入对中文 IME 支持差，中文输入建议英文或后续用剪贴板方案
- 局域网 HTTP 下 Web Speech API 与 Service Worker 不可用：语音会自动走录音上传转写，PWA 退化为普通网页
- 截图会发送到你配置的模型服务商（OpenAI/DeepSeek 等），敏感内容请自行规避

完整设计与后续路线图见 [docs/DESIGN.md](docs/DESIGN.md)。
