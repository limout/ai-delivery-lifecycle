"""Exact duplicate questions must not accumulate in active lists.

Semantic paraphrase collapsing is covered elsewhere. These tests only
prove that identical wording (including trivial whitespace) becomes one
active question at the state-update boundary.
"""

from app.decisions import (
    apply_reconciled_project_state,
    question_text,
    reconcile_open_questions,
)

USERS_QUESTION = "Who will use the first release, and what will they do in it?"
VOLUME_QUESTION = "What is the expected user volume and concurrent load?"
REQUEST = "Build a first-release inspection app for field technicians."
HISTORY = [
    {
        "question": "What is the target delivery timeline?",
        "answer": "The first release should launch in 12 weeks.",
    }
]


def _state(copies: int) -> dict:
    questions = [USERS_QUESTION] * copies
    return {
        "user_request": REQUEST,
        "clarification_history": [dict(item) for item in HISTORY],
        "discovery": {
            "problem": "Inspection app",
            "users": ["Field technicians"],
            "stakeholders": [],
            "unknowns": list(questions),
            "clarification_questions": list(questions),
        },
        "requirements": {"open_questions": list(questions)},
        "validation": {"status": "READY", "non_blocking_questions": list(questions)},
    }


def _active(updates: dict) -> list[str]:
    return [
        question_text(item)
        for item in (updates.get("requirements") or {}).get("open_questions") or []
    ]


def test_repeated_identical_questions_become_one_active_question():
    copies = [USERS_QUESTION] * 40
    copies[7] = f"  {USERS_QUESTION}  "
    copies[19] = USERS_QUESTION.replace("  ", " ")
    result = reconcile_open_questions(copies, {"user_request": REQUEST})
    texts = [question_text(item) for item in result]
    assert texts.count(USERS_QUESTION) == 1
    assert len(texts) == 1


def test_second_state_update_does_not_reintroduce_duplicates():
    original_history = [dict(item) for item in HISTORY]
    first = apply_reconciled_project_state(_state(25))
    assert _active(first).count(USERS_QUESTION) == 1
    second = apply_reconciled_project_state(
        {
            "user_request": REQUEST,
            "clarification_history": original_history,
            **first,
        }
    )
    assert _active(second).count(USERS_QUESTION) == 1
    assert second["discovery"]["unknowns"].count(USERS_QUESTION) == 1
    assert second["validation"]["non_blocking_questions"].count(USERS_QUESTION) == 1
    assert second["discovery"]["unknowns"] == _active(second)
    assert second["validation"]["non_blocking_questions"] == _active(second)


def test_differently_worded_questions_remain_separate():
    result = reconcile_open_questions(
        [USERS_QUESTION, VOLUME_QUESTION, USERS_QUESTION],
        {"user_request": REQUEST},
    )
    texts = [question_text(item) for item in result]
    assert texts == [USERS_QUESTION, VOLUME_QUESTION]


def test_original_request_and_history_are_unchanged():
    state = _state(12)
    original_history = [dict(item) for item in state["clarification_history"]]
    apply_reconciled_project_state(state)
    assert state["user_request"] == REQUEST
    assert state["clarification_history"] == original_history
    assert state["clarification_history"] == HISTORY
