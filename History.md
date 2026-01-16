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

### 11) Phase 5: clarifying-question gate (minimal, PRD-aligned)
- Added a minimal clarification policy and wired it into `/chat` to ask only when the input is materially ambiguous.
- **Why**: PRD §6 requires questions to be minimal and only when they materially affect scope.
- **Files**
  - `src/backend/response_policy.py`: clarification decision policy (minimal, forward-moving).
  - `src/backend/app.py`: uses policy before model call and persists the clarifying question.

### 12) Tests and dev dependencies
- Added a focused unit test suite for the clarification policy and a minimal pytest config.
- **Why**: ensure behavior guardrails are enforced by tests, not just manual inspection.
- **Files**
  - `tests/test_response_policy.py`: checks decision boundaries for clarify vs answer.
  - `pytest.ini`: test discovery config.
  - `src/backend/requirements-dev.txt`: dev dependencies (pytest).

### 13) Phase 6: tool sandbox (backend registry + runner)
- Added an explicit tool registry with allowlisted, local-first tools and a single `/tools/run` endpoint that logs tool runs as events.
- **Why**: PRD requires structured, inspectable tool execution without raw shell exposure.
- **Files**
  - `src/backend/tools/registry.py`: tool definitions, validation, and handlers.
  - `src/backend/tools/__init__.py`: tool exports.
  - `src/backend/app.py`: `GET /tools` and `POST /tools/run`, event logging for tool runs.

### 14) Tool UI and documentation
- Added UI controls for explicit tool invocation (with confirmation for protected tools) and surfaced tool output/errors.
- Documented local-first tool usage and environment flags.
- **Files**
  - `src/ui/src/App.tsx`: tools panel + run flow + output viewer.
  - `docs/tools.md`: tool usage, env flags, and offline/network rules.

### 15) Tool sandbox tests
- Added tests for path allowlisting and SQL read-only enforcement in tools.
- **Files**
  - `tests/test_tools.py`: validates tool boundary checks and SQL constraints.

### 16) Tool schema tightening + UI quick inputs
- Tightened tool input schemas to disallow extra properties and defined item types.
- Added “Quick inputs” form in the UI to generate valid tool JSON for common tools.
- **Files**
  - `src/backend/tools/registry.py`: stricter input schemas.
  - `src/ui/src/App.tsx`: quick input form + JSON apply flow.

### 17) Phase 7 kickoff (perf/packaging notes)
- Added a placeholder doc to capture performance measurements and packaging decisions.
- **Files**
  - `docs/perf-notes.md`: Phase 7 measurement and packaging notes.

### 18) Phase 7 measurement plan + packaging approach
- Added concrete measurement instructions and recorded a packaging plan (Tauri sidecar with PyInstaller).
- **Files**
  - `docs/perf-notes.md`: measurement steps and packaging plan details.

### 19) Startup timestamp logging + measurement script
- Added backend startup timestamp logging and a script to capture startup latency.
- **Files**
  - `src/backend/app.py`: startup log marker (`backend_startup`).
  - `scripts/measure-backend-startup.ps1`: runs backend and records startup timing.

### 20) Backend startup measurement + app.py fixes
- Captured backend startup time via the measurement script and fixed syntax issues in `app.py` that blocked startup.
- **Files**
  - `src/backend/app.py`: indentation normalization and f-string fixes.
  - `docs/perf-notes.md`: recorded startup measurement.

### 21) Backend idle measurement script
- Added a backend idle measurement script and recorded idle CPU/event deltas (memory still manual).
- **Files**
  - `scripts/measure-backend-idle.ps1`: backend idle CPU/memory/events script.
  - `docs/perf-notes.md`: recorded idle CPU/event results.

### 22) UI startup timing helper
- Added a helper script to capture UI startup time with a manual “UI ready” marker.
- **Files**
  - `scripts/measure-ui-startup.ps1`: UI startup timing prompt.

### 23) Fix Tauri build setup
- Added missing build script hook so `tauri dev` sets `OUT_DIR`.
- **Files**
  - `src/ui/src-tauri/build.rs`: tauri build script.
  - `src/ui/src-tauri/Cargo.toml`: added `build = "build.rs"`.

### 24) Dev-mode Tauri bundling fix
- Disabled bundle step in dev config to avoid missing icon errors.
- **Files**
  - `src/ui/src-tauri/tauri.conf.json`: `bundle.active` set to false.

### 25) Added minimal icon for Tauri dev build
- Added a minimal `icon.ico` so Tauri can generate Windows resources in dev.
- **Files**
  - `src/ui/src-tauri/icons/icon.ico`: minimal 1x1 icon.

### 26) TTFT measurement helper
- Added a script to measure time-to-first-token via `/chat`.
- **Files**
  - `scripts/measure-ttft.ps1`: TTFT measurement script.

### 27) Documented llama.cpp server details
- Recorded local llama.cpp server details used for TTFT testing.
- **Files**
  - `docs/perf-notes.md`: llama.cpp server script path, model, and args.

### 28) Model URL switcher (backend + UI)
- Added an explicit backend endpoint and UI control to switch the llama.cpp server URL.
- **Files**
  - `src/backend/app.py`: `GET /model` and `POST /model` (logs `model_switch` events).
  - `src/backend/model_gateway.py`: model URL override support.
  - `src/ui/src/App.tsx`: model URL panel (apply/reset).

### 29) Model switcher integration (single server restart)
- Added model switch options and a UI flow that restarts llama.cpp via the existing model switcher script.
- **Files**
  - `model-switch/models.json`: model list and gguf paths.
  - `model-switch/model_switcher.ps1`: env overrides + Vulkan defaults.
  - `src/backend/app.py`: `GET /model/options` and `POST /model/switch`.
  - `src/ui/src/App.tsx`: model selector + confirmation switch action.

### 30) Curated model switch list
- Trimmed model switch options to a 5-model test set for easier evaluation.
- **Files**
  - `model-switch/models.json`: curated list.

### 31) Model notes + ensure-dev script
- Added model notes to the model switcher UI and a script to start missing services.
- **Files**
  - `model-switch/models.json`: model notes.
  - `src/ui/src/App.tsx`: displays model notes.
  - `scripts/ensure-dev.ps1`: starts llama.cpp, backend, and UI if not running.
  - `README.md`: documented `ensure-dev` script.

### 32) Observability + operations dashboard
- Added structured logging, log tail endpoint, service status/control endpoints, and a dashboard view in the UI.
- **Files**
  - `src/backend/app.py`: log setup, request logging, log tail endpoint, service status/start/stop endpoints, event logs for prompts/responses.
  - `model-switch/stop_llama.ps1`: stop script for llama-server.
  - `src/ui/src/App.tsx`: operations dashboard (status, logs, start/stop).
  - `docs/tools.md`: dashboard and endpoints.

### 33) Log filters + events view
- Added log filtering and an events viewer in the operations dashboard.
- **Files**
  - `src/backend/app.py`: `GET /logs` filters + `GET /events`.
  - `src/ui/src/App.tsx`: log filters + events list UI.
  - `docs/tools.md`: updated endpoints.

### 34) Preference gating tests
- Added integration tests to enforce proposal timing and pre-approval non-influence.
- **Files**
  - `tests/test_integration.py`: proposal emitted after tokens; pending proposals do not affect prompts or create preferences.

### 35) Phase 7 measurements and status updates
- Recorded backend idle metrics, TTFT, and manual idle/network checks; documented the UI startup gap.
- Marked Phase 7 as complete with the documented gap.
- **Files**
  - `docs/perf-notes.md`: measurement results + PASS/FAIL status.
  - `docs/implementation-plan.md`: Phase 7 marked complete with UI startup gap note.
  - `Project_state.md`: Phase 7 status updated.
  - `next_tasks.md`: status updated to complete.

### 36) TTFT script fix
- Fixed PowerShell parameter placement in TTFT measurement script.
- **Files**
  - `scripts/measure-ttft.ps1`: move `$ErrorActionPreference` after `param`.

### 37) Startup logging via FastAPI lifespan
- Replaced deprecated `on_event("startup")` with a lifespan handler.
- **Files**
  - `src/backend/app.py`: lifespan handler logs startup marker.

### 38) Regex warning fix
- Fixed ANSI strip regex to avoid a future warning.
- **Files**
  - `src/backend/model_gateway.py`: corrected escape sequence.
