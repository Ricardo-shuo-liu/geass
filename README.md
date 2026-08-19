# Geass

> English · [中文](README.zh.md)

> **I command you, by the power of Geass — carry out my orders.**
>
> The name and idea come from *Code Geass: Lelouch of the Rebellion*, where "Geass" is the power of absolute command: Lelouch gives an order, and the target obeys unconditionally.

Geass turns that fantasy into reality: **your PC is placed under a Geass, and your phone is the one giving orders.** Say something in text or voice, and a vision Agent watches the screen and drives the keyboard and mouse through pyautogui to finish the task, with live screen feedback streamed back to your phone — stoppable at any time.

> The core interface layer is codenamed **Paisley-Park** (a nod to the guiding Stand from *JoJo's Bizarre Adventure*): the command-and-screen hub between phone and PC.

## Features

- **Live screen** — desktop streamed to the phone in real time (LAN, 15fps by default, tunable)
- **Text commands** — chat-style input, e.g. "open notepad and type hello world"
- **Voice commands** — on-device Web Speech API first, falls back to recorded audio + whisper-1 transcription
- **Vision Agent** — a "screenshot → vision model → act → observe again" loop that reads the UI and operates step by step
- **pyautogui toolkit** — move, click, double-click, right-click, scroll, drag, type, key combos, wait, screenshot, finish
- **Terminal tool** — `open_terminal` runs a shell command in a **new visible terminal window** (e.g. `echo hello world`)
- **Interruptible** — one-tap stop; the Agent also has a step limit
- **Secure** — LAN token auth; WebSocket auth goes through the subprotocol (no token in URLs/logs); shell runs only via the `open_terminal` tool

## Requirements

- Linux **X11** desktop (Windows/Wayland on the roadmap)
- conda env `geass` (Python 3.10)
- Any **OpenAI-compatible** model API (OpenAI / DeepSeek / local ollama…) with an `API Key`
- Node.js 18+ — **optional** (the frontend is prebuilt in `web/dist`; only needed to modify it)

## Getting Started

### 1. Install dependencies

```bash
conda activate geass
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2. Configure API key / base URL / model

One command, positional order is **API_KEY BASE_URL MODEL**, e.g. DeepSeek:

```bash
python -m geass.config set sk-xxx https://api.deepseek.com deepseek-v4-flash
```

You can also set just one, e.g. `python -m geass.config set sk-xxx`; add `--vision false` as needed. Settings are saved to `~/.geass/env.toml`.

Equivalent env vars, or plain `config.toml`:

```toml
[agent]
model = "deepseek-v4-flash"
base_url = "https://api.deepseek.com"
vision = false
```

> Env vars: `GEASS_API_KEY` / `GEASS_BASE_URL` / `GEASS_MODEL` / `GEASS_TOKEN`.

### 3. Start the server

```bash
./run.sh
```

The console prints:

```text
Geass 服务已启动
手机访问:  http://localhost:8765
访问 Token: xxxxxxxxxx
```

### 4. Connect your phone

1. Put the phone and PC on the **same Wi-Fi**;
2. Open the printed address in the phone browser (replace `localhost` with the PC's LAN IP, e.g. `http://192.168.1.10:8765`);
3. Enter the Token, then watch the live screen and type or tap 🎤 to issue commands.

> Find the LAN IP with `ip addr` or `hostname -I`.
> **A fresh random Token is generated on every startup** and printed in the terminal; the old one stops working immediately.

### (Optional) Rebuild the frontend

```bash
# install Node first if missing:
conda install -n geass -c conda-forge nodejs

cd web
npm install --registry=https://registry.npmmirror.com
npm run build
```

## Configuration

Personal settings (including the API key) live in `~/.geass/env.toml` outside the repo; `config.toml` keeps neutral defaults so it is safe to commit. The **access Token is randomly regenerated on every startup** and never written to a file:

| Key | Default | Description |
| --- | --- | --- |
| `server.host` / `server.port` | `0.0.0.0` / `8765` | Listen address |
| `server.token` | random per startup | optional: set explicitly to pin it |
| `screen.fps` | `15` | Stream FPS |
| `screen.jpeg_quality` | `70` | JPEG quality |
| `screen.max_width` | `1920` | Max stream width |
| `agent.model` | `gpt-5.6-terra` | Vision model (e.g. `sol` / `luna`) |
| `agent.base_url` | empty | OpenAI-compatible endpoint; DeepSeek: `https://api.deepseek.com` |
| `agent.vision` | `true` | Whether the model accepts images; non-vision models auto-degrade to text mode |
| `agent.max_steps` | `30` | Max steps per task |
| `agent.image_max_edge` | `1568` | Long edge cap for screenshots sent to the model |
| `voice.fallback_model` | `whisper-1` | Voice fallback transcription model |

Environment variables:

| Variable | Description |
| --- | --- |
| `GEASS_API_KEY` | API key |
| `GEASS_BASE_URL` | Overrides `agent.base_url` |
| `GEASS_MODEL` | Overrides `agent.model` |
| `GEASS_TOKEN` | Optional: pin the Token (otherwise random per startup) |
| `GEASS_CONFIG` / `GEASS_HOME` | Project config path / user config dir (default `~/.geass`) |

### Persistence & management

Precedence: **env vars > `~/.geass/env.toml` > `config.toml` > defaults**.

- `GEASS_*` env vars used at startup are auto-saved to `~/.geass/env.toml` (mode 0600);
- CLI: `python -m geass.config show` (secrets masked); `python -m geass.config set sk-... https://api.deepseek.com deepseek-v4-flash --vision false`;
- Runtime API: `GET /api/config` (masked) and `POST /api/config` (e.g. `{"model":"...","base_url":"...","api_key":"...","vision":false}`) — applied and persisted immediately.

## Project layout

```text
geass/
  geass/          # backend (pure Python)
    agent.py      # Agent loop + pyautogui toolkit
    server/       # FastAPI, WebSocket, auth
    screen.py     # mss capture + frame streaming
    io/backend.py # input backend abstraction (PyAutoGUI)
  web/            # React PWA (thin phone client)
  docs/DESIGN.md  # full design & roadmap
  config.toml     # config file
```

## Development

```bash
pytest                     # auto-discovers all tests under tests/ (see pytest.ini)
./run_tests.sh             # run all tests, log full output to test.log
python -m geass.main       # backend :8765
cd web && npm run dev      # frontend HMR :5173 (proxied to 8765)
```

## Known limitations

- Linux X11 only for now; Windows/macOS/Wayland are on the roadmap
- Models without vision input (e.g. some DeepSeek models) auto-degrade to text mode: keyboard-only tools, no mouse targeting
- Endpoints without a transcription API (e.g. DeepSeek): set `voice.fallback_model` to empty; on-device recognition still works
- pyautogui per-key typing handles Chinese IME poorly — prefer ASCII, or a clipboard approach later
- Over plain HTTP on LAN, Web Speech API and Service Worker are unavailable: voice falls back to recorded upload, PWA degrades to a normal page
- Screenshots are sent to your configured model provider; avoid sensitive content

Full design and roadmap: [docs/DESIGN.md](docs/DESIGN.md).
