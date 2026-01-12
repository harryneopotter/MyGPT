# Agent Guidelines — Operational Quick Reference

Purpose
- Canonical quick reference for human and automated agents working in this repository. Operationalizes PRD invariants into actionable rules, examples, and minimal enforcement suggestions.

Scope
- Applies to contributors, bots, and automated processes that read or modify repo contents, create PRs, or run CI.

Quick rules (canonical, with PRD pointers)
1. Message immutability (PRD §2.1): Never edit or delete user messages; corrections are additive.
2. Intent supremacy (PRD §2.2): Explicit user intent always overrides preferences; do not block or refuse based on inferred preferences.
3. No background autonomy (PRD §13.11): No scheduled/periodic/autonomous runs; everything must be explicitly user-triggered.
4. Forbidden tech (PRD §13.11): Do not introduce Electron, heavy ORMs, auto-generated GraphQL layers, implicit cloud dependencies, or background autonomous agents without formal approval.
5. Logic supremacy (PRD §2.3): Reasoning must be logically grounded; re-evaluate on new premises.
6. No silent state changes: All state changes must be attributable to an explicit user message or an approved preference change.
7. Inspectability: Memory must be inspectable; avoid opaque cloud-only memory.

MUST DO (concrete)
- Follow PRD exactly; cite relevant PRD sections in any design/PR that could affect invariants.
- For "look into X and create PR" work: investigate → implement minimal fix → add tests → run diagnostics/build/tests → create PR referencing the original issue and PRD implications.
- Run lsp_diagnostics on changed files; run build and tests where applicable.
- Add tests when behavior or invariants are affected (e.g., message immutability).
- If you believe deviation is justified: STOP → document trade-offs → request approval per docs/deviation-policy.md.

MUST NOT DO (concrete)
- Never edit or delete existing user messages.
- Never introduce forbidden tech or background autonomous agents without documented approval.
- Never suppress type errors with `as any`, `@ts-ignore`, or `@ts-expect-error`.
- Never add hidden state changes or silent automation.

Examples (how to handle common requests)
- "Look into X and create PR" workflow:
  1. Reproduce / write a failing test (captures intended behavior).
  2. Search codebase (grep/ast_grep).
  3. Make the smallest, safest change (bugfix rule).
  4. Add tests and docs if behavior changes.
  5. Run lsp_diagnostics, build, tests.
  6. Create PR: title, summary, rationale, list of files changed, tests added, CI results, and link to issue.
  7. If an invariant is touched → include deviation request + approval link.

- Ambiguity policy:
  - If one clarifying question can resolve it, ask exactly one concise question.
  - If ambiguity materially affects scope or safety, stop and request clarification.

Enforcement suggestions (low-effort, high-value)
- PR template additions (checkboxes):
  - "Does this change affect any PRD invariant? (Yes/No). If yes, link to deviation approval."
  - "Tests added / lsp_diagnostics clean / build & tests passed"
- CI checks (simple first pass):
  - GitHub Action that greps for forbidden keywords (e.g., electron, cron/schedule imports, celery/APScheduler, background_task usage).
  - Lint step fails PR on matches—small maintainable rule set.
- Test coverage:
  - Add a backend test that asserts attempts to edit/delete a user message fail (or are logged and rejected).
- Process:
  - Changes that would introduce forbidden tech must include a deviation request and explicit approval before merge.

Where to find more
- final_prd_logical_low_friction_ai_chat_system.md (invariants, forbidden tech, no-background agents)
- docs/deviation-policy.md (how to request approval)
- docs/implementation-plan.md (verification checklists)
- docs/approval-drills.md (manual test scenarios)

Notes
- This document is a living operational guide. If you believe additions are needed (examples, automation rules, enforcement scripts), propose them as a regular PR with tests and a rationale referencing the PRD.

---

(End of docs/agent-guidelines.md)
