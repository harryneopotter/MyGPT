# Tools (Local-First, Explicit, Inspectable)
This document describes the tool sandbox in Phase 6. Tools are local-only by default and require explicit user invocation from the UI.

## Principles
- Local-first: no network access is required for core usage.
- Explicit invocation: tools run only when the user triggers them in the UI.
- Inspectable: every tool run is logged as an `events` row (`type="tool_run"`).
- No raw shell: commands are allowlisted and executed with structured inputs.

## Endpoints
- `GET /tools`: returns tool definitions and flags.
- `POST /tools/run`: executes a tool with structured JSON input and logs the run.

## Local Tools (Current)
- `list_dir`: list files/dirs under allowed roots.
- `read_file`: read a text file under allowed roots.
- `search_text`: search text under allowed roots (uses `rg` if available).
- `stat_path`: file/dir metadata under allowed roots.
- `write_file`: write text to a file under allowed roots (requires confirmation).
- `git_status`: `git status -sb` (read-only).
- `git_diff`: `git diff` (read-only).
- `git_show`: `git show <ref>` (read-only).
- `apply_patch`: apply a unified diff (requires confirmation).
- `sql_query`: read-only `SELECT` / `WITH` query against SQLite (no mutations).
- `open_url`: returns a URL payload for explicit user action (requires confirmation).
- `run_command`: allowlisted commands only (requires confirmation).

## Environment Flags
- `MYGPT_TOOL_ROOTS`: allowed path roots (defaults to repo root). Use OS path separator (`;` on Windows).
- `MYGPT_ALLOW_NETWORK_TOOLS`: `0` by default. Set to `1` only if you add network tools and want them enabled.
- `MYGPT_TOOL_COMMAND_ALLOWLIST`: allowlisted commands for `run_command` (empty by default).
- `MYGPT_TOOL_MAX_OUTPUT_BYTES`: max stdout+stderr bytes (default `200000`).
- `MYGPT_TOOL_COMMAND_TIMEOUT`: command timeout in seconds (default `10`).

## UI Expectations
- The UI must require explicit user confirmation for any tool with `requires_confirmation=true`.
- Networked tools (if added) must be gated behind explicit opt-in and confirmation.
- The UI must require a `causality_message_id` so the run is attributable to a user message.
- The UI may provide structured “quick inputs” for common tools as long as it produces the same JSON that the backend receives.

## Model Switching (Single Server)
- Model switching is a user-triggered action that restarts the llama.cpp server on the same port.
- The backend exposes `POST /model/switch` for explicit, confirmed switches.
- Model options live in `model-switch/models.json`.

## Operations Dashboard
- Logs and service status are available via:
  - `GET /services/status`
  - `GET /logs?limit=...&level=...&contains=...`
  - `GET /events?limit=...&event_type=...&conversation_id=...`
- Service control (explicit confirmation required):
  - `POST /services/llama/start`
  - `POST /services/llama/stop`
