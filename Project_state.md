# Project State (Current Snapshot)

This document describes the current implemented state of the project (code + docs) in `G:\AI\tools\mygpt`.

## Purpose
- Implement the PRD in `final_prd_logical_low_friction_ai_chat_system.md`: a local-first AI chat system emphasizing message integrity (immutability), intent supremacy, logic supremacy, and inspectable state.

## Architecture (High-Level)
**Desktop UI (Tauri + React/TS)** → **Local backend (FastAPI control plane)** → **Local model server (llama.cpp HTTP)**  
**Backend** is the only component allowed to call model servers and to touch persistence.

### Data Flow (Chat)
1. UI sends a user message to backend `POST /chat`.
2. Backend appends the immutable user message row to SQLite.
3. Backend loads the conversation transcript and approved preferences.
4. Backend builds a prompt (base constitution + defaults + transcript) and streams tokens from the model server.
5. Backend streams tokens to UI via SSE (`data: {"token":"..."}`).
6. Backend stores the assistant message (append-only) after generation completes.
7. Backend may surface **one** preference proposal (after the answer, never mid-stream).

## Tech Stack (Current)
- **UI**: Tauri + React + TypeScript + Vite
  - Why: PRD forbids Electron by default; Tauri is lighter and local-first friendly.
- **Backend**: Python + FastAPI + Uvicorn + httpx
  - Why: quick local control plane; async streaming; simple deployment.
- **Storage**: SQLite
  - Why: local-first, inspectable, easy to enforce immutability with triggers.
- **Model integration**: llama.cpp-compatible HTTP server at `MYGPT_MODEL_URL` (defaults to `http://127.0.0.1:8080`)

## Repository Layout
- `final_prd_logical_low_friction_ai_chat_system.md`: source-of-truth PRD.
- `docs/`: operational docs (guardrails, deviation policy, implementation plan).
- `plans/`: planning artifacts (e.g., feasibility notes).
- `src/backend/`: FastAPI control plane + model gateway + SQLite schema.
- `src/ui/`: Tauri + React UI.
- `system/`: versioned constitutional system prompt artifact + hash.
- `scripts/`: dev scripts (start backend + UI together).
- `data/`: runtime state
  - `data/chat.db`: SQLite DB
  - `data/llm_logs/`: prompt/response traces (dev logging)

## Key Files and Relationships
- UI (`src/ui/src/App.tsx`) calls backend endpoints only:
  - `GET /conversations`, `POST /conversations`
  - `GET /messages?conversation_id=...`
  - `POST /chat` (SSE streaming)
  - `GET /preference-proposals`, `POST /preference-proposals/{id}/approve|reject`
  - `GET /preferences`, `POST /preferences/reset`
- Backend (`src/backend/app.py`) calls:
  - SQLite schema in `src/backend/schema.sql`
  - Model gateway in `src/backend/model_gateway.py`
- Model gateway (`src/backend/model_gateway.py`) calls:
  - llama.cpp server endpoint: `POST {MYGPT_MODEL_URL}/completion`
  - base system prompt: `system/base_assistant_prompt.md` (verified by `system/base_assistant_prompt.sha256`)

## Backend API (Current)
- Health
  - `GET /health` → `{"status":"ok"}`
- Conversations
  - `GET /conversations`
  - `POST /conversations` (body: `{ "title": string | null }`)
- Messages
  - `GET /messages?conversation_id=...`
  - `POST /messages` (manual append; supports `corrects_message_id`)
- Chat (streaming)
  - `POST /chat` (body: `{ "content": string, "conversation_id"?: number }`)
  - Streams SSE events:
    - `{"token":"..."}` repeated
    - optional `{"proposal": {...}}` at end
    - `{"done": true}` final
- Preferences
  - `GET /preferences?scope=global`
  - `POST /preferences/reset?scope=global` (append-only reset marker; does not delete history)
- Preference proposals
  - `GET /preference-proposals?conversation_id=...&status=pending`
  - `POST /preference-proposals/{id}/approve`
  - `POST /preference-proposals/{id}/reject`

## Base System Prompt (Constitution)
- Stored as a versioned artifact: `system/base_assistant_prompt.md`
- Hash locked: `system/base_assistant_prompt.sha256`
- Backend behavior:
  - On import/startup, backend computes sha256 of the prompt file and raises if it does not match the expected hash.
  - The prompt is injected as the highest-priority “System:” block on every model call (before transcript and before any defaults).

## Prompt Assembly and Model Controls
Prompt assembly happens in `src/backend/model_gateway.py` and uses:
- Constitutional “System:” block (from `system/base_assistant_prompt.md`)
- System instructions to avoid transcript simulation and internal reasoning output
- Approved defaults only (e.g., `verbosity=concise`)
- Transcript formatted as:
  - `User:` + indented content
  - `Assistant:` + indented (sanitized) assistant content

Model server controls (env vars / defaults):
- `MYGPT_MODEL_URL` (default `http://127.0.0.1:8080`)
- `MYGPT_N_PREDICT` (default `256`)
- `MYGPT_REASONING_FORMAT` (default `none`; passed to llama.cpp request payload)
- `MYGPT_REASONING_IN_CONTENT` (default `false`)
- Stop sequences: default stops on new role headers (e.g., `\nUser:`, `\nSystem:`) to prevent transcript continuation.

## Persistence (SQLite) and Invariants
Authoritative schema is `src/backend/schema.sql`.

### Tables
- `conversations(id, title, created_at)`
- `messages(id, content, role, timestamp, corrects_message_id)`
- `conversation_messages(conversation_id, message_id, created_at)` (mapping; supports multiple conversations without mutating messages)
- `events(id, type, payload_json, created_at, conversation_id, causality_message_id)`
  - Used for inspectable actions (preference approvals/rejections, LLM request/response trace pointers, resets).
- `preference_proposals(...)`
  - Stores inferred proposals separately from approved preferences.
- `preferences(id, key, value, scope, created_at, approved_event_id, source_proposal_id)`
  - Append-only; runtime defaults come only from this table (after considering resets).
- `preference_resets(id, scope, created_at, reset_event_id)`
  - Append-only reset markers; runtime preference loading ignores older preferences before the latest reset.

### Triggers (Non-Negotiable)
The schema enforces immutability via triggers that `RAISE(ABORT, ...)` on:
- `UPDATE`/`DELETE` for `messages`
- `UPDATE`/`DELETE` for `events`
- `UPDATE`/`DELETE` for `preferences`
- `UPDATE`/`DELETE` for `preference_resets`

## UI Components (Current)
Implemented in `src/ui/src/App.tsx`:
- Conversation selector + “New Chat”
- Transcript view (user + assistant messages)
- Streaming send + “Stop” (AbortController)
- Preference proposal card (Approve/Reject)
- Preferences panel:
  - refresh list
  - reset to baseline (calls backend reset endpoint)

## Dev Workflow
- Start both backend and UI:
  - `pwsh -File .\scripts\start-dev.ps1`
  - Defaults: prompt/response logging ON (disable with `-DisableLlmLogging`)
- Backend only:
  - `python -m pip install -r src\backend\requirements.txt`
  - `python -m uvicorn src.backend.app:app --reload --host 127.0.0.1 --port 8000`
- UI only:
  - `cd src\ui; npm install; npm run tauri dev`

## Observability / Logs
When enabled (default in dev script), backend writes:
- `data/llm_logs/<trace>.prompt.txt`
- `data/llm_logs/<trace>.response.txt` (raw model output)
- `data/llm_logs/<trace>.response.cleaned.txt` (post-processed content that is stored in SQLite)
and records corresponding `events` rows with file paths + sha256 hashes.

## Phase Status (Against `docs/implementation-plan.md`)
- Phase 0–3: runnable baseline, UI shell, immutable log, model gateway + streaming: implemented.
- Phase 4: preference proposal/approval pipeline: implemented (heuristic inference; approval stored as events + append-only prefs).
- Phase 5–7: not fully implemented (questioning rules/regeneration semantics, tool sandbox, packaging/perf/no-background-agents verification).

## Known Issues / Tuning Notes
- Some models output internal “thinking” or attempt to continue the transcript; mitigations exist (stop sequences, sanitization, response cleaning), but model behavior still matters.
- Old conversations can be “polluted” by earlier assistant messages; immutability prevents rewriting. Use `New Chat` to validate changes.
- If responses appear truncated, increase `MYGPT_N_PREDICT` (or `-ModelMaxTokens` in `scripts/start-dev.ps1`) and inspect the raw vs cleaned response logs.

