"""Answered optional questions stay open once, without a reworded copy.

The sentences are the regression scenario. The matching rules are generic:
answer text is a fact, an unapproved proposal stays unapproved, and a new
wording is not a new question when it asks for the same open decision.
"""

from app.agents import validation_agent
from app.decisions import (
    ClarificationDecisions,
    active_open_questions,
    apply_decisions_to_requirements,
    apply_optional_classifications,
    build_clarification_state,
    classify_optional_questions,
)
from app.providers import AIProvider


CANCELLATION = "What are the cancellation and proration rules?"
LOAD = "What customer volumes and peak transaction loads should the system support?"
ROLES = "What is the user-role and permission matrix?"
MIGRATION = "What is the initial migration scope?"
CRM = "Is CRM API documentation and sandbox access available?"

HISTORY = [
    {
        "question": CANCELLATION,
        "answer": (
            "Cancellation and proration rules are not approved and require "
            "stakeholder agreement."
        ),
    },
    {
        "question": LOAD,
        "answer": (
            "Proposed customer volumes and peak transaction loads are "
            "provisional assumptions that require validation."
        ),
    },
    {
        "question": ROLES,
        "answer": "The proposed user-role and permission matrix requires approval.",
    },
    {
        "question": MIGRATION,
        "answer": (
            "The initial migration scope is defined, but historical record "
            "volumes, retention requirements, and inclusion of inactive or "
            "closed accounts remain unconfirmed."
        ),
    },
    {
        "question": CRM,
        "answer": (
            "CRM API documentation is available, but sandbox access and "
            "credentials have not been confirmed."
        ),
    },
]

REPHRASED = [
    "Have the cancellation and proration rules been approved?",
    "Have the proposed customer volumes and peak transaction loads been approved?",
    "Has the proposed user-role and permission matrix been approved?",
    "What is the initial migration scope?",
    "Is CRM API documentation available?",
    "Has the proposed 10000 peak transactions per second been approved?",
    "What billing retry policy applies after a failed payment?",
]


def _state(extra=None):
    state = {"user_request": "Build an operations portal.", "clarification_history": HISTORY}
    if extra:
        state.update(extra)
    return state


def _open(state, proposed=None):
    return active_open_questions(state, proposed or [])


def test_answered_approval_questions_do_not_reappear():
    first = _open(_state(), [CANCELLATION, LOAD, ROLES, MIGRATION, CRM])
    assert CANCELLATION in first
    assert LOAD in first
    assert ROLES in first

    second = _open(_state(), REPHRASED)
    blob = " ".join(second).lower()
    assert CANCELLATION in second
    assert LOAD in second
    assert ROLES in second
    assert "been approved" not in blob.split("10000")[0]
    assert not any(item.lower().startswith("have the cancellation") for item in second)
    assert not any("volumes and peak transaction loads been approved" in item.lower() for item in second)
    assert not any("permission matrix been approved" in item.lower() for item in second)
    assert any("10000" in item for item in second)
    assert any("billing retry" in item.lower() for item in second)


def test_unapproved_decision_stays_pending_and_is_not_a_requirement():
    decisions = ClarificationDecisions(_state())
    pending = " ".join(item.text for item in decisions.pending).lower()
    resolved = " ".join(item.text for item in decisions.resolved).lower()
    assert "not approved" in pending
    assert "provisional" in pending
    assert "requires approval" in pending
    assert "not approved" not in resolved
    requirements = apply_decisions_to_requirements(
        {"functional_requirements": [], "acceptance_criteria": [], "open_questions": []},
        _state(),
    )
    functional = " ".join(requirements.get("functional_requirements") or []).lower()
    assert "not approved" not in functional
    assert "provisional assumptions" not in functional


def test_migration_and_crm_keep_only_the_unconfirmed_aspects():
    opened = _open(_state(), REPHRASED)
    blob = " ".join(opened).lower()
    assert MIGRATION not in opened
    assert "initial migration scope is defined" not in blob
    assert "historical record volumes" in blob
    assert "retention" in blob
    assert "inactive" in blob or "closed accounts" in blob
    assert CRM not in opened
    assert "documentation" not in blob
    assert "sandbox" in blob and "credentials" in blob


def test_restored_ledger_does_not_regrow_rephrased_questions():
    state = _state()
    opened = _open(state, REPHRASED)
    ledger = build_clarification_state(
        state,
        blocking_questions=[],
        non_blocking_questions=opened,
    )
    pending = [
        item["decision"]
        for item in ledger["decisions"]
        if item["status"] == "PENDING"
    ]
    assert any("not approved" in item.lower() for item in pending)
    open_questions = [item for item in ledger["questions"] if item["status"] == "OPEN"]
    assert any(item["question"] == CANCELLATION and "not approved" in item["reason"].lower() for item in open_questions)

    restored = _state({"clarification_state": ledger})
    again = _open(restored, REPHRASED)
    assert again == opened


def test_validation_regeneration_uses_the_same_open_questions():
    state = _state(
        {
            "discovery": {
                "problem": "Operations portal",
                "business_goal": "Manage accounts",
                "users": ["Operators"],
                "stakeholders": [],
                "existing_systems": [],
                "constraints": [],
                "assumptions": [],
                "unknowns": list(REPHRASED),
                "clarification_questions": [],
            },
            "requirements": {
                "functional_requirements": ["Operators manage accounts."],
                "non_functional_requirements": [],
                "acceptance_criteria": ["An operator can manage an account."],
                "open_questions": list(REPHRASED),
                "contradictions": [],
            },
        }
    )

    class _ValidationOnly(AIProvider):
        def generate_json(self, prompt, schema):
            if "classify optional clarification questions" in prompt.lower():
                return {"classifications": []}
            return {
                "status": "READY",
                "reasons": ["Ready for preliminary shaping."],
                "questions": [],
                "non_blocking_questions": list(REPHRASED),
            }

    result = validation_agent(state, _ValidationOnly())
    opened = result["validation"]["non_blocking_questions"]
    assert CANCELLATION in opened
    assert not any("cancellation and proration rules been approved" in item.lower() for item in opened)
    assert any("historical record volumes" in item.lower() for item in opened)
    assert any("sandbox" in item.lower() for item in opened)


def test_llm_classification_cites_history_and_cannot_approve_an_open_decision():
    class _Classifier(AIProvider):
        def generate_json(self, prompt, schema):
            assert "Cancellation and proration rules are not approved" in prompt
            assert CANCELLATION in prompt
            return {
                "classifications": [
                    {
                        "question": "Have the cancellation and proration rules been approved?",
                        "status": "UNRESOLVED",
                        "rationale": "The customer already said the rules are not approved.",
                        "source_question": CANCELLATION,
                        "source_answer": HISTORY[0]["answer"],
                    },
                    {
                        "question": CANCELLATION,
                        "status": "RESOLVED",
                        "rationale": "Incorrectly treats a pending decision as closed.",
                        "source_question": CANCELLATION,
                        "source_answer": HISTORY[0]["answer"],
                    },
                    {
                        "question": "Which invoice layout should the first release use?",
                        "status": "NEW",
                        "rationale": "No earlier answer discusses invoice layout.",
                        "source_question": "",
                        "source_answer": "",
                    },
                ]
            }

    rows = classify_optional_questions(
        _Classifier(),
        [
            "Have the cancellation and proration rules been approved?",
            CANCELLATION,
            "Which invoice layout should the first release use?",
        ],
        _state(),
    )
    assert [row["status"] for row in rows] == ["UNRESOLVED", "RESOLVED", "NEW"]
    assert rows[0]["source_question"] == CANCELLATION
    kept = apply_optional_classifications(
        [
            "Have the cancellation and proration rules been approved?",
            CANCELLATION,
            "Which invoice layout should the first release use?",
        ],
        rows,
        _state(),
    )
    assert "Have the cancellation and proration rules been approved?" not in kept
    assert CANCELLATION in kept
    assert "Which invoice layout should the first release use?" in kept
