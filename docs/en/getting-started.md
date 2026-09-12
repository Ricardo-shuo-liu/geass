# Getting started

> [Back to index](index.md) · [Project overview](../../README.md)

- Linux **X11** desktop (Windows/Wayland on the roadmap)
- conda env `geass` (Python 3.10)
- Any **OpenAI-compatible** model API (OpenAI / DeepSeek / local ollama…) with an `API Key`
- **PaddleOCR AI Studio token** (optional, for non-vision models) — see [Configure OCR token](#configure-ocr-token)
- **pyatspi** (optional, Linux) — needed by the `find_element` tool; it reports itself unavailable when missing (install with `sudo apt install python3-pyatspi` on Ubuntu/Debian; it is **not a pip/conda package**)
- Node.js 18+ — **optional** (the frontend is prebuilt in `web/dist`; only needed to modify it)

## Getting Started

### 1. Install dependencies

The easiest path is the included one-shot installer:

```bash
./scripts/install.sh

# also install Linux system packages (invokes sudo and may prompt for a password)
./scripts/install.sh --all
```

`scripts/install.sh` creates or updates the `geass` conda environment from `geass.yml`,
installs the project itself with `pip install -e .`, and runs the environment
check. `--all` additionally installs system packages such as `util-linux`,
`xclip/xsel` and `python3-pyatspi`, plus the `web/` npm dependencies; use
`--system` or `--web` for just one part. Pass `--name myenv` for a custom
environment name or `--no-prune` to keep extra packages already in the env.

On a fresh machine, `scripts/setup.sh` can clone the repository and then run
the installer:

```bash
./scripts/setup.sh --all
```

`setup.sh` configures the current repository when it is already inside one;
otherwise it clones to `~/geass` (override with `--dir`). Before the repository
exists anywhere on the machine, fetch the script first:

```bash
curl -fsSL https://raw.githubusercontent.com/Ricardo-shuo-liu/geass/master/scripts/setup.sh \
  -o /tmp/geass-setup.sh
bash /tmp/geass-setup.sh --all
```

If you prefer to install manually:

```bash
conda activate geass
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

`pyatspi` is not published on PyPI or conda-forge, so it cannot be installed
with pip. It is provided by the Linux distribution, and is only needed by
`find_element`:

```bash
# Ubuntu/Debian
sudo apt install python3-pyatspi

# Fedora
sudo dnf install python3-pyatspi
```

Once installed into the system Python, Geass loads it automatically, so it does
not need to be installed into the conda environment. When the conda Python
version differs from the system Python, `find_element` transparently switches to
a system-Python bridge for the query. Without it, `find_element` reports itself
as unavailable while `find_text` and the other tools keep working.

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
./scripts/run.sh          # normal start
./scripts/run.sh --qr     # start and print a pairing QR code
```

The console prints:

```text
Geass 服务已启动
手机访问:  http://localhost:8765
访问 Token: xxxxxxxxxx
```

### 5. Connect your phone

1. Put the phone and PC on the **same Wi-Fi** (or use the remote-access helper below);
2. **QR pairing (recommended)**: after starting with `--qr`, scan the terminal QR code with the phone camera; the control UI opens and pairs automatically;
3. Alternatively open the printed address in the phone browser (replace `localhost` with the PC's LAN IP, e.g. `http://192.168.1.10:8765`) and enter the Token;
4. Once connected, watch the live screen and type or tap 🎤 to issue commands.

> Find the LAN IP with `ip addr` or `hostname -I`.
> **A fresh random Token is generated on every startup** and printed in the terminal; the old one stops working immediately.
> The QR code carries a single-use pairing code (5-minute TTL by default) instead of the long-lived Token; rerun `./scripts/run.sh --qr` if it expires.

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
