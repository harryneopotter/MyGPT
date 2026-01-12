from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

_AMBIGUOUS_SINGLE_WORDS = {
    "this",
    "that",
    "it",
    "one",
    "thing",
    "stuff",
}

_AMBIGUOUS_PHRASES = (
    "do it",
    "do that",
    "do the thing",
    "help me",
    "help with this",
    "fix it",
)


@dataclass(frozen=True)
class PolicyDecision:
    action: Literal["answer", "clarify"]
    question: str | None = None
    rationale: str | None = None


def evaluate_clarifying_question(user_message: str, *, previous_message_role: str | None = None) -> PolicyDecision:
    """Return whether we should pause to ask for clarification.

    The heuristics intentionally err on the side of *not* asking questions. We only
    request clarification for extremely ambiguous one or two-word directives or for
    acknowledgements that lack any actionable instruction relative to the prior
    assistant turn.
    """

    normalized = user_message.strip()
    if not normalized:
        return PolicyDecision(
            action="clarify",
            question="I didn\'t catch what you\'d like me to do. Could you restate your intent?",
            rationale="blank_message",
        )

    lowered = normalized.lower()
    if lowered in _AMBIGUOUS_SINGLE_WORDS:
        return PolicyDecision(
            action="clarify",
            question="What specifically should I work on?",
            rationale="single_ambiguous_token",
        )

    if lowered in {"ok", "okay", "yes", "sure", "maybe"} and previous_message_role != "assistant":
        # These acknowledgements are fine if they are answering an assistant
        # question, but if we do not have an open question we need clarification.
        return PolicyDecision(
            action="clarify",
            question="Could you describe the task or question you want me to handle?",
            rationale="ack_without_context",
        )

    if any(lowered.startswith(phrase) for phrase in _AMBIGUOUS_PHRASES):
        return PolicyDecision(
            action="clarify",
            question="You mentioned needing help, but I need the concrete task. What should I produce?",
            rationale="generic_help_request",
        )

    return PolicyDecision(action="answer")
