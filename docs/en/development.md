# Project layout & development

> [Back to index](index.md) · [Project overview](../../README.md)

```text
geass/
  geass/          # backend (pure Python)
    agent.py      # Agent loop + pyautogui toolkit
    tasks.py      # self-assessed task plans (plan tool model)
    memory.py     # persistent cross-task memory (JSON file)
    evolution.py  # idle evolution engine that turns usage patterns into SKILLs
    safety.py     # high-risk command blocklist policy
    check.py      # environment readiness check (python -m geass.check)
    ocr.py        # PaddleOCR AI Studio remote API backend
    skills.py     # SKILL seed sync, runtime loading + progressive disclosure
    asyncutil.py  # non-blocking bridge for terminal/OCR calls
    server/       # FastAPI, WebSocket, auth, approval gateway
    screen.py     # mss capture + frame streaming
    io/backend.py # input backend abstraction (PyAutoGUI)
    io/accessibility.py # Linux AT-SPI control/window lookup (find_element / window_info)
    io/terminal.py# visible terminal sessions + output capture
    io/browser.py # open page / new tab / new window in the default browser
  skills/         # SKILL seed directory synced into ~/.geass/.skill/.system (see skills/README.md)
  web/            # React PWA (thin phone client)
  docs/DESIGN.md  # full design & roadmap
  config.toml     # config file
  geass.yml       # frozen conda environment (one-shot setup for others)
  scripts/
    setup.sh      # clone the repo, then run install.sh
    install.sh    # one-shot install/update based on geass.yml
    run.sh        # start the server
    run_tests.sh  # run all tests
    remote.sh     # Tailscale/Cloudflare remote-access helper
```

## Development

```bash
pytest                     # auto-discovers all tests under tests/ (see pytest.ini)
./scripts/run_tests.sh     # run all tests, log full output to test.log
python -m geass serve      # backend :8765 (same as python -m geass.main)
python -m geass.check      # check env/config readiness (secrets shown as configured/not)
cd web && npm run dev      # frontend HMR :5173 (proxied to 8765)
```

## Known limitations

- Linux X11 only for now; Windows/macOS/Wayland are on the roadmap
- Models without vision input (e.g. `deepseek-v4-flash`): with a PaddleOCR AI Studio token configured the Agent gets screen text + box coordinates and keeps mouse tools; without OCR it falls back to keyboard-only tools
- PaddleOCR screenshots are uploaded to the AI Studio API; the token is required
- Endpoints without a transcription API (e.g. DeepSeek): set `voice.fallback_model` to empty; on-device recognition still works
- Non-ASCII text (e.g. Chinese) is pasted via the clipboard; on Linux this needs `xclip`/`xsel` (falls back to per-key typing otherwise)
- Over plain HTTP on LAN, Web Speech API and Service Worker are unavailable: voice falls back to recorded upload, PWA degrades to a normal page
- The v1 safety boundary only reviews `open_terminal` calls that carry a command; `terminal_type` streaming input and mouse/keyboard tools are not reviewed, so bypasses remain possible (to be extended later)
- `find_element` relies on the Linux AT-SPI accessibility tree; Electron or custom-drawn apps may not expose controls, in which case the Agent falls back to estimating from the screenshot
- Screenshots are sent to your configured model provider; avoid sensitive content
- Idle evolution makes background model calls (small token cost) and sends
  memory plus recent tasks to the model; disable with
  `agent.evolution_enabled = false` if unwanted

Full design and roadmap: [DESIGN.md](DESIGN.md).

The full, area-by-area review of current-code problems and capability
boundaries: [Known issues & capability boundaries](known-issues.md).
