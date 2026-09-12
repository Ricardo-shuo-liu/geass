# Features

> [Back to index](index.md) · [Project overview](../../README.md)

- **Live screen** — desktop streamed to the phone in real time (LAN, 15fps by default, tunable)
- **QR pairing** — `geass serve --qr` prints a single-use QR code; scanning it exchanges a short-lived code for the Token and opens the control UI
- **Remote access** — Tailscale or Cloudflare quick-tunnel helper, so the phone and PC no longer need to share a network
- **Text commands** — chat-style input, e.g. "open notepad and type hello world"
- **Voice commands** — on-device Web Speech API first, falls back to recorded audio + whisper-1 transcription
- **Vision Agent** — a "screenshot → vision model → act → observe again" loop that reads the UI and operates step by step
- **Semantic grounding** — `find_text` resolves text to its center coordinates via PaddleOCR, and `find_element` resolves controls via the Linux AT-SPI accessibility tree, so the model clicks by name instead of guessing pixel positions
- **pyautogui toolkit** — move, click, double-click, right-click, scroll, drag, type, key combos, wait, screenshot, finish
- **Visible terminal** — opens a real terminal window, runs a command in one shot or types into it like a human (streamed input), and captures/monitors the output (e.g. `echo "hello world"`)
- **Manual direct control** — touch the live screen, or use the virtual mouse touchpad and virtual keyboard rendered in the PWA; events go straight to the input backend without passing through the model
- **Trust layer** — ghost action previews (click rings, drag arrows, text bubbles, step progress), tiered review (smart / confirm all / allow all) and privacy masks that redact streamed and model screenshots (off by default)
- **PaddleOCR fallback** — models without vision input (e.g. `deepseek-v4-flash`) read the screen as text + normalized box coordinates (via the AI Studio remote API, no local Paddle install) instead of degrading to keyboard-only
- **SKILL interface** — SKILLs are loaded at runtime from `~/.geass/.skill/` (standard frontmatter format); the repo `skills/` folder is only a seed synced into `~/.geass/.skill/.system/`, with on-demand `read_skill` loading
- **Self-assessed task system** — the Agent decides at the start of each task whether it is easy or hard; hard tasks first record a `plan`, then every step is verified through vision, window state and screen-change feedback, with automatic hints to switch approach when an action did nothing; the plan is shown live on the phone
- **Complete GUI operation** — mouse/keyboard, semantic grounding, window state and screen-diff feedback form a "plan → act → verify → switch approach" loop for launching apps/pages/tabs, filling forms, dragging and other moderately complex desktop tasks
- **Persistent memory** — `remember` / `recall` / `forget` store user preferences, environment facts and failure lessons across tasks in `~/.geass/.memory/entries.json`; relevant entries are injected into each new task
- **Idle evolution** — after a configurable idle period with no task running, the model reviews memory and recent tasks and automatically writes recurring usage patterns as new SKILLs under `~/.geass/.skill/`
- **Interruptible** — one-tap stop; the Agent also has a step limit
- **Safety boundary** — high-risk `open_terminal` commands (sudo, `rm -rf`, disk/format, power-off, uninstall, …) first pass a blocklist; a match pauses the Agent and shows an approval card on the phone (auto-denied after 30s) before the command runs; LAN token auth and one-tap stop remain in place
