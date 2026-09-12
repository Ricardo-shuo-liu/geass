# Trust layer: action preview & privacy masks

> [Back to index](index.md) · [Project README](../../README.md)

The PWA exposes a "Trust" panel (信任) that controls how Agent actions are
visualised/confirmed and whether privacy masks are applied. Settings live in
`~/.geass/.trust.json` and `~/.geass/.masks.json` (both 0600).

## Preview modes

| Mode | Behaviour |
| --- | --- |
| **Smart** (default) | Every GUI action is ghosted on screen and runs after a 600ms visual delay; terminal commands, closing a terminal and first-time MCP tools wait for phone confirmation |
| **Confirm all** | Every previewable action waits for "Execute / Edit / Reject" |
| **Off** | No ghosting, no waiting; only the existing terminal blocklist review remains |

- Visuals include crosshair rings for mouse moves and clicks, drag arrows with handles, scroll
  direction, text bubbles and a "step 3/7 · click Save · auto in 0.6s" strip.
- In smart mode the strip has an "Intercept" button that cancels the action
  before the delay elapses.
- In confirm mode targets are editable: drag point/drag markers on the screen,
  edit text/command/key/URL in the card, or adjust scroll deltas.
- Cards offer "always allow this tool" and "allow everything for this task";
  blocklisted commands can never be silently allowed.
- If no phone control client is connected, confirmation-required actions are
  rejected immediately; smart-mode GUI actions still run after the delay.

## Privacy masks

- Disabled by default; enable the master switch or draw the first mask (which
  enables it automatically).
- Masks are drawn by dragging on the live screen and render as translucent
  boxes only while masking is enabled.
- Cancel with "Cancel drawing" or Esc (drawing mode also exits after one
  region); delete a single region, clear all regions, or turn the master
  switch off to stop both redaction and the on-screen boxes.
- Masking happens in the capture layer, so streamed frames, model screenshots,
  OCR input and before/after action frames are all redacted. Masks cover the
  primary monitor only and never block input.
- Up to 20 regions with a 1% minimum edge; delete from the same panel.
- **Auto-detection**: "Detect sensitive regions" runs once and combines AT-SPI
  password/protected inputs with OCR keyword matches (password, verification
  code, ID card, bank card, token, …), returning suggestions you can apply
  individually or all at once. It is best-effort: custom-drawn UIs and a
  missing OCR token can lead to misses, so manual drawing remains useful.

## Interfaces

- `GET/POST /api/trust`, `GET /api/privacy/masks`;
- `/ws/control`: `action_proposal`, `action_decision`, `action_resolved`,
  `privacy_masks_changed`, `trust_changed`.

One-click undo and session replay are not part of this phase.
