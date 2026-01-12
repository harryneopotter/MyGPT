# State & Storage Guardrails

This system is local-first. Storage exists to preserve causal history and make state changes inspectable.

> **PRD Supremacy Clause:** In any ambiguity or conflict, the FINAL PRD – Logical, Low-Friction AI Chat System governs. Interpretations that improve comfort, UX, performance, or developer convenience at the expense of intent supremacy, causal integrity, or inspectability are forbidden.

## Message History (Immutable)
- Store user/assistant messages as an **append-only** log. Never update or delete message rows.
- Corrections are new messages that reference the prior message (e.g., `corrects_message_id`), not edits.
- Treat past messages as historical facts in all reasoning; do not “rewrite” earlier context.

## Preferences (Infer → Propose → Approve)
- Separate **inferred** preferences from **approved** preferences.
- Inference may be internal, but behavior changes must be keyed only off approved preferences.
- Record approvals as first-class events (who/what/when), not as hidden state.

## No Silent State Changes
- Every persisted change must be attributable to:
  - a specific user message (explicit intent), or
  - an approved preference change, or
  - an explicit user-triggered tool/action.
- Maintain an audit trail for state transitions (append-only event log recommended).

### Event Non-Authority Rule
**Event non-authority rule:** No event, log entry, or internal record may alter runtime behavior, defaults, or reasoning unless its effect is user-visible and explainable via the chat transcript on request. Events are descriptive, not authoritative.

## Files & Artifacts
- Keep artifacts in project-scoped directories (e.g., `artifacts/` or per-chat folders) and ingest files only via explicit user action.
- Avoid implicit cloud sync or remote storage; if optional cloud is added later, it must sit behind a gateway and be opt-in.

## Minimal Suggested SQLite Shape (Non-Binding)
- `messages(id, role, content, created_at, corrects_message_id NULL)`
- `preference_proposals(id, text, rationale, created_at, status)`
- `preferences(id, key, value, approved_at, scope)`
- `events(id, type, payload_json, created_at, causality_message_id NULL)`
