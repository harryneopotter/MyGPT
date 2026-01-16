from src.backend.response_policy import evaluate_clarifying_question


def test_answers_clear_request():
    decision = evaluate_clarifying_question("Please summarize the PRD.")
    assert decision.action == "answer"
    assert decision.question is None


def test_clarifies_blank_message():
    decision = evaluate_clarifying_question("   ")
    assert decision.action == "clarify"
    assert decision.question
    assert decision.rationale == "blank_message"


def test_clarifies_single_word_ambiguous():
    decision = evaluate_clarifying_question("this")
    assert decision.action == "clarify"
    assert decision.question
    assert decision.rationale == "single_ambiguous_token"


def test_clarifies_generic_help_request():
    decision = evaluate_clarifying_question("help me")
    assert decision.action == "clarify"
    assert decision.question
    assert decision.rationale == "generic_help_request"


def test_ack_without_context_clarifies():
    decision = evaluate_clarifying_question("ok", previous_message_role=None)
    assert decision.action == "clarify"
    assert decision.question
    assert decision.rationale == "ack_without_context"


def test_ack_after_assistant_question_answers():
    decision = evaluate_clarifying_question("ok", previous_message_role="assistant")
    assert decision.action == "answer"
    assert decision.question is None
