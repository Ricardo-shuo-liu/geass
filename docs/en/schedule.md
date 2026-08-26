# Scheduled tasks

> [Back to index](index.md) · [Project overview](../../README.md)

Scheduled tasks are primarily created **conversationally**: type something like
"open the terminal at 5 pm today" and the Agent recognizes the temporal intent
and calls the `schedule` tool. At the due time the server executes it through
the exact same Agent flow used for manual commands; execution status is
streamed to the phone log. There is no dedicated schedule window in the
frontend; cancelling or reviewing tasks can be done conversationally or via
the REST API below.

## Persistence & confirmation

The Agent decides whether a task needs to survive restarts:

- **Temporary jobs** (`persist=false`) live only in memory, suited for
  one-off near-term actions; they are lost when the service restarts;
- **Long-term jobs** (`persist=true`) are written to
  `~/.geass/.schedule/jobs.json` and continue after restart.

When the Agent decides persistence is needed, it must first ask the user
whether to keep the task long-term; after the user agrees, it confirms the
command and run time once more, and only then creates it with `confirm=true`.
Nothing is written to disk without user confirmation.

## Behavior

- Long-term jobs persist in `~/.geass/.schedule/jobs.json` (directory
  configurable via `agent.schedule_path`) and survive server restarts;
  temporary jobs are lost on restart;
- If another Agent task is already running at the due time, the scheduled job
  retries after 5 seconds instead of failing immediately;
- Pending jobs can be cancelled from the phone; completed jobs record a
  `done` or `error` status and result.

## API

- `GET /api/schedule`: list jobs (for integration/debugging);
- `POST /api/schedule`: `{"command": "...", "run_at": epoch-seconds,
  "persistent": true/false}`;
- `DELETE /api/schedule/{id}`: cancel;
- Status events are pushed over `/ws/control` as `schedule_status`.

The phone converts local time to epoch seconds; the server triggers on the
timestamp, independent of timezone display.
