# Command line

> [Back to index](index.md) · [Project overview](../../README.md)

`geass` (or `python -m geass`) is the unified entry point: `serve`, `cli`,
`export`, `rag`, `mcp`, `config`, `check`, `pot`, `reset`, `commands`.

`geass reset` deletes runtime data under `~/.geass/` (`.memory/.skill/.rag/.mcp/
.schedule/.pot/` and `env.toml`) after two consecutive `reset` confirmations;
original files and repository files are untouched.

Optional QR pairing:

```text
geass serve --qr                  # start and print a single-use pairing QR code
geass serve --qr --qr-ttl 600     # custom TTL (30-3600 seconds)
./scripts/run.sh --qr             # equivalent
```

The QR code contains `/#pair=<short-lived code>`; the page exchanges it for the
access Token via `/api/pair`. Codes expire after 300 seconds by default and can
be redeemed once; restart with `--qr` to generate a new one.

MCP commands: `geass mcp add/import/list/test/enable/disable/remove`
(see [MCP tools](mcp.md)).

Asset export (SKILL / COT / ROT):

```text
geass export skill desktop-automation web-search --to ~/geass-assets
geass export skill --all --to ~/geass-assets
geass export cot --to ~/geass-assets
geass export rot security --to ~/geass-assets
geass export rot --all --to ~/geass-assets
geass export all --to ~/geass-assets        # all SKILL + COT + ROT
```

The destination contains `skills/<name>/`, `pot/cot.md`, `pot/rot/<name>.md`
and a `manifest.json` with sources and file lists. Re-exporting an existing
name requires `--force`; ROT export includes disabled items unless
`--enabled-only` is given.
