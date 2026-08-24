# Task planning & memory

> [Back to index](index.md) · [Project overview](../../README.md)

At the start of every task the model chooses its difficulty. Easy, single-step
tasks can act immediately. Hard tasks (multi-step, cross-app, needing a new
page or verification) first call the `plan` tool with `difficulty="hard"`, a
`goal`, and `steps`; the execution loop keeps injecting that plan and the model
updates `current_step` as it progresses. The phone shows a compact plan card
with completed/current/pending steps.

The key part is the verify-and-recover loop. Mouse and keyboard only *perform*
actions; they don't prove an action worked. So each screen-changing action
captures before/after frames and reports `screen_changed` back to the model,
and a `window_info` tool reports the active window plus the visible top-level
window list. Together with screenshots, OCR text and the AT-SPI tree, the model
can notice a failed click and retry with a different coordinate or method
instead of blindly repeating itself.

`remember` / `recall` / `forget` provide cross-task memory backed by
`~/.geass/.memory/entries.json` (200 entries by default). Facts such as "default browser
is Firefox" or "this task failed because of X" survive restarts, and the 8 most
relevant entries are injected into the system prompt before each command.
Set `agent.memory_enabled = false` to disable it.
Relevant memory entries are sent to your configured model provider with the
system prompt, so do not store passwords or other secrets with `remember`.

Tasks like "open the browser, then create a new page" use `browser` only as the
deterministic "open it" primitive (`action` of `open`, `new_tab`, or
`new_window`). The whole task is finished by the planning/verification loop:
`plan`, launch, `wait`, then `window_info` + `screenshot` to confirm the page
loaded, switching approach when verification fails. Browser launching is a
built-in `browser` tool rather than a SKILL; SKILLs stay general-purpose and
low-level.
