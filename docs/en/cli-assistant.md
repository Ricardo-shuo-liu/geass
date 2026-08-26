# CLI terminal assistant

> [Back to index](index.md) · [Project overview](../../README.md)

CLI (`geass cli`) is a terminal assistant separate from the phone GUI, sharing
memory, RAG, SKILLs and COT/ROT assets.

- It opens a **claude-cmd style menu**: big ASCII logo, arrow-key navigation
  (↑/↓ + Enter), emoji icons and group headers (会话/资产/Configuration),
  for starting sessions, viewing assets or exiting;
- **light mode (default)**: loads Global-COT, 1-2 relevant ROTs, SKILL
  catalog, RAG injection and memory; tools are read-only assets plus confirmed
  terminal commands; no GUI mouse/keyboard actions.
- **deliberate mode**: `/deliberate` switches the prompt to `Delib>`; selects
  ROTs, spawns 2-3 in-process sub-agents (one ROT each) for visible debate
  rounds, then a main agent summarizes; `/light` or `/exit` returns.
- Slash commands: `/help /mode /deliberate /light /rot list|use /skill
  list|read /rag search /cot show /clear /exit`.

The UI uses Rich panels when available and falls back to a plain REPL.
