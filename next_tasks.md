# Next Tasks (Phase-Gated, Guardrail-First)

This file is the execution guide to complete the remaining phases from `docs/implementation-plan.md` while strictly preserving the PRD invariants and the repo guardrails.

**Status:** All phases are complete. The UI startup <2s gap is documented in `docs/perf-notes.md` and is not being targeted.

## Non‑Negotiables (Reinforce Before Every Change)
- **Message integrity**: never update/delete message rows; corrections are additive messages only (`corrects_message_id`).
- **UI never talks to models**: UI only calls backend endpoints; backend owns model/tool access.
- **No silent state changes**: every persisted change must be attributable to a user message, an approved preference change, or an explicit user-triggered tool action (and be inspectable).
- **Preference gating**: inferred preferences must be inert until explicitly approved; never influence reasoning/framing/structure pre-approval.
- **No background agents**: no periodic work, no scheduling, no autonomous tool runs; everything is triggered by a user message in the active session.
- **PRD supremacy**: if uncertain, follow `final_prd_logical_low_friction_ai_chat_system.md` and `docs/guardrails.md`; deviations require `docs/deviation-policy.md`.

## Phase Gate Evidence (Do This for Each Phase)
For each phase, produce:
- A short demo note (“How to run” + “What to click/type” + expected result).
- Copy/paste verification commands (health checks, DB checks, grep checks).
- If/when tests exist, one command that runs them all.

---

## Phase 5 — Questioning Rules + Regeneration Semantics (Completed)
**Status:** Implemented (backend clarification gate + regenerate semantics).

**Evidence**
- Clarifying gate: `src/backend/response_policy.py`, used by `/chat` in `src/backend/app.py`.
- Regenerate: `/regenerate` endpoint appends new assistant messages and does not create proposals.
- Tests: `python -m pytest` (see `tests/test_response_policy.py`).

---

## Phase 6 - Tool Execution Sandbox (Structured, Inspectable) (Completed)
**Goal:** Allow user-triggered tool execution without giving the model raw shell access.

### 6.1 Tool model and allowlist (Completed - backend)
Implemented backend tool registry + runner with allowlisted, local-first tools.
Current local tools: `list_dir`, `read_file`, `search_text`, `stat_path`, `write_file`, `git_status`, `git_diff`, `git_show`, `apply_patch`, `sql_query`, `open_url`, `run_command`.
Network tools are disabled by default (`MYGPT_ALLOW_NETWORK_TOOLS=0`).

### 6.2 Tool model and allowlist (Optional)
Define tools as explicit backend-owned capabilities if you expand the tool set.
- No “model can run any command”.
- Every tool:
  - has a stable `tool_id`,
  - an explicit JSON schema for inputs,
  - an explicit JSON schema for outputs,
  - deterministic execution (same input → same output where feasible),
  - bounded time/resources.

**Recommended structure**
- `src/backend/tools/registry.py`: tool definitions + allowlist (implemented).
- `src/backend/tools/schemas/*.json`: optional input/output schemas if you want them split out later.

### 6.3 Execution rules (hard constraints)
- Tools execute **only** as a direct consequence of a user message in the active session.
- Store a tool-run record as an append-only event:
  - `type="tool_run"`
  - `payload_json` includes: `tool_id`, `input_json`, `output_json`, `exit_code`, `started_at`, `ended_at`, `artifacts`.
- Tool outputs must never mutate message history; attach artifacts separately.

### 6.4 UI: explicit tool invocation (Completed)
UI includes a tools panel with explicit confirmation and output viewer.

### 6.5 UX polish (Deferred)
- Add required-field hints and inline schema guidance for tool inputs.
- Provide common presets (e.g., list repo root, last diff).
- Improve formatting of tool outputs (tables for `sql_query`, collapsible sections for long logs).

**Verification commands**
- Attempt to run a non-allowlisted tool → clear structured error.
- Confirm every tool run has a corresponding `events` row with full I/O.
- Confirm app idle state does no work (no polling / no hidden calls).

---

## Phase 7 - Performance, Packaging, No-Background-Agents Guarantee (Completed)
**Goal:** Meet constraints and prove there is no unintended autonomy.
Use `docs/perf-notes.md` to capture measurements and decisions.

**Status:** Complete with documented UI startup gap (see `docs/perf-notes.md`).

### 7.1 Performance targets (measure first)
Create a small `docs/perf-notes.md` (or expand existing docs) with:
- Backend startup time and steady-state idle CPU/memory.
- UI startup time.
- Token streaming latency (time-to-first-token).

### 7.2 Packaging plan (Tauri)
Define how the backend is shipped with the desktop app.
- Preferred: bundle a local Python environment or ship backend as a packaged artifact and start it from Tauri.
- Must remain offline-capable (local model server optional).

### 7.3 No-background-agents proof
Add a simple checklist and manual validation protocol:
- With the app idle:
  - CPU near zero,
  - no periodic network calls,
  - no background tool execution.
- With network disabled:
  - core flows still work (local model only).

---

## Cross-Cutting Hardening (Do Between Phases as Needed)
These are permitted as long as they do not violate invariants and do not “skip gates”.

### A) Prompt / output hygiene (debuggability without rewriting history)
- Use `data/llm_logs/*.prompt.txt` and `.response.txt` to debug model behavior.
- Keep “cleaned vs raw” distinct:
  - raw output stays in logs,
  - stored assistant message is cleaned for transcript readability.
- Do not edit existing stored messages; use `New Chat` to validate improvements.

### B) Safety against accidental preference approval (UI-level)
Follow `docs/approval-drills.md`:
- Ensure proposal UI is visually secondary, appears after the answer, and requires explicit Approve/Reject action.
- Do not interpret casual acknowledgements as approvals.

### C) Migrations (SQLite)
If schema changes are needed:
- Prefer additive tables/columns and append-only event logging.
- Keep triggers that enforce immutability.
- Never add a migration that retroactively edits message content.

---

## Suggested Execution Order (Historical)
1. Phase 6 Tool sandbox skeleton (registry + runner + one safe demo tool like “read file” or “list directory” with strict allowlist).
2. Phase 6 UI tool invocation + event/audit trail.
3. Phase 7 measurement + packaging plan + no-background-agents proof.

## Quick “Don’t Accidentally Break PRD” Checklist
- Did you add any `UPDATE`/`DELETE` path for `messages`? (must remain impossible)
- Did you make UI call the model server directly? (must remain impossible)
- Did any preference affect behavior before approval? (must remain impossible)
- Did you introduce any timer/background thread/cron-like behavior? (must remain impossible)
- Can every persisted change be explained and traced to an explicit user action? (must remain true)
