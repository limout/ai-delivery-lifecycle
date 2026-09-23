"""Regression tests for deterministic evidence gaps and optional clarification UX."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.agents import _answered_clarification_topics
from app.api import get_provider
from app.evidence import (
    FIRST_RELEASE_SCOPE_QUESTION,
    has_first_release_scope,
    has_named_integration,
    has_substantive_first_release_scope_answer,
    material_evidence_gaps,
    needs_compliance_clarity,
    needs_integration_clarity,
)
from app.main import app
from app.providers import MockProvider
from app.resume import answers_require_upstream_regen
from tests.test_phase0 import COMPLETE_REQUEST


app.dependency_overrides[get_provider] = MockProvider
client = TestClient(app)
INDEX = Path("app/static/index.html").read_text(encoding="utf-8")

CRITICAL_EXAMPLE = """
We need to build a customer self-service web application.
The customer wants the first release in 2 months.
The system must integrate with an existing ERP and payment provider.
The customer has not provided detailed requirements yet.
What should we do and can we realistically commit to the deadline?
""".strip()

SCOPE_QUESTION = FIRST_RELEASE_SCOPE_QUESTION
SYSTEMS_QUESTION = (
    "Which systems must the first release integrate with, and what "
    "is the source of truth?"
)


def _codes(state) -> set[str]:
    return {gap.code for gap in material_evidence_gaps(state)}


def _question_text(items) -> str:
    parts = []
    for item in items or []:
        if isinstance(item, dict):
            parts.append(str(item.get("question") or ""))
        else:
            parts.append(str(item))
    return " ".join(parts).lower()


def test_undefined_mvp_scope_is_blocking():
    codes = _codes({"user_request": CRITICAL_EXAMPLE})
    assert "first_release_scope" in codes
    assert has_first_release_scope(CRITICAL_EXAMPLE) is False


def test_unnamed_required_integration_is_blocking():
    assert needs_integration_clarity(CRITICAL_EXAMPLE) is True
    assert has_named_integration(CRITICAL_EXAMPLE) is False
    codes = _codes({"user_request": CRITICAL_EXAMPLE})
    assert "integrations" in codes


def test_generic_unknown_security_is_not_automatically_blocking():
    request = COMPLETE_REQUEST + "\nSecurity requirements are not yet defined."
    assert needs_compliance_clarity(request) is False
    assert "compliance" not in _codes({"user_request": request})
    data = client.post("/analyze", json={"user_request": request}).json()
    blocking = _question_text(data.get("blocking_questions"))
    assert "mandatory security or regulatory" not in blocking


def test_optional_user_volume_question_is_non_blocking():
    data = client.post("/analyze", json={"user_request": COMPLETE_REQUEST}).json()
    assert data["status"] == "COMPLETE"
    assert not data.get("blocking_questions")
    non_blocking = _question_text(data.get("non_blocking_questions"))
    assert "volume" in non_blocking or "roles" in non_blocking


def test_complete_run_frontend_displays_optional_questions():
    assert "Clarification questions" in INDEX
    assert "Recommended questions" not in INDEX.split("else if (laterQuestions.length > 0)", 1)[1].split("function statusClassFor", 1)[0]
    optional_branch = INDEX.split("} else if (laterQuestions.length > 0)", 1)[1]
    assert "These questions do not block the current assessment. Answer any subset to refine the analysis and run another iteration." in optional_branch
    assert "Answer questions" in optional_branch
    assert 'optionalForm.classList.add("hidden")' in optional_branch
    assert "toggleOptionalQuestions" in INDEX
    assert "Hide questions" in INDEX
    assert "Refine analysis" in optional_branch
    assert "/clarify/stream" in INDEX
    data = client.post("/analyze", json={"user_request": COMPLETE_REQUEST}).json()
    assert data["status"] == "COMPLETE"
    assert data.get("non_blocking_questions")


def test_complete_optional_questions_toggle_labels():
    optional_branch = INDEX.split("} else if (laterQuestions.length > 0)", 1)[1]
    blocking_branch = INDEX.split("if (needsInfo && blockingQuestions.length > 0)", 1)[1].split(
        "} else if (laterQuestions.length > 0)", 1
    )[0]
    assert 'optionalToggle.textContent = "Answer questions"' in optional_branch
    assert 'optionalForm.classList.add("hidden")' in optional_branch
    assert "toggleOptionalQuestions" in INDEX
    toggle_fn = INDEX.split("function toggleOptionalQuestions()", 1)[1].split(
        "function buildQuestionGroup", 1
    )[0]
    assert 'toggle.textContent = "Hide questions"' in toggle_fn
    assert 'toggle.textContent = "Answer questions"' in toggle_fn
    assert 'optionalToggle.classList.add("hidden")' in blocking_branch
    assert 'optionalForm.classList.remove("hidden")' in blocking_branch


def test_clarification_questions_use_shared_containers():
    assert "function buildQuestionGroup" in INDEX
    assert "buildQuestionGroup(blockingQuestions, true" in INDEX
    assert "buildQuestionGroup(laterQuestions, false" in INDEX
    group_fn = INDEX.split("function buildQuestionGroup", 1)[1].split(
        "function buildQuestionCard", 1
    )[0]
    assert 'label.textContent = required ? "Required" : "Optional"' in group_fn
    card_fn = INDEX.split("function buildQuestionCard", 1)[1].split(
        "function renderVerdict", 1
    )[0]
    assert "Useful later" not in card_fn
    assert "question-priority" not in card_fn
    assert "question-item question-card" in card_fn
    assert ".question-group" in INDEX


def test_optional_answers_still_submit_via_existing_clarify():
    assert "async function clarify()" in INDEX
    clarify_fn = INDEX.split("async function clarify()", 1)[1].split(
        "document.addEventListener", 1
    )[0]
    assert "/clarify/stream" in clarify_fn
    assert "clarification_answers" in clarify_fn
    assert "iteration: currentIteration" in clarify_fn
    assert "id=\"clarifyButton\"" in INDEX
    assert "id=\"optionalQuestionsForm\"" in INDEX


def test_optional_answers_trigger_another_iteration():
    first = client.post("/analyze", json={"user_request": COMPLETE_REQUEST}).json()
    assert first["status"] == "COMPLETE"
    question = "What are the expected user roles/permissions and expected user volume?"
    items = first.get("non_blocking_questions") or []
    if items:
        first_q = items[0]
        question = first_q["question"] if isinstance(first_q, dict) else str(first_q)
    second = client.post(
        "/clarify",
        json={
            "user_request": COMPLETE_REQUEST,
            "answers": [
                {
                    "question": question,
                    "answer": "About 200 enterprise users with admin and requester roles.",
                }
            ],
            "iteration": first["iteration"],
            "run_id": first["run_id"],
            "prior_state": first,
            "clarification_history": first.get("clarification_history") or [],
        },
    ).json()
    assert second["iteration"] == first["iteration"] + 1
    assert second.get("clarification_history")
    assert second["status"] in {"COMPLETE", "NEEDS_INFO", "BLOCKED"}


def test_critical_example_stops_then_clarify_resumes():
    first = client.post("/analyze", json={"user_request": CRITICAL_EXAMPLE}).json()
    assert first["status"] == "NEEDS_INFO"
    assert first.get("awaiting_customer") is True
    assert first.get("estimate") in (None, {})
    blocking = _question_text(first.get("blocking_questions"))
    assert "first production release" in blocking
    assert "integrate" in blocking
    assert first["iteration"] == 1

    second = client.post(
        "/clarify",
        json={
            "user_request": CRITICAL_EXAMPLE,
            "answers": [
                {
                    "question": SCOPE_QUESTION,
                    "answer": (
                        "First release: customers can view invoices, submit payment "
                        "requests, and track status. Out of scope: mobile apps."
                    ),
                },
                {
                    "question": SYSTEMS_QUESTION,
                    "answer": (
                        "Integrate with SAP as the ERP source of truth and Stripe "
                        "as the payment provider."
                    ),
                },
            ],
            "iteration": first["iteration"],
            "run_id": first["run_id"],
            "prior_state": first,
            "clarification_history": first.get("clarification_history") or [],
        },
    )
    assert second.status_code == 200
    data = second.json()
    assert data["iteration"] == 2
    codes = _codes({
        "user_request": CRITICAL_EXAMPLE,
        "clarification_history": data.get("clarification_history") or [],
    })
    assert "first_release_scope" not in codes
    assert "integrations" not in codes


def test_blocking_clarify_flow_still_requires_answers():
    first = client.post(
        "/analyze",
        json={"user_request": "We want to build a customer self-service portal."},
    ).json()
    assert first["status"] == "NEEDS_INFO"
    assert first["blocking_questions"]
    empty = client.post(
        "/clarify",
        json={
            "user_request": "We want to build a customer self-service portal.",
            "answers": [],
            "iteration": first["iteration"],
        },
    )
    assert empty.status_code == 422
    second = client.post(
        "/clarify",
        json={
            "user_request": "We want to build a customer self-service portal.",
            "answers": [
                {
                    "question": SCOPE_QUESTION,
                    "answer": (
                        "Customers can view account information, submit service "
                        "requests, and track status."
                    ),
                }
            ],
            "iteration": first["iteration"],
            "run_id": first["run_id"],
            "prior_state": first,
            "clarification_history": first.get("clarification_history") or [],
        },
    )
    assert second.status_code == 200
    assert second.json()["iteration"] == first["iteration"] + 1


def _legacy_scope_state(answer: str) -> dict:
    payload = f"{SCOPE_QUESTION}: {answer}"
    return {
        "user_request": CRITICAL_EXAMPLE,
        "clarification_history": [
            {"question": "Customer clarification", "answer": payload},
        ],
        "clarification_answers": [payload],
        "new_clarification_records": [{"question": "", "answer": payload}],
        "discovery": {"problem": "portal"},
        "requirements": {"functional_requirements": []},
    }


SUBSTANTIVE_SCOPE_ANSWER = (
    "First release is an invoice list and payment-status page for logged-in "
    "customers. Mobile apps are out of scope."
)


def test_iteration_1_missing_scope_is_first_release_scope_blocker():
    first = client.post("/analyze", json={"user_request": CRITICAL_EXAMPLE}).json()
    assert first["status"] == "NEEDS_INFO"
    assert "first_release_scope" in _codes({"user_request": CRITICAL_EXAMPLE})
    assert SCOPE_QUESTION.lower() in _question_text(first.get("blocking_questions"))


def test_iteration_2_substantive_scope_answer_clears_scope_blocker():
    state = _legacy_scope_state(SUBSTANTIVE_SCOPE_ANSWER)
    assert has_substantive_first_release_scope_answer(state) is True
    assert "first_release_scope" not in _codes(state)
    assert "first_release_scope" in _answered_clarification_topics(state)

    first = client.post("/analyze", json={"user_request": CRITICAL_EXAMPLE}).json()
    second = client.post(
        "/clarify",
        json={
            "user_request": CRITICAL_EXAMPLE,
            "clarification_answers": [f"{SCOPE_QUESTION}: {SUBSTANTIVE_SCOPE_ANSWER}"],
            "iteration": first["iteration"],
            "run_id": first["run_id"],
            "prior_state": first,
            "clarification_history": first.get("clarification_history") or [],
        },
    ).json()
    assert second["iteration"] == first["iteration"] + 1
    assert SCOPE_QUESTION.lower() not in _question_text(second.get("blocking_questions"))
    assert "first_release_scope" not in _codes({
        "user_request": CRITICAL_EXAMPLE,
        "clarification_history": second.get("clarification_history") or [],
        "clarification_answers": [f"{SCOPE_QUESTION}: {SUBSTANTIVE_SCOPE_ANSWER}"],
    })


def test_iteration_2_tbd_scope_answer_keeps_scope_blocker():
    state = _legacy_scope_state("I don't know / TBD")
    assert has_substantive_first_release_scope_answer(state) is False
    assert "first_release_scope" in _codes(state)

    first = client.post("/analyze", json={"user_request": CRITICAL_EXAMPLE}).json()
    second = client.post(
        "/clarify",
        json={
            "user_request": CRITICAL_EXAMPLE,
            "clarification_answers": [f"{SCOPE_QUESTION}: I don't know / TBD"],
            "iteration": first["iteration"],
            "run_id": first["run_id"],
            "prior_state": first,
            "clarification_history": first.get("clarification_history") or [],
        },
    ).json()
    assert second["status"] == "NEEDS_INFO"
    assert SCOPE_QUESTION.lower() in _question_text(second.get("blocking_questions"))


def test_scope_answer_triggers_upstream_regeneration():
    state = {
        "discovery": {"problem": "portal"},
        "requirements": {"functional_requirements": []},
        "new_clarification_records": [
            {"question": "", "answer": f"{SCOPE_QUESTION}: {SUBSTANTIVE_SCOPE_ANSWER}"},
        ],
    }
    assert answers_require_upstream_regen(state) is True


def test_original_undefined_scope_wording_does_not_void_substantive_answer():
    assert "not provided detailed requirements" in CRITICAL_EXAMPLE.lower()
    state = _legacy_scope_state(SUBSTANTIVE_SCOPE_ANSWER)
    assert has_first_release_scope(CRITICAL_EXAMPLE) is False
    assert "first_release_scope" not in _codes(state)
