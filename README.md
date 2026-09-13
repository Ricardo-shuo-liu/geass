# Geass

<p align="center">
  <img src="assets/images/geass.png" alt="Geass terminal startup banner" width="694">
</p>

> English · [中文](README.zh.md)
> Detailed docs: [English Guide](docs/en/index.md) · [中文使用手册](docs/zh/index.md) · [Design](docs/DESIGN.md)

> **I command you, by the power of Geass — carry out my orders.**

The name and idea come from *Code Geass: Lelouch of the Rebellion*: the phone
issues the order, the PC obeys. Geass runs a vision Agent on the PC and turns a
phone PWA into the remote control, with live screen streaming plus text, voice
and direct manual input. The command/agent/action orchestration layer is
codenamed **Paisley-Park**.

> **Status**: functional MVP. Current platform and precision limitations are
> documented honestly in
> [Known issues & capability boundaries](docs/en/known-issues.md) — read before
> relying on it.

## Features

- Live screen streaming and remote access (Tailscale / Cloudflare quick tunnel)
- QR pairing: `geass serve --qr` prints a single-use code so the phone connects without typing URL or Token
- Text and voice commands (Web Speech API with whisper-1 fallback)
- Vision Agent: "screenshot → model → act → verify" loop with PaddleOCR text-mode fallback
- Self-assessed task system: `plan`, multi-channel verification and automatic approach switching
- Semantic grounding: `find_text` / `find_element` / `window_info`
- Manual direct control: touch screen plus virtual mouse touchpad and keyboard rendered in the PWA, no model in the loop
- Trust layer: ghost action previews (on-screen markers, step progress, tiered review or one-tap allow) and privacy masks redacting stream and model screenshots
- Scheduled tasks: created conversationally from temporal prompts; long-term jobs persist after user confirmation
- RAG retrieval: register local files/folders as sources with vector or local lexical search injected into tasks
- MCP tools: import stdio or Streamable HTTP tools from the UI or CLI, auto-test on import, and manage each server/tool independently
- POT reflection: distills a Global-COT and role ROT templates from task traces
- CIL terminal assistant: GUI-independent light/deliberate modes reusing all assets
- Asset export: `geass export` backs up selected or all SKILL / COT / ROT assets
- Unified CLI: `geass serve/cli/export/rag/mcp/config/check/pot/reset/commands`
- Phone resource manager: visual management of memory, MCP, RAG, SKILLs, POT and scheduled tasks
- Background tasks: run in parallel with the foreground agent (GUI actions serialized by a global input lock)
- Context compression: long tasks auto-summarize early messages with originals archived
- Visible terminal: one-shot commands, streamed input, output monitoring
- Persistent memory and idle evolution: recurring usage patterns become SKILLs automatically
- SKILL system: repo `skills/` is a seed, runtime loading from `~/.geass/.skill/`
- Safety boundary, Token auth, one-tap stop

## Quick start

### 1. Install

```bash
./scripts/install.sh            # create/update the geass conda env
./scripts/install.sh --all      # also install Linux system and web dependencies
```

Manual install:

```bash
conda activate geass
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2. Configure the model

```bash
# positional order: API_KEY BASE_URL MODEL
python -m geass.config set sk-xxx https://api.deepseek.com deepseek-v4-flash
```

For non-vision models, optionally configure an OCR token:

```bash
python -m geass.config set --ocr-token YOUR_TOKEN
```

### 3. Start

```bash
./scripts/run.sh            # normal start
./scripts/run.sh --qr       # start and print a pairing QR code
```

The terminal prints the phone URL and a fresh random Token. With `--qr` it also
prints a QR code (valid for 5 minutes, single use): scan it to open the control
UI and connect without typing the URL or Token.

### 4. Connect the phone

On the same Wi-Fi, open `http://<PC-IP>:8765` in the phone browser and enter the
Token. From a different network, run in another terminal:

```bash
./scripts/remote.sh
```

## Documentation

- [English detailed guide](docs/en/index.md): installation, OCR/config, manual control, SKILLs, memory & evolution, protocol, safety, limitations
- [中文详细文档](docs/zh/index.md)
- [Design and roadmap](docs/DESIGN.md)
- [SKILL authoring guide](skills/README.md)
- [Known issues & capability boundaries](docs/en/known-issues.md): current limitations by functional area
