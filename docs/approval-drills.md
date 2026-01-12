# Approval Drills (Manual Self-Test)

Use this to learn how *your* replies behave when the system asks to approve an inferred preference (PRD §3.2). The goal is to avoid accidental persistent preference approvals when you meant “okay” about the main answer.

> **PRD Supremacy Clause:** In any ambiguity or conflict, the FINAL PRD – Logical, Low-Friction AI Chat System governs. Interpretations that improve comfort, UX, performance, or developer convenience at the expense of intent supremacy, causal integrity, or inspectability are forbidden.

## How to Use
1. Read the assistant turn (answer + a preference proposal).
2. Write the reply you would naturally send.
3. Compare against the “What can go wrong” note.
4. If you want to be unambiguous, use the “Safe reply” pattern.

## Safe Reply Patterns (Unambiguous)
- Approve: `Approve preference: <short restatement>` (or click an Approve button if present)
- Reject: `Reject preference` or `Do not save that preference`
- Discuss (no approval): `Explain why you inferred that` / `What evidence supports that?`
- Proceed with task (no approval): `Continue with the task; do not change preferences`

## Scenarios

### 1) Acknowledging the answer (risk: accidental approval)
Assistant: (answers) + Proposal: “Prefer concise answers by default. Approve?”
- What can go wrong: replying “Sounds good” could be interpreted as approving the preference.
- Safe reply: `Continue with the task; do not change preferences` OR `Approve preference: concise answers`

### 2) Asking “why” (risk: novice system treats any engagement as approval)
Assistant: (answers) + Proposal: “Prefer more formal tone. Approve?”
- What can go wrong: a naive system might treat *any* positive/neutral engagement as approval.
- Safe reply: `Explain why you inferred that` (explicitly non-approval)

### 3) Mixed message (risk: “sure” attaches to wrong target)
Assistant: (answers) + Proposal: “Prefer bullet lists. Approve?”
User intent: you want bullet lists *only for this response*.
- What can go wrong: “Sure, do bullets” becomes a persistent default.
- Safe reply: `Use bullet lists for this answer only; do not save as a preference`

### 4) Conflicting intent (risk: preference overrides intent)
Assistant: Proposal: “Prefer shorter output.” Approve?
User intent: “Write the full detailed spec.”
- What can go wrong: an implementation might obey the preference and shorten output anyway (violates intent supremacy).
- Safe reply: `My intent overrides: produce full detail. Do not save shorter-output preference.`

### 5) Approval with a condition (risk: partial approval becomes permanent)
Assistant: Proposal: “Prefer terse responses. Approve?”
User: “Sure, but only for code reviews.”
- What can go wrong: system stores “terse everywhere” instead of scoped preference.
- Safe reply: `Approve preference (scoped): terse responses only for code reviews`

### 6) Silent drift (risk: pre-approval influence)
Assistant: Proposal: “Prefer minimal clarifying questions. Approve?”
- What can go wrong: even before approval, the system changes question-asking behavior (forbidden by `docs/guardrails.md`).
- Safe reply: `Do not apply until approved. Explain what would change if approved.`

### 7) Proposal missed (risk: you respond to the “last thing”)
Assistant: (answers) + Proposal at bottom, visually secondary.
- What can go wrong: “OK” is sent reflexively to end the turn and is treated as approval.
- Safe reply: `OK on the answer; no preference changes`

### 8) Multiple actionable items (risk: one “yes” approves the wrong one)
Assistant: (answers) + Proposal + “Should I proceed with X?”
- What can go wrong: you answer the proceed-question; system interprets as proposal approval too.
- Safe reply: `Proceed with X; do not approve the preference proposal`

## Success Criteria (You)
You “pass” if, in a week of normal use, you can reliably:
- Approve only when you explicitly intend to create a persistent default.
- Reject/discuss proposals without accidentally approving them.
- Override preferences with explicit intent without friction.

