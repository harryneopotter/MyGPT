# PRD Deviation Corrections – Required Amendments

This document specifies **exact, minimal, and mandatory changes** required in the four supporting project documents to remove deviation risk and fully align them with the **FINAL PRD – Logical, Low-Friction AI Chat System**.

This is not a rewrite. Each change is surgical, enforceable, and intended to eliminate agent escape hatches without expanding scope.

---

## 1. Guardrails (Non-Negotiables)

### 1.1 Strengthen Preference Non-Influence (REQUIRED)

**Problem:**
Current language allows inferred preferences to subtly influence reasoning, framing, or defaults prior to approval.

**Add the following bullet under “Preference Inference Rules”:**

> **Pre-approval non-influence:** Inferred preferences must not influence reasoning paths, question framing, verbosity, defaults, prioritization, or response structure until explicitly approved. Prior to approval, inferred preferences may exist only as inert internal hypotheses.

**Rationale:**
Aligns with PRD §§2.2, 3.2, and 10. Prevents silent behavioral drift.

---

### 1.2 Remove Passive Logic Defense Constraint (REQUIRED)

**Problem:**
Logic defense is framed as reactive (“when asked”), weakening logic supremacy.

**Replace the sentence:**
> “re-evaluate when premises change and explain disagreements when asked.”

**With:**
> “re-evaluate when premises change and may proactively explain or defend logical disagreements when user intent or conclusions are internally inconsistent.”

**Rationale:**
Restores PRD §2.3 logic supremacy and allows adversarial honesty.

---

## 2. State & Storage Guardrails

### 2.1 Constrain Event Log Authority (REQUIRED)

**Problem:**
The event system can be abused as an invisible behavior modifier.

**Add a new subsection under “No Silent State Changes”:**

> **Event non-authority rule:** No event, log entry, or internal record may alter runtime behavior, defaults, or reasoning unless its effect is user-visible and explainable via the chat transcript on request. Events are descriptive, not authoritative.

**Rationale:**
Enforces PRD §10 (“All behavior is explainable on demand”).

---

## 3. Deviation Policy

### 3.1 Establish Invariant Supremacy Over “Benefits” (CRITICAL)

**Problem:**
“Concrete benefit” language allows performance or ergonomics to override causal integrity.

**Add the following paragraph at the top of the document:**

> **Invariant supremacy:** No deviation may trade off or weaken message immutability, intent supremacy, causal traceability, user inspectability, or the prohibition of hidden autonomy. Performance, UX, or developer ergonomics benefits are invalid justifications if any core invariant is impacted.

---

### 3.2 Narrow the Definition of Acceptable Benefit (REQUIRED)

**Replace:**
> “concrete benefit (performance, debuggability, minimal abstraction tax)”

**With:**
> “concrete benefit that does not affect or reinterpret any core invariant defined in the FINAL PRD.”

**Rationale:**
Prevents agent-justified erosion of foundational guarantees.

---

## 4. Implementation Plan (Phased)

### 4.1 Add Negative Compliance Tests (REQUIRED)

**Problem:**
Phases verify functionality but not absence of forbidden behavior.

**Add to Phase 4 (Preference Inference) – Checklist:**

> [ ] Verified that inferred-but-unapproved preferences produce identical reasoning, framing, defaults, and outputs as baseline behavior.
>
> [ ] Verified that no preference inference alters question selection or response structure prior to approval.

---

### 4.2 Explicitly Forbid Tool Autonomy (CRITICAL)

**Problem:**
Tool execution language allows chaining, scheduling, or prefetching.

**Add to Phase 6 – Checklist:**

> [ ] Verified that tools execute only as a direct, immediate consequence of a specific user message and never via chaining, scheduling, background execution, or speculative prefetch.

**Add to Phase 7 – Checklist:**

> [ ] Verified that no tool, model, or subsystem performs work without an explicit user-triggered message in the active session.

---

## 5. Global Addition (Apply to All Four Documents)

**Add the following clause verbatim to each document’s introduction or footer:**

> **PRD Supremacy Clause:** In any ambiguity or conflict, the FINAL PRD – Logical, Low-Friction AI Chat System governs. Interpretations that improve comfort, UX, performance, or developer convenience at the expense of intent supremacy, causal integrity, or inspectability are forbidden.

---

## 6. Change Scope Confirmation

- No new features introduced
- No stack changes
- No UX expansion
- No behavioral loosening

These amendments exist solely to **close agent escape hatches and enforce the PRD as law, not guidance**.

---

**Status:** Mandatory
**Approval required:** No (alignment-only corrections)
**Intended audience:** Autonomous implementation agents and reviewers

