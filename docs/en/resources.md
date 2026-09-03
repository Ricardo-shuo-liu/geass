# Resource management (phone)

> [Back to index](index.md) · [Project overview](../../README.md)

The **资源** button in the phone top bar opens the resource panel for managing
all runtime assets used by the Agent:

- **Memory**: view entries, delete one, clear all;
- **MCP**: import via stdio/HTTP forms or JSON, auto connection test, per-server/per-tool toggles, permanent delete;
- **RAG**: add/remove sources, enable/disable, reindex;
- **Skills**: view runtime SKILLs (system/evolved badges), delete;
- **POT**: view Global-COT, enable/disable/delete ROTs;
- **Schedule**: view pending jobs and cancel;
- **Background**: view background tasks (pending/running/done/error), start, cancel, remove.

All actions affect only runtime data under `~/.geass/`; original files are
untouched. Deleting a system skill restores it on the next sync from the seed
directory.

Backend endpoints: `GET/POST/DELETE /api/resources/...` (see
[DESIGN.md](../DESIGN.md)), sharing the same storage as the CLI commands.
