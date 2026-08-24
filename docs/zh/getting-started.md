# 快速开始

> [返回索引](index.md) · [项目简介](../../README.zh.md)

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
