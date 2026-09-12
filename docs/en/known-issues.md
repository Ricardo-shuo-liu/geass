# Known issues and capability boundaries (current-code review)

> [Back to index](index.md) · [Project overview](../../README.md)

This page is based on the September 2026 code review. It groups the problems and
limitations of the current implementation by functional area and is intended as
input for development planning, the roadmap, and the upcoming privacy-mask /
action-preview / undo / session-replay work.
[development.md](development.md) lists the short version of the known
limitations; this page expands them by area and describes the current state
without promising fixes. The full design and roadmap live in
[DESIGN.md](../DESIGN.md).

## Platform and desktop environment

- The complete input + visible-terminal + semantic-locating loop currently only
  works on Linux X11. On Windows/macOS, pyautogui and terminal/browser
  "open a window" paths are best-effort only; Wayland is unsupported. Window
  movement, DPI/scaling, or desktop-session differences can invalidate
  coordinates.
- Only the first physical monitor is captured and controlled
  (`mss.monitors[1]`), and coordinates are normalized against the primary
  screen. Targets on a second monitor cannot be seen or reached.
- There is no deterministic `window_activate` / `app_launch` tool: the Agent
  cannot directly wake, raise, or focus a minimized/background window; it has to
  guess through the launcher, clicks, or keyboard. System trays and
  always-running resident apps are especially unreliable.
- `window_info` only reads the window list and active state; it does not provide
  an "activate window / switch focus" action. Electron, custom-drawn apps, or
  windows without AT-SPI exposure may have no detectable title or controls.
- Over plain HTTP on a LAN, Web Speech API and Service Worker are unavailable:
  voice falls back to recorded upload and the PWA degrades to a normal page.

## Perception and state verification

- The Agent's input is mainly a full-screen screenshot or OCR text. There is no
  persistent representation of DOM, AT-SPI control trees, layout/hierarchy, or
  structure inside a window; the model mostly "guesses coordinates from pixels".
- `find_text` / `find_element` only return a target center point. They do not
  return a clickable region, control state, or an action that can be performed
  directly on the control. Text-less icons, graphical buttons, and
  Electron/custom-drawn UIs are often not found.
- PaddleOCR is a remote AI Studio service; a single recognition can take up to
  about 90 seconds. In text mode, every "observe the screen" step may trigger a
  remote transcription, making long tasks slow and costly. OCR represents text
  and bounding boxes only; it cannot represent icons, colors, hierarchy, or
  visual layout.
- Screen-change detection compares the whole screen as a 64x64 grayscale image
  and waits a fixed ~0.18 seconds after an action. There are no region, text, or
  window assertions; animations, cursors, and loading states cause false
  positives, while slow loading is often misread as "the screen did not change".
- There is no `wait_until` / `assert` style conditional-wait tool. `wait` is a
  fixed sleep capped at 10 seconds per call and cannot express "wait until a
  title appears" or "wait until an input is editable".
- When the model returns several tool calls in one response, the tools run
  sequentially but a new screenshot is only appended after the whole batch; no
  observation can be inserted between calls. `screenshot` itself does not return
  an image; the loop attaches one after the batch, so its meaning as an
  "immediate mid-batch observation" is not real.
- When context compression triggers, early screenshots are removed and replaced
  by a text summary, so the model loses part of the earlier visual state; the
  summary is model-generated and may lose information.

## Mouse and keyboard granularity

- Only discrete actions exist:
  move/click/double_click/right_click/scroll/drag/type_text/key_press. There is
  no mouse_down/mouse_up, key_down/key_up, long press, or press-and-move, so
  gestures that need continuous feedback, selections, intermediate drag states,
  or drawing paths cannot be expressed.
- `drag` is a one-shot "from A to B", not a drag with an intermediate path;
  `scroll` accepts no target coordinates, so if the cursor is not over the
  target area the scroll can affect the wrong window.
- Coordinates are full-screen normalized values, not window-relative. If the
  target window moves, resizes, or changes focus, coordinates remembered by the
  model easily become stale.
- Non-ASCII text (e.g. Chinese) is pasted via the clipboard; Linux depends on
  `xclip`/`xsel`. If missing, it falls back to per-key typing with poor IME
  support. The clipboard is temporarily overwritten and then restored, which can
  still disturb content the user was holding.
- The Agent has no dedicated clipboard read/write tool, so it cannot reliably
  "copy visible text and paste it somewhere else"; keyboard input has no
  layout/locale awareness.

## Visible terminal and browser

- Full visible-terminal output capture is only reliable on Linux with bash and a
  common terminal emulator. Interactive programs such as vi, htop, or ssh have a
  degraded experience; command output waits for 15 seconds by default, so long
  commands time out easily.
- On macOS/Windows, `open_terminal` is mostly "open a window without capturing
  output"; the `terminal_type/read/close` session semantics only work on Linux.
- The safety boundary only reviews `open_terminal` and `terminal_type` when the
  input hits the blocklist or can execute. `key_press`, `type_text`, ordinary
  terminal commands, and manual direct control are outside the review scope, so
  dangerous un-reviewed operations can in theory be composed.
- `browser` is only deterministic browser launching / URL opening; there is no
  DOM, CDP, or page-event channel. Subsequent address-bar locating, search-box
  focusing, and page-content reading all fall back to screenshots/OCR. On
  macOS/Windows, `new_window` semantics are best-effort and may degrade to a new
  tab.
- Apart from `open_terminal`, there are no general file read/write tools; file
  operations mostly rely on the shell, and the Agent has no structured
  read-file/write-file/list-directory tools.

## Manual direct control

- Touch/virtual touchpad supports only single-pointer click, double-click,
  right-click, drag, and scroll. There is no pinch zoom, multi-touch,
  stylus/pressure, or an intermediate state while dragging to a moving target.
- Drags are composed from a start event plus an end event, not a full trajectory.
  Manual operations leave no trajectory or replay data, so they cannot serve as
  training material for "teaching the Agent" later.
- The first manual input marks the Agent as cancelled, but if the Agent is
  blocked waiting for an approval, the manual input does not reject/resolve that
  approval; the user must stop or wait for the timeout. The "interrupt and take
  over" behavior has a gap at that boundary.
- Manual direct control bypasses the Agent step limit and shell review and is
  currently neither audited nor recorded. It represents the user operating the
  computer, but mistakes also have no undo.

## Task lifecycle and the intelligence loop

- Only one foreground Agent task is allowed at a time; new commands during
  execution are rejected as busy. There is no mechanism to pause the current
  task and insert a new instruction.
- `plan` is only external text notes, not an enforced state machine: the model
  may skip the plan, fail to update `current_step`, or even claim verification
  without evidence; the loop does not enforce plan consistency.
- There are no checkpoints, persistent task states, or resume/continue
  capabilities, and no `human_checkpoint` semantics for waiting on physical
  actions such as QR-code login. A single Agent task defaults to a 30-step
  limit, and waiting consumes steps.
- There is no undo/rollback. Context compression and failure fallbacks do not
  keep reproducible action history; after a task only a lightweight trace is kept
  for evolution, not an auditable user-facing replay.
- Background tasks are independent and have no shared plan, coordination layer,
  or result merging. When several Agents run concurrently, mouse/keyboard
  actions are serialized by a global lock, but foreground and background tasks
  can both raise approval requests while the approval protocol does not carry a
  `task_id`, making it hard for the phone UI to tell which task a request came
  from.

## Trust layer (action preview & privacy masks)

- The visual delay only makes actions observable and interceptable; it is not a
  transactional boundary. At 0ms or in "allow all" mode there is no preview
  step (the terminal blocklist review still applies).
- Confirmation-required actions are rejected when no phone control client is
  connected; unattended background/scheduled tasks should use "allow all" or
  keep the phone online.
- Privacy masks only cover the primary monitor and never block input; they are
  skipped entirely while the master switch is off.
- Auto-detection is on-demand and relies on AT-SPI password fields plus OCR
  keyword matches; custom-drawn UIs, a missing OCR token or unmatched keywords
  cause misses. Suggestions are best-effort, never automatic redaction.
- This phase has no undo or session replay; `action_proposal.undoable` is
  always false.

## Memory, RAG, SKILL, and evolution

- Persistent memory is key-value plus keyword retrieval, with no semantic/vector
  search, expiration policy, permission isolation, or encryption. It is capped
  at about 200 entries and 8000 characters per value, and prompt-injection
  defense is only a keyword heuristic.
- RAG only registers local files/folders with a built-in extension whitelist and
  does not watch files for live changes; re-running `add`/reindex is required
  for reconciliation. URL/web/database sources are not supported.
- SKILLs are Markdown guidance only: no executable scripts, sandbox, dry-run, or
  automatic acceptance tests. `read_skill` only reads scanned skill directories
  and does not offer arbitrary file reads.
- Idle evolution and POT reflection make background model calls and send memory
  plus task history to the model provider. Generated SKILLs/ROTs are not
  replayed or verified and may duplicate, be low quality, or contain injected
  content; only simple phrase filtering is applied.

## MCP

- MCP tools have no spatial/screen semantics and cannot participate in
  target-coordinate previews or corrections; the current design can only show a
  generic parameter-summary card.
- Enabled MCP tools are treated as user-authorized and are not approved per
  call. A stdio server is effectively arbitrary command execution on the
  computer: importing is trusting, and the safety boundary does not cover
  side effects produced by MCP tools after they return.
- MCP calls time out after about 30 seconds; images, resource references, and
  other non-text content are discarded, so the model only sees textual results.

## Security, privacy, and audit

- QR pairing exchanges a short-lived single-use code (300s default) for the
  Token; once expired or consumed you must restart with `--qr` or type the
  Token manually, as there is no runtime re-issue endpoint.
- On plain-HTTP LAN the pairing code and Token can be sniffed by the same
  network segment; use Tailscale/HTTPS off-LAN. The Token lives in
  `sessionStorage` (cleared when the tab closes) but XSS could still read it.
- The service listens on an HTTP LAN port by default and has no built-in TLS.
  Screenshots are sent to the configured model provider; with OCR enabled they
  are also uploaded to AI Studio. There is currently no local OCR or
  sensitive-region masking/redaction capability.
- There is no session recording, persistent action logging, or audit replay.
  Who approved which action and what parameters were actually executed exists
  only briefly in WebSocket events and is lost on restart.
- Security review can be disabled by configuration; custom blocklists replace
  the built-in rules entirely, so a poorly chosen configuration protects less
  than the defaults. Approval requests time out by default after 30 seconds and
  are then auto-rejected.
- The phone token is not stored in localStorage, so refreshing the page requires
  re-entering it: secure but inconvenient. WebSocket tokens travel in the
  subprotocol and REST tokens in a header, keeping them out of URLs, but
  transport security still depends on the LAN and tunnel.

## Testing and acceptance blind spots

- Automated tests mainly use a mocked OpenAI client and a fake InputBackend.
  Logic coverage is good, but there is no quantitative end-to-end success
  baseline against a real desktop, WeChat, Electron, or web page.
- There is no task-level success-assertion dataset (for example: open WeChat →
  find a contact → send a message → verify the bubble) and no replay/regression
  harness, so whether a change makes real tasks more or less accurate cannot be
  measured.

The items above are the current-state gaps that the upcoming precision
foundation (window activation, semantic targets, conditional waits, human
checkpoints, app recipes) and the trust trio are expected to fill.
