"""Usage-estimate phrasings for the same capacity decision collapse to one.

An 'has this been established?' check is the same remaining decision as a
direct request for those usage figures. Distinct capacity decisions stay
separate. History and the original request are not rewritten.
"""

from app.decisions import (
    CAPACITY_COLLECTION_QUESTION,
    apply_reconciled_project_state,
    question_text,
    reconcile_open_questions,
)

VOLUME_QUESTION = (
    "What is the expected user volume and concurrent load for the web application?"
)
ESTABLISHED_QUESTION = (
    "Have expected number of users, active installations, daily inspections, "
    "photo uploads, and peak concurrent users been established?"
)
DISK_QUESTION = "What disk capacity is required for backup retention?"
REQUEST = "Build a first-release inspection app for field technicians."
HISTORY = [
    {
        "question": "What is the target delivery timeline?",
        "answer": "The first release should launch in 12 weeks.",
    }
]


def _state(questions: list[str]) -> dict:
    return {
        "user_request": REQUEST,
        "clarification_history": [dict(item) for item in HISTORY],
        "discovery": {
            "problem": "Inspection app",
            "users": ["Field technicians"],
            "stakeholders": [],
            "unknowns": list(questions),
            "clarification_questions": [],
        },
        "requirements": {"open_questions": list(questions)},
        "validation": {"status": "READY", "non_blocking_questions": list(questions)},
    }


def _active(updates: dict) -> list[str]:
    return [
        question_text(item)
        for item in (updates.get("requirements") or {}).get("open_questions") or []
    ]


def _capacity_items(questions: list[str]) -> list[str]:
    return [
        item
        for item in questions
        if any(
            marker in item.lower()
            for marker in ("volume", "concurrent", "user count", "established")
        )
    ]


def test_volume_and_established_capacity_phrasings_collapse_to_one():
    result = reconcile_open_questions(
        [VOLUME_QUESTION, ESTABLISHED_QUESTION],
        {"user_request": REQUEST},
    )
    texts = [question_text(item) for item in result]
    capacity = _capacity_items(texts)
    assert len(capacity) == 1, texts
    survivor = capacity[0]
    assert "established" not in survivor.lower()
    assert any(
        marker in survivor.lower()
        for marker in ("volume", "concurrent", "user count", "peak")
    )
    assert "what" in survivor.lower()


def test_second_state_update_does_not_restore_capacity_duplicate():
    original_history = [dict(item) for item in HISTORY]
    incoming = _state([VOLUME_QUESTION, ESTABLISHED_QUESTION, VOLUME_QUESTION])
    first = apply_reconciled_project_state(incoming)
    assert len(_capacity_items(_active(first))) == 1
    second = apply_reconciled_project_state(
        {
            "user_request": REQUEST,
            "clarification_history": original_history,
            **first,
        }
    )
    active = _active(second)
    assert len(_capacity_items(active)) == 1
    assert second["discovery"]["unknowns"] == active
    assert second["validation"]["non_blocking_questions"] == active
    assert incoming["user_request"] == REQUEST
    assert incoming["clarification_history"] == original_history


def test_distinct_capacity_decisions_remain_separate():
    result = reconcile_open_questions(
        [VOLUME_QUESTION, DISK_QUESTION, ESTABLISHED_QUESTION],
        {"user_request": REQUEST},
    )
    texts = [question_text(item) for item in result]
    assert DISK_QUESTION in texts
    assert len(_capacity_items(texts)) == 1
    assert len(texts) == 2


def test_original_request_and_history_are_unchanged():
    state = _state([VOLUME_QUESTION, ESTABLISHED_QUESTION])
    original_history = [dict(item) for item in state["clarification_history"]]
    apply_reconciled_project_state(state)
    assert state["user_request"] == REQUEST
    assert state["clarification_history"] == original_history
    assert state["clarification_history"] == HISTORY


def test_established_only_capacity_question_becomes_estimate_request():
    result = reconcile_open_questions(
        [ESTABLISHED_QUESTION, ESTABLISHED_QUESTION],
        {"user_request": REQUEST},
    )
    texts = [question_text(item) for item in result]
    assert texts == [CAPACITY_COLLECTION_QUESTION]
    assert "established" not in texts[0].lower()
