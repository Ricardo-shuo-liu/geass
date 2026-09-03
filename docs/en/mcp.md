# MCP tools

> [Back to index](index.md) · [Project overview](../../README.md)

Geass can import MCP (Model Context Protocol) servers so their tools are
available to the desktop Agent and the terminal CIL. Server registrations live
in `~/.geass/.mcp/servers.json` (mode 0600), completely separate from Geass
persistent memory.

## Supported transports

- **stdio**: `command + args + env + cwd` for local `npx` / `uvx` / Python
  MCP servers;
- **Streamable HTTP**: `url + headers` for remote MCP servers.

## UI

The phone resource panel has a new **MCP** tab:

- fill in the server details with the stdio/HTTP form, or paste Claude/Cursor
  style `{"mcpServers": {...}}` JSON;
- importing runs a connection + `list_tools` test automatically; only passing
  servers become verified and enabled. A failed import is kept disabled and
  can be retested later;
- enable/disable or permanently delete whole servers, and toggle individual
  tools after expanding a server. Unverified servers cannot be enabled or
  exposed to the model.

## CLI

```text
geass mcp add demo --transport stdio \
  --command uvx --args mcp-server-github --env GITHUB_TOKEN=xxx
geass mcp add search --transport http --url https://example.com/mcp \
  --header "Authorization: Bearer xxx"
geass mcp import ~/claude_desktop_config.json
geass mcp list
geass mcp test demo
geass mcp enable demo
geass mcp disable demo search_issue
geass mcp remove demo
```

A failed import keeps the disabled record and exits non-zero so you can fix the
command/URL and run `geass mcp test NAME` again.

## Runtime notes

- Enabled MCP tools are exposed as `mcp__<server>__<tool>` functions to the
  Agent and CIL;
- calls to one server are serialized, connections are lazy and cached, and are
  closed on disable/delete/shutdown to avoid orphan stdio processes;
- text results are forwarded to the model; non-text content is summarized;
- importing and enabling a server is treated as authorization; v1 does not add
  per-call approval.

`geass reset` also removes `.mcp/` registrations; remove one server at a time
with `geass mcp remove NAME`.
