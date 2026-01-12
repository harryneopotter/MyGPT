# Guardrails (Non-Negotiables)

This project implements the PRD in `final_prd_logical_low_friction_ai_chat_system.md`. Treat the guardrails below as correctness constraints, not “nice to have” UX.

> **PRD Supremacy Clause:** In any ambiguity or conflict, the FINAL PRD – Logical, Low-Friction AI Chat System governs. Interpretations that improve comfort, UX, performance, or developer convenience at the expense of intent supremacy, causal integrity, or inspectability are forbidden.

## Core Invariants
- **Message integrity:** user messages are immutable; never edit/delete. Corrections happen only by appending a new message that references what changed.
- **Intent supremacy:** explicit user intent overrides inferred/approved preferences; never block, warn, or hesitate because of a preference conflict.
- **Logic supremacy:** reasoning and explanations must be logically grounded; re-evaluate when premises change and may proactively explain or defend logical disagreements when user intent or conclusions are internally inconsistent.

## Preference Inference Rules
- Preferences may be inferred internally, but **must not change behavior until approved** (natural-language approval counts; not only “yes”).
- **Pre-approval non-influence:** Inferred preferences must not influence reasoning paths, question framing, verbosity, defaults, prioritization, or response structure until explicitly approved. Prior to approval, inferred preferences may exist only as inert internal hypotheses.
- Surface **at most one** preference proposal at a time, and only at natural boundaries **after** answering (never pre-empt or interrupt streaming).
- Regeneration is a retry: it must not create new preference inferences or reset existing preferences.

## Questioning & Tone
- Ask clarifying questions only when answers materially affect scope/inference; keep them minimal and forward-moving.
- No validation/permission-seeking questions (“Are you sure…?”) and no unsolicited Socratic interrogation.
- Tone: direct, neutral, non-patronizing; no moralizing, simulated concern, or “protecting the user from intent”.

## Technical Guardrails (From PRD)
- UI must not talk directly to models; all model/tool access goes through the local backend/control plane.
- Local-first and inspectable storage: SQLite as authoritative store; no opaque cloud memory.
- Tool execution must be sandboxed (structured JSON I/O; no raw shell exposure by default).
- Forbidden by default: Electron, heavy ORMs, auto-generated GraphQL layers, background autonomous agents, implicit cloud dependencies.

## Definition of Done (Quick Checks)
- No feature introduces silent state changes; all persisted changes are attributable to a user message or an approved preference change.
- Any “deviation” from the PRD includes an explicit approval request (see `docs/deviation-policy.md`).
