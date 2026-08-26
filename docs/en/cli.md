# Command line

> [Back to index](index.md) · [Project overview](../../README.md)

`geass` (or `python -m geass`) is the unified entry point: `serve`, `cli`,
`rag`, `config`, `check`, `pot`, `reset`, `commands`.

`geass reset` deletes runtime data under `~/.geass/` (`.memory/.skill/.rag/
.schedule/.pot/` and `env.toml`) after two consecutive `reset` confirmations;
original files and repository files are untouched.
