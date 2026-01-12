# Deviation Policy

The PRD intentionally constrains implementation choices. Deviating without approval is a correctness failure.

**Invariant supremacy:** No deviation may trade off or weaken message immutability, intent supremacy, causal traceability, user inspectability, or the prohibition of hidden autonomy. Performance, UX, or developer ergonomics benefits are invalid justifications if any core invariant is impacted.

> **PRD Supremacy Clause:** In any ambiguity or conflict, the FINAL PRD – Logical, Low-Friction AI Chat System governs. Interpretations that improve comfort, UX, performance, or developer convenience at the expense of intent supremacy, causal integrity, or inspectability are forbidden.

## When a Deviation Is Allowed
Request approval only when you can show a concrete benefit that does not affect or reinterpret any core invariant defined in the FINAL PRD. The deviation must not violate message integrity, intent supremacy, or logic supremacy.

## Required Process
1. **Stop** work on the deviating path.
2. **Explain the tradeoff** in plain language (what breaks, what improves, what it costs).
3. **Propose alternatives** that stay within the PRD.
4. **Request explicit approval** before implementing.

## What Always Requires Explicit Approval
- Substituting the prescribed stack (e.g., replacing Tauri/React/TS, Python 3.11+/FastAPI, SQLite).
- Introducing any forbidden-by-default item (Electron, heavy ORM, GraphQL layers, background autonomous agents, implicit cloud dependencies).
- Changing any rule that affects: message immutability, preference approval gating, “no silent state changes”, or UI↔model separation.

## Deviation Request Template (Use in PR or Issue)
**Summary:** (1 sentence)
**Motivation:** (why PRD-compliant options fail)
**Proposed change:** (what you want to do)
**Alternatives considered:** (PRD-compliant options + why rejected)
**Risks / costs:** (perf, complexity, lock-in)
**PRD impact:** (which numbered sections/invariants are affected)
**Approval asked from:** (repo owner/maintainer)
