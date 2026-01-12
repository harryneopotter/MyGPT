# Next Tasks (Phase-Gated, Guardrail-First)

This file is the execution guide to complete the remaining phases from `docs/implementation-plan.md` while strictly preserving the PRD invariants and the repo guardrails.

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

## Phase 5 — Questioning Rules + Regeneration Semantics
**Goal:** Prevent UX drift (permission-seeking, hidden rethink, preference drift) and implement regenerate as a true retry.

### 5.1 Clarifying-question gate (backend policy)
Implement a small, explicit policy function used on every response path:
- Ask a clarifying question **only** when the answer materially changes scope/outcome.
- No “Are you sure…?” / validation-seeking / comfort checks.
- No “Would you like me to…?” unless the user asked for options.

**Implementation approach**
- Add a response policy module (e.g., `src/backend/response_policy.py`) that:
  - decides: answer now vs ask 1 minimal question,
  - provides a short “decision rationale” (for optional debug logging only; not shown to user unless requested).
- Ensure this policy never consults inferred preferences (only approved prefs may affect defaults).

**Pass/Fail checks**
- Same input produces same behavior regardless of inferred-but-unapproved proposals.
- Questions are rare, short, and forward-moving.

### 5.2 Regenerate semantics (true retry)
Add a UI “Regenerate” action that:
- Regenerates **the last assistant response** for the same conversation context.
- Does **not** create new preference proposals or reset existing approved preferences.
- Does **not** mutate prior messages.

**Suggested data shape (append-only)**
- Add an `events` row for regenerate attempts:
  - `type="regenerate"`
  - `payload_json` includes: `target_assistant_message_id`, `request_params_hash`, and a new `trace_id`.
- Store the regenerated output as a **new assistant message** (optionally link via `corrects_message_id` or a new linking table if needed).

**Verification commands**
- Run regenerate 5x; confirm:
  - `preferences` table unchanged,
  - no new `preference_proposals` created unless independently triggered by post-answer logic and allowed by rules,
  - no message rows updated/deleted (triggers enforce this).

---

## Phase 6 — Tool Execution Sandbox (Structured, Inspectable)
**Goal:** Allow user-triggered tool execution without giving the model raw shell access.

### 6.1 Tool model and allowlist
Define tools as explicit backend-owned capabilities.
- No “model can run any command”.
- Every tool:
  - has a stable `tool_id`,
  - an explicit JSON schema for inputs,
  - an explicit JSON schema for outputs,
  - deterministic execution (same input → same output where feasible),
  - bounded time/resources.

**Recommended structure**
- `src/backend/tools/registry.py`: tool definitions + allowlist.
- `src/backend/tools/runner.py`: runs tools with subprocess isolation.
- `src/backend/tools/schemas/*.json`: input/output schemas.

### 6.2 Execution rules (hard constraints)
- Tools execute **only** as a direct consequence of a user message in the active session.
- Store a tool-run record as an append-only event:
  - `type="tool_run"`
  - `payload_json` includes: `tool_id`, `input_json`, `output_json`, `exit_code`, `started_at`, `ended_at`, `artifacts`.
- Tool outputs must never mutate message history; attach artifacts separately.

### 6.3 UI: explicit tool invocation
Do not let the model “secretly” trigger tools.
- Add explicit UI controls (buttons/forms) for tool runs, or a clearly gated “Run tool” confirmation step.
- If a model suggests a tool run, it must ask for an explicit user-triggered action, not execute automatically.

**Verification commands**
- Attempt to run a non-allowlisted tool → clear structured error.
- Confirm every tool run has a corresponding `events` row with full I/O.
- Confirm app idle state does no work (no polling / no hidden calls).

---

## Phase 7 — Performance, Packaging, No-Background-Agents Guarantee
**Goal:** Meet constraints and prove there is no unintended autonomy.

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

## Suggested Execution Order (Practical)
1. Phase 5.2 Regenerate (lowest risk: append-only events + new assistant messages).
2. Phase 5.1 Clarifying-question gate (policy module + tests/fixtures if added later).
3. Phase 6 Tool sandbox skeleton (registry + runner + one safe demo tool like “read file” or “list directory” with strict allowlist).
4. Phase 6 UI tool invocation + event/audit trail.
5. Phase 7 measurement + packaging plan + no-background-agents proof.

## Quick “Don’t Accidentally Break PRD” Checklist
- Did you add any `UPDATE`/`DELETE` path for `messages`? (must remain impossible)
- Did you make UI call the model server directly? (must remain impossible)
- Did any preference affect behavior before approval? (must remain impossible)
- Did you introduce any timer/background thread/cron-like behavior? (must remain impossible)
- Can every persisted change be explained and traced to an explicit user action? (must remain true)

