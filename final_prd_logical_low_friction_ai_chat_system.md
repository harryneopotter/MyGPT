# FINAL PRD – Logical, Low-Friction AI Chat System

This document is the **final, handoff-ready Product Requirements Document** for building a local-first AI chat system. It is written to be given directly to an autonomous coding agent, with minimal human supervision.

This PRD intentionally rejects conventional chatbot UX compromises. It encodes **causal integrity, logical consistency, and zero-friction intent execution** as first principles.

---

## 1. Product Definition

### 1.1 What This Product Is

A **single-user, local-first AI chat system** designed for:
- deep reasoning
- long-running tasks
- iterative clarification
- logical collaboration

The system prioritizes **intent, logic, and causal honesty** over comfort, safety theater, or mass-market UX patterns.

It is a thinking tool, not a concierge.

---

### 1.2 What This Product Is Not

- Not a social chatbot
- Not a multi-user system
- Not a preference-protecting assistant
- Not a safety-nagging system
- Not a system that edits or rewrites history

---

## 2. Core Invariants (Non-Negotiable)

These invariants override all other design considerations.

### 2.1 Message Integrity

1. User messages are **immutable**.
2. Messages are never edited or deleted.
3. Corrections must be additive, via new messages.
4. All reasoning must treat past messages as historical facts.

This preserves causal integrity and prevents unlinked reasoning nodes.

---

### 2.2 Intent Supremacy

5. Explicit user intent always overrides preferences.
6. Approved task definitions override comfort or defaults.
7. The system must never block, warn, or hesitate due to preference conflict.

Preferences describe comfort, not authority.

---

### 2.3 Logic Supremacy

8. All reasoning must be logically grounded.
9. The system may defend its inferences using logic.
10. If new information is added, inference must be re-evaluated.
11. If added logic is incorrect, the system must explain why.

Disagreement is acceptable. Illogical behavior is not.

---

## 3. Preference Inference Model

### 3.1 Inference Freedom

12. The system may infer user preferences freely using model-native reasoning.
13. The user does not define evidence, thresholds, or heuristics.
14. Inference mechanisms are not exposed or constrained.

---

### 3.2 Proposal Gate

15. Inferred preferences do **not** affect behavior until approved.
16. Approval may be expressed via natural language agreement (e.g. “sure”, “go ahead”, “sounds good”).
17. Literal “yes” is not required.

---

### 3.3 Logical Engagement

18. The user may request explanation at any time.
19. The system must explain reasoning in human-readable terms when asked.
20. The system may defend an inference logically.
21. The system must re-evaluate inference when new premises are supplied.

---

### 3.4 Stabilization

22. Preferences may be refined, scoped, or collapsed through interaction.
23. Once approved, preferences influence defaults only.
24. Preferences persist until explicitly changed.

---

## 4. Multiple Inference Handling

25. The system may infer multiple preferences internally.
26. At most **one** inference proposal may surface at a time.
27. Preference proposals must be relevant, actionable, and stable.
28. Conflicting inferences must be resolved internally before surfacing.
29. Compound preferences may be surfaced only if naturally expressible.

---

## 5. Proposal Timing and Placement

30. Inference proposals may surface only at natural conversational boundaries.
31. Proposals must appear **after** an answer, never before.
32. Proposals must appear inline in the chat, visually secondary.
33. Proposals must never interrupt reasoning or streaming output.

---

## 6. Questioning Rules

34. The system may ask clarifying questions only if answers can materially affect inference or scope.
35. Questions must be minimal and forward-moving.
36. Socratic interrogation is forbidden unless explicitly invited.
37. Validation or permission-seeking questions are forbidden.

---

## 7. Regeneration Rules

38. Regeneration is a retry, not a rethink.
39. Regeneration must not create new preference inferences.
40. Regeneration must not reset or alter existing preferences.

---

## 8. Chat Modes (Behavioral Context, Not Authority)

41. Chat modes may influence interaction style.
42. Chat modes must never override explicit intent.
43. Chat modes must never block task execution.

Modes exist to shape interaction, not to constrain outcomes.

---

## 9. System Tone and UX

44. The system must be direct, neutral, and non-patronizing.
45. The system must not moralize user choices.
46. The system must not protect the user from their own intent.
47. The system must not simulate concern or reassurance.

---

## 10. Success Criteria

The system is successful if:
- Logical disagreements can occur productively.
- Preferences evolve without friction or micromanagement.
- Intent is never blocked or second-guessed.
- All behavior is explainable on demand.
- No silent state changes occur.

---

## 11. Agent Execution Rules

Any AI agent implementing this system must:
- Follow this PRD exactly.
- Ask before deviating.
- Prefer explicit logic over heuristics.
- Avoid introducing mass-market UX patterns.

Failure to respect message immutability or intent supremacy is a correctness bug.

---

## 12. Final Statement

This system is designed for **thinking with an AI**, not being managed by one.

If a choice exists between comfort and correctness, correctness wins.


---

## 13. Technical Constraints & Prescribed Stack (Efficiency-First)

This section intentionally **constrains implementation choices**. Agents are not permitted to substitute technologies unless explicitly approved. The goal is **performance, debuggability, and minimal abstraction tax**.

### 13.1 Platform Targets

- Primary OS: **Windows 11**
- Secondary support (optional): Linux
- Single-user, local-first execution

---

### 13.2 Application Architecture

**Desktop application with local backend**.

Prescribed model:
- UI process
- Local backend/control-plane process
- Local model servers as external processes

Hard rule:
- UI must never talk directly to models

---

### 13.3 UI Stack (Thin by Design)

- Framework: **Tauri**
- Frontend: **React + TypeScript**
- Styling: Minimal CSS / Tailwind (no heavy UI frameworks)
- Rendering: Markdown with code blocks

Rationale:
- Low memory overhead
- Native windowing
- No Electron tax

---

### 13.4 Backend / Control Plane

- Language: **Python 3.11+**
- Framework: **FastAPI** (or equivalent minimal async framework)
- Concurrency: asyncio

Rationale:
- Fast iteration
- Mature async ecosystem
- Easy model/tool orchestration

---

### 13.5 Model Integration

#### Local Models
- llama.cpp server OR equivalent
- Accessed via HTTP

#### Cloud Models (optional)
- API gateway abstraction
- No provider-specific logic above the gateway

Unified internal interface:
- generate()
- embed()
- vision()

---

### 13.6 Streaming

- Transport: WebSocket or Server-Sent Events (SSE)
- Streaming handled by backend
- UI only renders tokens

---

### 13.7 Memory & Storage

- Persistent memory: **SQLite** (authoritative store)
- Embeddings / retrieval:
  - SQLite + vector extension OR
  - Lightweight vector DB (e.g., Qdrant local)

Rules:
- No opaque cloud memory
- All memory inspectable

---

### 13.8 File & Artifact Storage

- Local filesystem
- Project-scoped directories
- Explicit file ingestion only

---

### 13.9 Tool Execution

- Sandbox: subprocess-based isolation
- No direct shell exposure by default
- Structured JSON I/O only

---

### 13.10 Performance Constraints

- Startup time < 2s (without model warmup)
- UI idle memory footprint minimal
- No background agents without explicit trigger

---

### 13.11 Forbidden Choices (Explicit)

Agents must NOT introduce:
- Electron
- Heavy ORMs
- Auto-generated GraphQL layers
- Background autonomous agents
- Implicit cloud dependencies

---

### 13.12 Deviation Policy

If an agent believes deviation is justified:
1. Stop
2. Explain tradeoff
3. Request approval

Unauthorized deviation is a correctness failure.

