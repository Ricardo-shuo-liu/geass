# Geass

> English · [中文](README.zh.md)

> **I command you, by the power of Geass — carry out my orders.**
>
> The name and idea come from *Code Geass: Lelouch of the Rebellion*, where "Geass" is the power of absolute command: Lelouch gives an order, and the target obeys unconditionally.

Geass turns that fantasy into reality: **your PC is placed under a Geass, and your phone is the one giving orders.** Say something in text or voice, and a vision Agent watches the screen and drives the keyboard and mouse through pyautogui to finish the task, with live screen feedback streamed back to your phone — stoppable at any time.

> The core interface layer is codenamed **Paisley-Park** (a nod to the guiding Stand from *JoJo's Bizarre Adventure*): the command-and-screen hub between phone and PC.

## Features

- **Live screen** — desktop streamed to the phone in real time (LAN, 15fps by default, tunable)
- **Remote access** — Tailscale or Cloudflare quick-tunnel helper, so the phone and PC no longer need to share a network
- **Text commands** — chat-style input, e.g. "open notepad and type hello world"
- **Voice commands** — on-device Web Speech API first, falls back to recorded audio + whisper-1 transcription
- **Vision Agent** — a "screenshot → vision model → act → observe again" loop that reads the UI and operates step by step
- **pyautogui toolkit** — move, click, double-click, right-click, scroll, drag, type, key combos, wait, screenshot, finish
- **Visible terminal** — opens a real terminal window, runs a command in one shot or types into it like a human (streamed input), and captures/monitors the output (e.g. `echo "hello world"`)
- **PaddleOCR fallback** — models without vision input (e.g. `deepseek-v4-flash`) read the screen as text + normalized box coordinates (via the AI Studio remote API, no local Paddle install) instead of degrading to keyboard-only
- **SKILL interface** — `skills/*/SKILL.md` files in the standard frontmatter format are discovered, listed, and loaded on demand (`read_skill`)
- **Interruptible** — one-tap stop; the Agent also has a step limit
- **Safety boundary** — high-risk `open_terminal` commands (sudo, `rm -rf`, disk/format, power-off, uninstall, …) first pass a blocklist; a match pauses the Agent and shows an approval card on the phone (auto-denied after 30s) before the command runs; LAN token auth and one-tap stop remain in place

## Requirements

- Linux **X11** desktop (Windows/Wayland on the roadmap)
- conda env `geass` (Python 3.10)
- Any **OpenAI-compatible** model API (OpenAI / DeepSeek / local ollama…) with an `API Key`
- **PaddleOCR AI Studio token** (optional, for non-vision models) — see [Configure OCR token](#configure-ocr-token)
- Node.js 18+ — **optional** (the frontend is prebuilt in `web/dist`; only needed to modify it)

## Getting Started

### 1. Install dependencies

```bash
conda activate geass
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

Or recreate the whole pinned environment (Python 3.10, Linux x86_64) from the
included `geass.yml` in one shot — the easiest way to hand this to someone else:

```bash
conda env create -f geass.yml
conda activate geass
pip install -e .
```

`geass.yml` pins every third-party dependency but intentionally does **not**
install the Geass project itself (it isn't published on PyPI), so the final
`pip install -e .` from the repo is required. The pip/conda channels in the
file point at the TUNA mirror; replace them with `conda-forge` if it is slow
or unreachable. System-level prerequisites (X11 desktop, util-linux `script`,
a terminal emulator) are outside conda and still need to be present.

### 2. Configure API key / base URL / model

One command, positional order is **API_KEY BASE_URL MODEL**, e.g. DeepSeek:

```bash
python -m geass.config set sk-xxx https://api.deepseek.com deepseek-v4-flash
```

You can also set just one, e.g. `python -m geass.config set sk-xxx`; add
`--vision false` for DeepSeek text models. With a PaddleOCR token configured,
the Agent then reads the screen as text with coordinates (config `agent.ocr`
is on by default). Settings are saved to `~/.geass/env.toml`.

Equivalent env vars, or plain `config.toml`:

```toml
[agent]
model = "deepseek-v4-flash"
base_url = "https://api.deepseek.com"
vision = false
```

> Env vars: `GEASS_API_KEY` / `GEASS_BASE_URL` / `GEASS_MODEL` / `GEASS_TOKEN`.

### 3. Configure OCR token

Screen OCR uses the **PaddleOCR AI Studio remote jobs API** — no local
`paddlepaddle`/`paddleocr` install is needed (that library no longer ships the
new `PaddleOCR-VL-1.6` / `PP-StructureV3` models). Configure the token the
same way as the LLM API key:

```bash
python -m geass.config set --ocr-token YOUR_TOKEN --ocr-model PaddleOCR-VL-1.6
```

The token is saved to `~/.geass/env.toml` (mode 0600) and never goes into the
repo. Equivalent env vars: `GEASS_PADDLEOCR_TOKEN` / `GEASS_PADDLEOCR_MODEL` /
`GEASS_PADDLEOCR_BASE_URL` (the token also falls back to
`PADDLEOCR_MCP_AISTUDIO_ACCESS_TOKEN`). The server calls
`POST https://paddleocr.aistudio-app.com/api/v2/ocr/jobs` directly and polls
for the JSONL result; the PaddleOCR MCP JSON configs are supported as an
alternative way to obtain the token, but the runtime does not depend on MCP.

### 4. Start the server

```bash
./run.sh
```

The console prints:

```text
Geass 服务已启动
手机访问:  http://localhost:8765
访问 Token: xxxxxxxxxx
```

### 5. Connect your phone

1. Put the phone and PC on the **same Wi-Fi** (or use the remote-access helper below);
2. Open the printed address in the phone browser (replace `localhost` with the PC's LAN IP, e.g. `http://192.168.1.10:8765`);
3. Enter the Token, then watch the live screen and type or tap 🎤 to issue commands.

> Find the LAN IP with `ip addr` or `hostname -I`.
> **A fresh random Token is generated on every startup** and printed in the terminal; the old one stops working immediately.

### 6. Remote access (different networks)

You don't have to be on the same Wi-Fi. While the server is running, open a
second terminal and run:

```bash
./scripts/remote.sh
```

It auto-picks a channel and prints the URL to open on the phone:

- **Tailscale** (recommended, stable address): install Tailscale on both the
  PC and phone and sign in with the same account, then open
  `http://<tailscale-ip>:8765` — the address stays valid across restarts.
- **Cloudflare quick tunnel** (no account, nothing to install on the phone):
  downloads the `cloudflared` binary into `~/.local/bin` on first use and
  prints an `https://*.trycloudflare.com` URL. That URL changes every restart,
  and the HTTPS transport also keeps voice/PWA working over remote networks.

Pick one explicitly with:

```bash
./scripts/remote.sh --provider tailscale     # or cloudflared
```

The server still requires the printed access Token, so an exposed URL alone is
not enough to control the PC.

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
| `security.enabled` | `true` | Manual review of high-risk shell commands |
| `security.approval_timeout` | `30` | Seconds to wait for the phone's decision; timeout auto-denies (min 5s) |
| `security.patterns` | empty | Custom blocklist regexes; empty uses the built-in list, non-empty replaces it |
| `agent.model` | `gpt-5.6-terra` | Vision model (e.g. `sol` / `luna`) |
| `agent.base_url` | empty | OpenAI-compatible endpoint; DeepSeek: `https://api.deepseek.com` |
| `agent.vision` | `true` | Whether the model accepts images; non-vision models auto-degrade to text mode |
| `agent.ocr` | `true` | Use PaddleOCR (remote API) to transcribe the screen for non-vision models (text + normalized box coordinates) |
| `agent.ocr_token` | empty | AI Studio access token; set via `python -m geass.config set --ocr-token ...` |
| `agent.ocr_model` | `PaddleOCR-VL-1.6` | OCR model: `PaddleOCR-VL-1.6` or `PP-StructureV3` |
| `agent.ocr_base_url` | `https://paddleocr.aistudio-app.com` | OCR jobs API endpoint |
| `agent.ocr_timeout` | `90` | Seconds to wait for an OCR job (submit + poll) |
| `agent.terminal_timeout` | `15` | Seconds `open_terminal` waits for a command's output |
| `agent.skills_dir` | `skills` | SKILL directory (relative to the project root) |
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
| `GEASS_PADDLEOCR_TOKEN` | AI Studio OCR token (falls back to `PADDLEOCR_MCP_AISTUDIO_ACCESS_TOKEN`) |
| `GEASS_PADDLEOCR_MODEL` | Overrides `agent.ocr_model` |
| `GEASS_PADDLEOCR_BASE_URL` | Overrides `agent.ocr_base_url` |
| `GEASS_CONFIG` / `GEASS_HOME` | Project config path / user config dir (default `~/.geass`) |

### Persistence & management

Precedence: **env vars > `~/.geass/env.toml` > `config.toml` > defaults**.

- `GEASS_*` env vars used at startup are auto-saved to `~/.geass/env.toml` (mode 0600);
- CLI: `python -m geass.config show` (secrets masked); `python -m geass.config set sk-... https://api.deepseek.com deepseek-v4-flash --vision false`; OCR: `python -m geass.config set --ocr-token ... --ocr-model PaddleOCR-VL-1.6`; safety: `--security-enabled false` / `--approval-timeout 60`;
- Runtime API: `GET /api/config` (masked) and `POST /api/config` (e.g. `{"model":"...","base_url":"...","api_key":"...","vision":false}`) — applied and persisted immediately.

## Project layout

```text
geass/
  geass/          # backend (pure Python)
    agent.py      # Agent loop + pyautogui toolkit
    safety.py     # high-risk command blocklist policy
    ocr.py        # PaddleOCR AI Studio remote API backend
    skills.py     # SKILL.md loader + progressive disclosure
    asyncutil.py  # non-blocking bridge for terminal/OCR calls
    server/       # FastAPI, WebSocket, auth, approval gateway
    screen.py     # mss capture + frame streaming
    io/backend.py # input backend abstraction (PyAutoGUI)
    io/terminal.py# visible terminal sessions + output capture
  skills/         # user-provided SKILL.md skills (see skills/README.md)
  web/            # React PWA (thin phone client)
  docs/DESIGN.md  # full design & roadmap
  config.toml     # config file
  geass.yml       # frozen conda environment (one-shot setup for others)
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
- Models without vision input (e.g. `deepseek-v4-flash`): with a PaddleOCR AI Studio token configured the Agent gets screen text + box coordinates and keeps mouse tools; without OCR it falls back to keyboard-only tools
- PaddleOCR screenshots are uploaded to the AI Studio API; the token is required
- Endpoints without a transcription API (e.g. DeepSeek): set `voice.fallback_model` to empty; on-device recognition still works
- pyautogui per-key typing handles Chinese IME poorly — prefer ASCII, or a clipboard approach later
- Over plain HTTP on LAN, Web Speech API and Service Worker are unavailable: voice falls back to recorded upload, PWA degrades to a normal page
- The v1 safety boundary only reviews `open_terminal` calls that carry a command; `terminal_type` streaming input and mouse/keyboard tools are not reviewed, so bypasses remain possible (to be extended later)
- Screenshots are sent to your configured model provider; avoid sensitive content

Full design and roadmap: [docs/DESIGN.md](docs/DESIGN.md).
