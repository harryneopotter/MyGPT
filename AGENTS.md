# Repository Guidelines

## Purpose
This repository currently contains a single, handoff-ready Product Requirements Document (PRD) for a “Logical, Low-Friction AI Chat System”. Contributions should improve clarity, internal consistency, and implementability without changing the intent of the spec.

## Project Structure & Module Organization
- `final_prd_logical_low_friction_ai_chat_system.md`: Source-of-truth PRD. Keep section numbers stable when possible so external references don’t break.
- `docs/`: Guardrails and process docs that operationalize the PRD (e.g., `docs/guardrails.md`, `docs/deviation-policy.md`).
- `docs/implementation-plan.md`: Phase-gated implementation plan with checklists.
- `docs/agent-guidelines.md`: Operational quick reference consolidating PRD invariants into MUST DO / MUST NOT DO actionable rules (new)
- `docs/approval-drills.md`: Manual scenarios to prevent accidental preference approval.
- If code is added later, prefer: `src/` (runtime), `tests/` (automated tests), `docs/` (supporting docs), `assets/` (diagrams/images).

## Development Commands
No build/test toolchain is defined yet. Useful local checks:
- Quick preview (PowerShell): `Get-Content .\final_prd_logical_low_friction_ai_chat_system.md -TotalCount 60`
- Find a term across the repo: `Select-String -Path .\*.md -Pattern "invariant|integrity|causal" -CaseSensitive:$false`
- Validate Markdown rendering by previewing in your editor (VS Code Markdown preview or equivalent).

## Writing Style & Naming Conventions
- Use clear, declarative headings and short paragraphs; prefer bullet lists for requirements.
- Keep terminology consistent (e.g., “invariant”, “integrity”, “causal honesty”).
- Avoid renaming major sections; add clarifications via new subsections when needed.
- For new docs, use `kebab-case.md` names (e.g., `docs/architecture-overview.md`).

## Testing / Validation Guidelines
- There are no automated tests today. Validate changes by:
  - Checking for broken heading hierarchy and numbering.
  - Ensuring requirements are unambiguous (inputs, outputs, and constraints).
  - Verifying any commands/paths you introduce are copy-pastable on Windows.

## Commit & Pull Request Guidelines
No Git history exists in this repo right now; if/when Git is initialized, use Conventional Commits:
- Examples: `docs: clarify message integrity invariant`, `docs: add glossary for key terms`
PRs should include a short summary, rationale, and a list of touched sections (by heading).
