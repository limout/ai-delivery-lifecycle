"""Broad offline questions close once basic behavior is answered.

The unresolved remainder is the conflict-resolution workflow, kept once.
Last-write-wins is not inferred. Distinct storage and load questions stay.

The realistic workflow path is ``workflow_response``: it writes the canonical
list into discovery.unknowns, requirements.open_questions,
validation.non_blocking_questions, the root non_blocking_questions, and
assessment.what_is_uncertain.
"""

from app.api import workflow_response
from app.decisions import apply_reconciled_project_state, question_text, reconcile_open_questions

REQUEST = (
    "Build a mobile inspection app for field technicians. The application is "
    "expected to support field work in remote conditions, but the exact "
    "offline behavior and synchronization rules have not yet been defined. "
    "Photo retention, photo storage capacity, user volume, and hosting also "
    "need clarification."
)
BROAD_OFFLINE = (
    "What is the exact offline behavior and what are the synchronization rules?"
)
CONFLICT_SYNC = (
    "How should the application handle offline data synchronization and "
    "conflict resolution when connectivity is restored?"
)
STORAGE_QUESTION = "What disk capacity is required for photo storage?"
VOLUME_QUESTION = (
    "What is the expected user volume and concurrent load for the web application?"
)
HOSTING_QUESTION = "Which hosting provider and region should be used?"
PHOTO_RETENTION = "Has the proposed three-year photo retention policy been approved?"
OFFLINE_HISTORY_QUESTION = (
    "What are the specific requirements for offline behavior and data "
    "synchronization when technicians work at remote sites with unreliable connectivity?"
)
OFFLINE_ANSWER = (
    "Assigned-job data and checklists are available offline. Users can "
    "perform inspection work offline. Changes are stored locally and "
    "queued. Offline, pending-sync, and failure status must be visible. "
    "Retries must not silently lose or duplicate data. Conflicts must be "
    "detected rather than silently overwriting changes. The exact "
    "conflict-resolution workflow for conflicting synchronized changes "
    "has not yet been defined."
)
HISTORY = [
    {
        "question": OFFLINE_HISTORY_QUESTION,
        "answer": OFFLINE_ANSWER,
    }
]
INCOMING = [
    BROAD_OFFLINE,
    CONFLICT_SYNC,
    STORAGE_QUESTION,
    VOLUME_QUESTION,
    HOSTING_QUESTION,
    PHOTO_RETENTION,
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


def _blob(questions: list[str]) -> str:
    return " ".join(questions).lower()


def _conflict_items(questions: list[str]) -> list[str]:
    return [item for item in questions if "conflict" in item.lower()]


def test_broad_offline_answer_closes_broad_question_and_keeps_one_conflict():
    result = reconcile_open_questions(
        [BROAD_OFFLINE, CONFLICT_SYNC],
        {"user_request": REQUEST, "clarification_history": HISTORY},
    )
    texts = [question_text(item) for item in result]
    blob = _blob(texts)
    assert BROAD_OFFLINE not in texts
    assert "exact offline behavior" not in blob
    assert "synchronization rules" not in blob
    conflict = _conflict_items(texts)
    assert len(conflict) == 1, texts
    assert "last-write" not in blob
    assert "wins" not in blob


def test_unresolved_conflict_workflow_is_not_treated_as_approved():
    result = reconcile_open_questions(
        [BROAD_OFFLINE, CONFLICT_SYNC],
        {"user_request": REQUEST, "clarification_history": HISTORY},
    )
    texts = [question_text(item) for item in result]
    assert _conflict_items(texts)
    joined = _blob(texts)
    assert "last-write-wins" not in joined
    assert "most recent" not in joined
    assert "approved" not in joined or "conflict" in joined


def test_second_reconciliation_does_not_restore_broad_offline():
    incoming = _state(INCOMING)
    original_history = [dict(item) for item in incoming["clarification_history"]]
    first = apply_reconciled_project_state(incoming)
    second = apply_reconciled_project_state(
        {
            "user_request": REQUEST,
            "clarification_history": original_history,
            **first,
        }
    )
    active = _active(second)
    blob = _blob(active)
    assert "exact offline behavior" not in blob
    assert "synchronization rules" not in blob
    assert len(_conflict_items(active)) == 1
    assert STORAGE_QUESTION in active
    assert PHOTO_RETENTION in active
    assert HOSTING_QUESTION in active
    assert any("volume" in item.lower() or "concurrent" in item.lower() for item in active)
    assert incoming["user_request"] == REQUEST
    assert incoming["clarification_history"] == original_history


def test_distinct_storage_and_load_questions_remain_separate():
    result = reconcile_open_questions(
        INCOMING,
        {"user_request": REQUEST, "clarification_history": HISTORY},
    )
    texts = [question_text(item) for item in result]
    assert STORAGE_QUESTION in texts
    assert HOSTING_QUESTION in texts
    assert PHOTO_RETENTION in texts
    assert any("volume" in item.lower() or "concurrent" in item.lower() for item in texts)
    assert len(_conflict_items(texts)) == 1
    assert BROAD_OFFLINE not in texts


def test_original_request_and_history_are_unchanged():
    state = _state(INCOMING)
    original_history = [dict(item) for item in state["clarification_history"]]
    apply_reconciled_project_state(state)
    assert state["user_request"] == REQUEST
    assert state["clarification_history"] == original_history
    assert state["clarification_history"] == HISTORY
    assert OFFLINE_ANSWER in state["clarification_history"][0]["answer"]
    assert state["clarification_history"][0]["question"] == OFFLINE_HISTORY_QUESTION


# ---------------------------------------------------------------------------
# Realistic workflow_response path (production remainder wording)
# ---------------------------------------------------------------------------

WORKFLOW_BROAD = (
    "What are the exact offline behavior and synchronization rules when "
    "mobile connectivity is unreliable?"
)
WORKFLOW_PENDING = (
    "The exact user workflow for resolving conflicts, including the handling "
    "of changes made to the same record by multiple users, still needs to be "
    "defined."
)
WORKFLOW_RESOLVED = (
    "Technicians can access previously synchronized jobs and installation "
    "details offline.",
    "They can complete inspection checklists, capture defects, attach photos "
    "and notes, submit reports, and create follow-up actions while offline.",
    "Changes are persisted locally and queued for synchronization.",
    "Synchronization states must be visible.",
    "Retries must not silently lose or duplicate data.",
    "Conflicts must be detected rather than silently overwriting changes.",
)
WORKFLOW_ANSWER = " ".join(WORKFLOW_RESOLVED) + " " + WORKFLOW_PENDING
WORKFLOW_REQUEST = (
    "Technicians work at remote sites where mobile connectivity may be "
    "unreliable. The exact offline behavior and synchronization rules have "
    "not yet been defined."
)
WORKFLOW_HISTORY = [
    {
        "question": WORKFLOW_BROAD,
        "answer": WORKFLOW_ANSWER,
    }
]
WORKFLOW_PRESERVED = [
    "Should the first release support iOS, Android, or both platforms?",
    "What are the expected user roles and permissions?",
    PHOTO_RETENTION,
    VOLUME_QUESTION,
]


def _workflow_state() -> dict:
    return {
        "user_request": WORKFLOW_REQUEST,
        "clarification_history": [dict(item) for item in WORKFLOW_HISTORY],
        "discovery": {
            "problem": "Field inspection mobile app",
            "users": ["Field technicians"],
            "stakeholders": [],
            "unknowns": [WORKFLOW_BROAD, *WORKFLOW_PRESERVED],
            "clarification_questions": [],
        },
        "requirements": {
            "functional_requirements": list(WORKFLOW_RESOLVED),
            "open_questions": [WORKFLOW_BROAD, *WORKFLOW_PRESERVED],
            "clarified_decisions": [
                *[
                    {
                        "question": WORKFLOW_BROAD,
                        "decision": text,
                        "status": "RESOLVED",
                        "source": "customer clarification",
                    }
                    for text in WORKFLOW_RESOLVED
                ],
                {
                    "question": WORKFLOW_BROAD,
                    "decision": WORKFLOW_PENDING,
                    "status": "PENDING",
                    "source": "customer clarification",
                },
            ],
        },
        "validation": {
            "status": "READY",
            "reasons": ["Ready for preliminary shaping."],
            "questions": [],
            "non_blocking_questions": [WORKFLOW_BROAD, *WORKFLOW_PRESERVED],
        },
        "workflow_status": "COMPLETE",
        "delivery_review": {"status": "READY", "blocking_issues": []},
    }


def _question_lists(payload: dict) -> dict[str, list[str]]:
    root = [
        item["question"] if isinstance(item, dict) else str(item)
        for item in payload.get("non_blocking_questions") or []
    ]
    return {
        "unknowns": list((payload.get("discovery") or {}).get("unknowns") or []),
        "open_questions": list((payload.get("requirements") or {}).get("open_questions") or []),
        "validation": list(
            (payload.get("validation") or {}).get("non_blocking_questions") or []
        ),
        "root": root,
        "uncertain": [
            item
            for item in (payload.get("assessment") or {}).get("what_is_uncertain") or []
            if item in ((payload.get("requirements") or {}).get("open_questions") or [])
        ],
    }


def _assert_offline_narrowed(questions: list[str]) -> None:
    blob = _blob(questions)
    assert WORKFLOW_BROAD not in questions, questions
    assert "exact offline behavior" not in blob
    assert "synchronization rules" not in blob
    conflict = _conflict_items(questions)
    assert len(conflict) == 1, questions
    assert "workflow" in conflict[0].lower() or "resolv" in conflict[0].lower()
    assert "last-write" not in blob
    assert "wins" not in blob
    for preserved in WORKFLOW_PRESERVED:
        assert preserved in questions, (preserved, questions)


def test_workflow_response_narrows_broad_offline_to_conflict_remainder():
    original_history = [dict(item) for item in WORKFLOW_HISTORY]
    incoming = _workflow_state()
    payload = workflow_response(incoming, run_id="offline-conflict-workflow")
    lists = _question_lists(payload)
    assert lists["unknowns"] == lists["open_questions"] == lists["validation"] == lists["root"]
    _assert_offline_narrowed(lists["open_questions"])
    assert lists["uncertain"] == [
        item for item in lists["open_questions"] if item in lists["uncertain"]
    ]
    for item in lists["uncertain"]:
        assert "exact offline behavior" not in item.lower()
    functional = " ".join(
        (payload.get("requirements") or {}).get("functional_requirements") or []
    ).lower()
    for fragment in (
        "previously synchronized jobs",
        "queued for synchronization",
        "detected rather than silently overwriting",
    ):
        assert fragment in functional
    assert "last-write-wins" not in functional
    pending = [
        item
        for item in (payload.get("requirements") or {}).get("clarified_decisions") or []
        if str(item.get("status") or "").upper() == "PENDING"
    ]
    assert any("conflict" in str(item.get("decision") or "").lower() for item in pending)
    assert not any(
        "approved" in str(item.get("decision") or "").lower()
        and "conflict" in str(item.get("decision") or "").lower()
        and "status" in str(item).lower()
        and str(item.get("status")).upper() == "RESOLVED"
        for item in (payload.get("requirements") or {}).get("clarified_decisions") or []
    )
    assert payload["user_request"] == WORKFLOW_REQUEST
    assert payload["clarification_history"] == original_history
    assert incoming["user_request"] == WORKFLOW_REQUEST
    assert incoming["clarification_history"] == original_history


def test_workflow_response_second_pass_does_not_restore_broad_offline():
    original_history = [dict(item) for item in WORKFLOW_HISTORY]
    first = workflow_response(_workflow_state(), run_id="offline-conflict-pass-1")
    second = workflow_response(
        {
            "user_request": WORKFLOW_REQUEST,
            "clarification_history": original_history,
            "discovery": first["discovery"],
            "requirements": first["requirements"],
            "validation": first["validation"],
            "workflow_status": "COMPLETE",
            "delivery_review": {"status": "READY", "blocking_issues": []},
        },
        run_id="offline-conflict-pass-2",
    )
    first_lists = _question_lists(first)
    second_lists = _question_lists(second)
    assert first_lists["open_questions"] == second_lists["open_questions"]
    assert second_lists["unknowns"] == second_lists["open_questions"] == second_lists["validation"] == second_lists["root"]
    _assert_offline_narrowed(second_lists["open_questions"])
    assert second["user_request"] == WORKFLOW_REQUEST
    assert second["clarification_history"] == original_history
