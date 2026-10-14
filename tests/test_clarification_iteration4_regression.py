"""Iteration-4 clarification ledger is authoritative over stale open lists.

The Render payload had a RESOLVED canonical question, an ACCEPTED answer, and
a PENDING remainder decision, while discovery/requirements/validation still
listed the original (malformed) question as OPEN. No live model call.
"""

from app.api import workflow_response
from app.decisions import (
    ClarificationDecisions,
    _as_open_question,
    apply_reconciled_project_state,
    build_clarification_state,
    question_text,
    reconcile_open_questions,
    unanswered_request_items,
)

MALFORMED_OFFLINE = "What are the but the exact offline behavior?"
VOLUME_QUESTION = (
    "What is the expected user volume and concurrent load for the web application?"
)
PERMISSION_QUESTION = (
    "What are the detailed permission boundaries for each user role?"
)
OFFLINE_ANSWER = (
    "Technicians can access previously synchronized jobs and installation "
    "details offline. They can complete inspection checklists, capture defects, "
    "attach photos and notes, submit reports, and create follow-up actions "
    "while offline. Changes are persisted locally and queued for synchronization. "
    "Synchronization states must be visible. Retries must not silently lose or "
    "duplicate data. Conflicts must be detected rather than silently overwriting "
    "changes. The exact user workflow for resolving conflicts, including the "
    "handling of changes made to the same record by multiple users, still needs "
    "to be defined."
)
RESOLVED_DECISIONS = (
    "Technicians can access previously synchronized jobs and installation details offline.",
    "They can complete inspection checklists, capture defects, attach photos "
    "and notes, submit reports, and create follow-up actions while offline.",
    "Changes are persisted locally and queued for synchronization.",
    "Synchronization states must be visible.",
    "Retries must not silently lose or duplicate data.",
    "Conflicts must be detected rather than silently overwriting changes.",
)
PENDING_DECISION = (
    "The exact user workflow for resolving conflicts, including the handling "
    "of changes made to the same record by multiple users, still needs to be "
    "defined."
)
REQUEST = (
    "Build a mobile inspection app for field technicians. The application is "
    "expected to support field work in these conditions, but the exact offline "
    "behavior and synchronization rules have not yet been defined. User volume "
    "and detailed permission boundaries also need clarification."
)
OFFLINE_FR = list(RESOLVED_DECISIONS)
OFFLINE_AC = [
    f"Verified by demonstration or test that: {item}" for item in RESOLVED_DECISIONS[:3]
]
OFFLINE_CAPABILITIES = [
    "Technicians can access previously synchronized jobs and installation details offline.",
    "Changes are persisted locally and queued for synchronization.",
    "Conflicts must be detected rather than silently overwriting changes.",
]


def _ledger(questions: list[dict], *, question_status: str = "RESOLVED") -> dict:
    return {
        "version": 1,
        "answers": [
            {
                "question": MALFORMED_OFFLINE,
                "answer": OFFLINE_ANSWER,
                "status": "ACCEPTED",
                "source": "customer clarification",
            }
        ],
        "decisions": [
            *[
                {
                    "question": MALFORMED_OFFLINE,
                    "decision": text,
                    "status": "RESOLVED",
                    "source": "customer clarification",
                }
                for text in RESOLVED_DECISIONS
            ],
            {
                "question": MALFORMED_OFFLINE,
                "decision": PENDING_DECISION,
                "status": "PENDING",
                "source": "customer clarification",
            },
        ],
        "questions": [
            {
                "question": MALFORMED_OFFLINE,
                "status": question_status,
                "priority": "RECOMMENDED",
                "blocks_workflow": False,
                "reason": "",
            },
            *questions,
        ],
    }


def _iteration4_state(*, include_stale_open: bool = True) -> dict:
    stale = [MALFORMED_OFFLINE, VOLUME_QUESTION, PERMISSION_QUESTION]
    open_items = stale if include_stale_open else [VOLUME_QUESTION, PERMISSION_QUESTION]
    remaining = [
        {
            "question": VOLUME_QUESTION,
            "status": "OPEN",
            "priority": "RECOMMENDED",
            "blocks_workflow": False,
            "reason": "",
        },
        {
            "question": PERMISSION_QUESTION,
            "status": "OPEN",
            "priority": "RECOMMENDED",
            "blocks_workflow": False,
            "reason": "",
        },
    ]
    return {
        "user_request": REQUEST,
        "clarification_history": [
            {"question": MALFORMED_OFFLINE, "answer": OFFLINE_ANSWER}
        ],
        "clarification_state": _ledger(remaining),
        "discovery": {
            "problem": "Field inspection mobile app",
            "users": ["Field technicians"],
            "stakeholders": [],
            "unknowns": list(open_items),
            "clarification_questions": [],
        },
        "requirements": {
            "functional_requirements": list(OFFLINE_FR),
            "acceptance_criteria": list(OFFLINE_AC),
            "open_questions": list(open_items),
            "clarified_decisions": _ledger(remaining)["decisions"],
        },
        "validation": {
            "status": "READY",
            "reasons": ["Ready for preliminary shaping."],
            "questions": [],
            "non_blocking_questions": list(open_items),
        },
        "solution": {
            "overview": "Field inspection mobile app",
            "capabilities": list(OFFLINE_CAPABILITIES),
        },
        "workflow_status": "COMPLETE",
        "delivery_review": {"status": "READY", "blocking_issues": []},
        "non_blocking_questions": [
            {"question": item, "status": "OPEN", "priority": "RECOMMENDED"}
            for item in open_items
        ],
    }


def _texts(items) -> list[str]:
    return [question_text(item) for item in items or [] if question_text(item)]


def _question_lists(payload: dict) -> dict[str, list[str]]:
    return {
        "unknowns": _texts((payload.get("discovery") or {}).get("unknowns")),
        "open_questions": _texts((payload.get("requirements") or {}).get("open_questions")),
        "validation": _texts(
            (payload.get("validation") or {}).get("non_blocking_questions")
        ),
        "root": _texts(payload.get("non_blocking_questions")),
        "uncertain": _texts(
            (payload.get("assessment") or {}).get("what_is_uncertain") or []
        ),
    }


def _assert_consistent_open_lists(payload: dict) -> list[str]:
    lists = _question_lists(payload)
    canonical = lists["open_questions"]
    assert lists["unknowns"] == canonical
    assert lists["validation"] == canonical
    assert lists["root"] == canonical
    return canonical


def test_malformed_but_clause_is_not_generated():
    generated = _as_open_question("but the exact offline behavior")
    assert generated
    assert "but the" not in generated.lower()
    items = unanswered_request_items(
        {
            "user_request": REQUEST,
            "clarification_history": [],
        }
    )
    blob = " ".join(items).lower()
    assert "what are the but" not in blob
    assert "the but the" not in blob


def test_pending_remainder_does_not_reopen_resolved_original():
    state = _iteration4_state()
    decisions = ClarificationDecisions(state)
    assert decisions.resolves(MALFORMED_OFFLINE)
    assert decisions.is_pending(MALFORMED_OFFLINE)
    remainders = decisions.remainder_questions()
    assert remainders
    assert MALFORMED_OFFLINE not in remainders
    assert any("conflict" in item.lower() for item in remainders)
    for remainder in remainders:
        assert not decisions.resolves(remainder)


def test_all_pending_answer_keeps_question_open():
    question = PERMISSION_QUESTION
    pending_body = (
        "The exact permission matrix and detailed permission boundaries have "
        "not yet been defined."
    )
    state = {
        "user_request": (
            "Build a mobile inspection app. Detailed permission boundaries "
            "have not yet been defined."
        ),
        "clarification_history": [{"question": question, "answer": pending_body}],
        "clarification_state": {
            "version": 1,
            "answers": [
                {
                    "question": question,
                    "answer": pending_body,
                    "status": "ACCEPTED",
                    "source": "customer clarification",
                }
            ],
            "decisions": [
                {
                    "question": question,
                    "decision": pending_body,
                    "status": "PENDING",
                    "source": "customer clarification",
                }
            ],
            "questions": [
                {
                    "question": question,
                    "status": "OPEN",
                    "priority": "RECOMMENDED",
                    "blocks_workflow": False,
                    "reason": "",
                }
            ],
        },
        "discovery": {"unknowns": [question], "users": [], "stakeholders": []},
        "requirements": {"open_questions": [question]},
        "validation": {
            "status": "READY",
            "questions": [],
            "non_blocking_questions": [question],
        },
        "workflow_status": "COMPLETE",
        "delivery_review": {"status": "READY", "blocking_issues": []},
    }
    decisions = ClarificationDecisions(state)
    assert not decisions.resolves(question)
    assert decisions.is_pending(question)
    payload = workflow_response(state, run_id="iteration4-all-pending")
    open_lists = _assert_consistent_open_lists(payload)
    assert any(
        question_text(item) == question or "permission" in question_text(item).lower()
        for item in open_lists
    )
    ledger_questions = (payload.get("clarification_state") or {}).get("questions") or []
    statuses = {
        question_text(item): str(item.get("status") or "").upper()
        for item in ledger_questions
        if isinstance(item, dict)
    }
    assert "RESOLVED" not in {
        status
        for text, status in statuses.items()
        if "permission" in text.lower()
    }


def test_ledger_resolved_question_is_dropped_from_stale_open_lists():
    incoming = _iteration4_state(include_stale_open=True)
    extras = [
        {"question": MALFORMED_OFFLINE, "status": "OPEN"},
        VOLUME_QUESTION,
        PERMISSION_QUESTION,
    ]
    reconciled = reconcile_open_questions(extras, incoming)
    texts = _texts(reconciled)
    blob = " ".join(texts).lower()
    assert MALFORMED_OFFLINE not in texts
    assert "what are the but" not in blob
    assert VOLUME_QUESTION in texts
    assert PERMISSION_QUESTION in texts
    assert any("conflict" in item.lower() for item in texts)


def test_iteration4_workflow_lists_match_canonical_ledger():
    original_request = REQUEST
    original_history = [{"question": MALFORMED_OFFLINE, "answer": OFFLINE_ANSWER}]
    incoming = _iteration4_state()
    payload = workflow_response(incoming, run_id="iteration4-ledger")
    open_lists = _assert_consistent_open_lists(payload)
    blob = " ".join(open_lists).lower()
    assert MALFORMED_OFFLINE not in open_lists
    assert "what are the but" not in blob
    assert "the but the" not in blob
    assert VOLUME_QUESTION in open_lists
    assert PERMISSION_QUESTION in open_lists
    assert any("conflict" in item.lower() for item in open_lists)
    uncertain = " ".join(_question_lists(payload)["uncertain"]).lower()
    assert "what are the but" not in uncertain

    ledger = payload.get("clarification_state") or {}
    question_status = {
        question_text(item): str(item.get("status") or "").upper()
        for item in ledger.get("questions") or []
        if isinstance(item, dict)
    }
    assert question_status.get(MALFORMED_OFFLINE) == "RESOLVED"
    answers = ledger.get("answers") or []
    assert any(
        str(item.get("status") or "").upper() == "ACCEPTED"
        and question_text(item) == MALFORMED_OFFLINE
        for item in answers
        if isinstance(item, dict)
    )
    pending = [
        item
        for item in ledger.get("decisions") or []
        if isinstance(item, dict) and str(item.get("status") or "").upper() == "PENDING"
    ]
    assert len(pending) == 1
    assert "conflict" in str(pending[0].get("decision") or "").lower()

    functional = " ".join(
        (payload.get("requirements") or {}).get("functional_requirements") or []
    ).lower()
    acceptance = " ".join(
        (payload.get("requirements") or {}).get("acceptance_criteria") or []
    ).lower()
    capabilities = " ".join(
        ((payload.get("solution") or {}).get("capabilities") or [])
    ).lower()
    for fragment in (
        "previously synchronized jobs",
        "queued for synchronization",
        "detected rather than silently overwriting",
    ):
        assert fragment in functional
        assert fragment in capabilities or fragment in functional
    assert "offline" in acceptance or "queued for synchronization" in acceptance
    assert payload["user_request"] == original_request
    assert payload["clarification_history"] == original_history


def test_second_pass_does_not_reintroduce_resolved_offline_question():
    first = workflow_response(_iteration4_state(), run_id="iteration4-pass-1")
    second = workflow_response(
        {
            "user_request": REQUEST,
            "clarification_history": [
                {"question": MALFORMED_OFFLINE, "answer": OFFLINE_ANSWER}
            ],
            "clarification_state": first["clarification_state"],
            "discovery": first["discovery"],
            "requirements": first["requirements"],
            "validation": first["validation"],
            "solution": first["solution"],
            "workflow_status": "COMPLETE",
            "delivery_review": {"status": "READY", "blocking_issues": []},
            "non_blocking_questions": first["non_blocking_questions"],
        },
        run_id="iteration4-pass-2",
    )
    first_lists = _assert_consistent_open_lists(first)
    second_lists = _assert_consistent_open_lists(second)
    assert first_lists == second_lists
    assert MALFORMED_OFFLINE not in second_lists
    assert VOLUME_QUESTION in second_lists
    assert PERMISSION_QUESTION in second_lists


def test_sibling_remainders_from_one_original_stay_separate():
    original = "Who will use the first release, and what will they do in it?"
    interface = (
        "Has the Operations Manager dedicated first-release interface been decided?"
    )
    permissions = (
        "Have the exact permission matrix and report-correction workflow been defined?"
    )
    state = {
        "user_request": "Build a mobile inspection first release.",
        "clarification_history": [
            {
                "question": original,
                "answer": (
                    "Field technicians are the primary users of the mobile app. "
                    "Whether the Operations Manager needs a dedicated "
                    "first-release interface has not been decided. Field "
                    "Technician and Operations Manager roles are identified, "
                    "but the exact permission matrix and report-correction "
                    "workflow are not yet defined."
                ),
            }
        ],
        "clarification_state": {
            "version": 1,
            "answers": [
                {
                    "question": original,
                    "answer": (
                        "Field technicians are the primary users of the mobile app. "
                        "Whether the Operations Manager needs a dedicated "
                        "first-release interface has not been decided. Field "
                        "Technician and Operations Manager roles are identified, "
                        "but the exact permission matrix and report-correction "
                        "workflow are not yet defined."
                    ),
                    "status": "ACCEPTED",
                }
            ],
            "questions": [
                {
                    "question": original,
                    "status": "RESOLVED",
                    "priority": "REQUIRED",
                    "blocks_workflow": True,
                }
            ],
        },
    }
    texts = _texts(
        reconcile_open_questions([original, interface, permissions], state)
    )
    blob = " ".join(texts).lower()
    assert original not in texts
    assert "who will use the first release" not in blob
    assert "operations manager" in blob
    assert "permission matrix" in blob


def test_apply_reconciled_state_does_not_reopen_ledger_resolved_question():
    state = _iteration4_state()
    updates = apply_reconciled_project_state(state)
    texts = _texts((updates.get("requirements") or {}).get("open_questions"))
    assert MALFORMED_OFFLINE not in texts
    assert VOLUME_QUESTION in texts
    assert PERMISSION_QUESTION in texts
    rebuilt = build_clarification_state(
        {**state, **updates},
        non_blocking_questions=texts,
    )
    statuses = {
        question_text(item): str(item.get("status") or "").upper()
        for item in rebuilt.get("questions") or []
        if isinstance(item, dict)
    }
    assert statuses.get(MALFORMED_OFFLINE) == "RESOLVED"
