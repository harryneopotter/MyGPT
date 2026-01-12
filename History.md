# Project History (Work Log)

This repo currently has no Git history (`.git/` is absent). This document summarizes completed work based on the current on-disk state and recent changes made during the rebuilt session after the crash.

## Completed Work (What + Where + Why)

### 1) Repo structure + runnable baseline
- Added runnable backend + UI with a copy/paste Windows dev flow.
- **Files**
  - `README.md`: quick-start commands and dev workflow.

### 2) Backend control plane (FastAPI) + streaming chat
- Implemented a local control plane with SSE streaming and SQLite persistence.
- **Why**: PRD requires UI↔backend separation, local-first operation, and inspectable state.
- **Files**
  - `src/backend/app.py`: FastAPI app, endpoints, SSE streaming (`/chat`), SQLite persistence, and event logging.
  - `src/backend/requirements.txt`: backend deps (`fastapi`, `uvicorn[standard]`, `pydantic`, `httpx`).

### 3) SQLite storage with immutability enforcement
- Implemented append-only message storage and immutability triggers.
- **Why**: PRD message integrity invariant (no edits/deletes).
- **Files**
  - `src/backend/schema.sql`: schema + triggers for immutability.
  - `data/chat.db`: runtime DB (generated/updated by the backend; not a source file).

### 4) Conversation model (multiple chats)
- Added `conversations` + mapping table so messages are grouped without mutating messages.
- **Why**: multi-chat UX while preserving immutable message rows.
- **Files**
  - `src/backend/app.py`: `/conversations` endpoints and conversation/message mapping.
  - `src/backend/schema.sql`: `conversations`, `conversation_messages`.

### 5) Model gateway + llama.cpp integration
- Added a backend-only model gateway that talks to a local llama.cpp-style HTTP server (`/completion`) and streams tokens.
- **Why**: PRD requires UI never calls models directly; backend owns model access.
- **Files**
  - `src/backend/model_gateway.py`: prompt assembly, llama.cpp streaming adapter, stop sequences, reasoning-format controls.

### 6) Phase 4: preference inference → propose → approve (no pre-approval influence)
- Added storage separation for proposals vs approved preferences and a one-at-a-time UI proposal card.
- **Why**: PRD/guardrails require inferred preferences to be inert until explicit approval.
- **Files**
  - `src/backend/schema.sql`: `preference_proposals`, `preferences`, `preference_resets`, `events` tables + immutability triggers.
  - `src/backend/app.py`: proposal inference (simple heuristic), proposal endpoints, preference approval events, preference reset endpoint.
  - `src/ui/src/App.tsx`: renders at most one pending proposal after answers; approve/reject actions.

### 7) Base assistant system prompt as a versioned, immutable artifact
- Moved the canonical “constitutional” system prompt into a versioned artifact and enforced immutability via a sha256 check.
- **Why**: ensure the exact constitution used by the backend is provable and cannot drift silently.
- **Files**
  - `system/base_assistant_prompt.md`: canonical base system prompt used for every model call.
  - `system/base_assistant_prompt.sha256`: expected hash; backend raises on mismatch.
  - `src/backend/model_gateway.py`: loads, hashes, logs the base prompt at startup; prepends it to every prompt.
  - `base_assistant_system_prompt_non_negotiable.md`: original source document used to derive the artifact (kept for reference).

### 8) Dev launcher to start backend + UI together
- Added a single PowerShell script that spawns backend and UI in separate PowerShell windows.
- **Why**: reduce friction during local dev and ensure consistent env configuration.
- **Files**
  - `scripts/start-dev.ps1`: starts backend + UI; sets `MYGPT_MODEL_URL`, `MYGPT_N_PREDICT`, `VITE_BACKEND_URL`; defaults LLM logging ON (disable via `-DisableLlmLogging`).
  - `README.md`: documents `scripts/start-dev.ps1`.

### 9) LLM prompt/response logging for debugging
- Added optional logging for the exact prompt sent to llama.cpp and the full raw response; logs are stored as files and referenced via append-only DB events.
- **Why**: inspectability + debugging (e.g., prompt-echo, transcript continuation, “thinking” wrappers, truncation).
- **Files**
  - `src/backend/app.py`: writes `data/llm_logs/<trace>.prompt.txt`, `...response.txt`, `...response.cleaned.txt`; records `events` rows (`llm_request`, `llm_response`).
  - `scripts/start-dev.ps1`: enables logging by default in dev.

### 10) Output hygiene (prevent transcript continuation, strip control tokens)
- Added stop sequences and sanitization to reduce:
  - invented `User:` turns,
  - ANSI escape codes polluting the UI,
  - internal reasoning wrappers polluting stored history.
- **Why**: keep transcript causal and readable; prevent model from re-ingesting its own transcript artifacts.
- **Files**
  - `src/backend/model_gateway.py`: stop sequences + prompt formatting; sanitizes prior assistant history when assembling prompts.
  - `src/backend/app.py`: strips ANSI and common think wrappers; truncates stored assistant messages at role markers.

## Notes / Known Caveats
- Existing conversations may contain older polluted assistant messages (immutability prevents rewriting). Start a new conversation to get clean behavior after prompt/output fixes.
- Some local models can still strongly prefer “thinking” or transcript formats; the repo now logs raw vs cleaned responses and provides tuning knobs via env vars.

