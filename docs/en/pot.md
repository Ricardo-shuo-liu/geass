# POT reflection system

> [Back to index](index.md) · [Project overview](../../README.md)

POT = Reflect → Distill → Template:

- **Global-COT**: a universal problem-solving paradigm distilled from task
  traces, injected into prompts by default;
- **ROT**: role-perspective thinking templates (SKILL-like), with 1-2 injected
  automatically by relevance or pinned manually;
- **trace**: commands/plans/tool sequences/results kept in
  `~/.geass/.pot/trace.jsonl` (capped at 200) for idle reflection.

The idle evolution engine reflects over traces and updates the COT or creates
new ROTs. Manage with `geass pot cot show` / `geass pot rot list|show|disable|
enable|delete <name>`.

Export with `geass export cot --to <dir>`, `geass export rot <name> --to <dir>`
or `geass export rot --all --to <dir>` (disabled ROTs are included unless
`--enabled-only` is passed); see [Command line](cli.md).
