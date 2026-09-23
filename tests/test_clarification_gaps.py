"""Regression tests for deterministic evidence gaps and optional clarification UX."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.agents import (
    _answered_clarification_topics,
    _answered_question_texts,
    _normalize_question_text,
    _question_dedup_key,
    _question_topic,
    ROLES_FOLLOW_UP_QUESTION,
    VOLUME_FOLLOW_UP_QUESTION,
    validation_agent,
)
from app.api import get_provider, workflow_response
from app.evidence import (
    FIRST_RELEASE_SCOPE_QUESTION,
    has_first_release_scope,
    has_named_integration,
    has_substantive_first_release_scope_answer,
    is_non_substantive_clarification_answer,
    material_evidence_gaps,
    needs_compliance_clarity,
    needs_integration_clarity,
)
from app.main import app
from app.providers import AIProvider, MockProvider
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


def test_assessment_result_hierarchy():
    result = INDEX.split('id="result"', 1)[1]
    context_at = result.find("summary-card")
    verdict_at = result.find('id="verdict"')
    progress_at = result.find("lifecycle-card")
    questions_at = result.find('id="questions"')
    assert -1 not in (context_at, verdict_at, progress_at, questions_at)
    assert context_at < verdict_at < progress_at < questions_at
    assert 'id="summaryProblem"' in INDEX
    assert 'id="summaryGoal"' in INDEX
    assert 'id="summaryState"' not in INDEX
    assert "Workflow State" not in INDEX.split("summary-card", 1)[1].split("id=\"verdict\"", 1)[0]
    assert 'id="status"' in INDEX
    assert 'id="iteration"' in INDEX
    print_css = INDEX.split("@media print", 1)[1].split("@media", 1)[0]
    assert ".lifecycle-card" in print_css
    assert "#verdict" in print_css
    assert ".summary-card" not in print_css


def test_optional_answers_still_submit_via_existing_clarify():
    assert "async function clarify()" in INDEX
    clarify_fn = INDEX.split("async function clarify()", 1)[1].split(
        "document.addEventListener", 1
    )[0]
    assert "/clarify/stream" in clarify_fn
    assert "clarification_answers" in clarify_fn
    assert "iteration: currentIteration" in clarify_fn
    assert 'window.scrollTo({ top: 0, behavior: "smooth" })' in clarify_fn
    assert "requestAnimationFrame" in clarify_fn
    assert 'document.querySelector(".app-main")' in clarify_fn
    assert "main.scrollTo" in clarify_fn
    assert clarify_fn.index('showError("Please answer the required questions before continuing.")') < clarify_fn.index("scrollTo")
    assert clarify_fn.index('showError("Please answer at least one question.")') < clarify_fn.index("scrollTo")
    assert clarify_fn.index("updateRunningStatus") < clarify_fn.index("requestAnimationFrame")
    assert clarify_fn.index("requestAnimationFrame") < clarify_fn.index("consumeWorkflowStream")
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


API_ACCESS_QUESTION = (
    "Do we have existing API access and technical documentation for "
    "SAP S/4HANA and Stripe, or will sandbox environments need to be "
    "provisioned?"
)
API_ACCESS_ANSWER = "yes, we have access to API and documentation"
ROLES_VOLUME_QUESTION = (
    "What are the expected user roles/permissions and expected user volume?"
)
FOLLOW_UP_RATE_LIMITS = "What are the expected API rate limits?"
IMMEDIATE_ACCESS_QUESTION = (
    "Do we have immediate access to test environments and API documentation "
    "for SAP S/4HANA and Stripe?"
)
IMMEDIATE_ACCESS_ANSWER = (
    "yes, we have access to test environments and API documentation"
)
IMMEDIATE_ACCESS_BLOB = f"{IMMEDIATE_ACCESS_QUESTION}: {IMMEDIATE_ACCESS_ANSWER}"


class _ValidationScriptProvider(AIProvider):
    def __init__(self, non_blocking=None, questions=None):
        self.non_blocking = list(non_blocking or [])
        self.questions = list(questions or [])

    def generate_json(self, prompt: str, schema: dict) -> dict:
        return {
            "status": "READY",
            "reasons": [
                "The available information is sufficient for preliminary solution shaping."
            ],
            "questions": list(self.questions),
            "non_blocking_questions": list(self.non_blocking),
        }


def _validation_state(*, history=None, unknowns=None, open_questions=None, new_records=None):
    state = {
        "user_request": COMPLETE_REQUEST,
        "discovery": {
            "problem": "Enterprise customers need self-service",
            "business_goal": "Reduce support effort",
            "users": ["Enterprise customers"],
            "stakeholders": [],
            "existing_systems": ["Salesforce"],
            "constraints": ["Target delivery timeline: 2 months"],
            "assumptions": [],
            "unknowns": list(unknowns or []),
        },
        "requirements": {
            "functional_requirements": ["Submit service requests"],
            "non_functional_requirements": [],
            "acceptance_criteria": [],
            "open_questions": list(open_questions or []),
            "contradictions": [],
        },
        "clarification_history": list(history or []),
    }
    if new_records is not None:
        state["new_clarification_records"] = list(new_records)
    return state


def test_substantive_optional_answer_suppresses_exact_question():
    history = [{"question": API_ACCESS_QUESTION, "answer": API_ACCESS_ANSWER}]
    state = _validation_state(
        history=history,
        unknowns=[API_ACCESS_QUESTION],
        open_questions=[API_ACCESS_QUESTION],
    )
    result = validation_agent(
        state,
        _ValidationScriptProvider(non_blocking=[API_ACCESS_QUESTION]),
    )
    merged = {**state, **result}
    payload = workflow_response(merged)
    asked = _question_text(result["validation"]["non_blocking_questions"])
    assert API_ACCESS_QUESTION.lower() not in asked
    assert API_ACCESS_QUESTION.lower() not in _question_text(
        payload["non_blocking_questions"]
    )
    assert API_ACCESS_QUESTION.lower() not in _question_text(
        payload["assessment"]["ask_next"]
    )


def test_answered_unknown_is_not_remerged_into_non_blocking():
    history = [{"question": API_ACCESS_QUESTION, "answer": API_ACCESS_ANSWER}]
    state = _validation_state(history=history, unknowns=[API_ACCESS_QUESTION])
    result = validation_agent(state, _ValidationScriptProvider(non_blocking=[]))
    asked = _question_text(result["validation"]["non_blocking_questions"])
    assert API_ACCESS_QUESTION.lower() not in asked


def test_unanswered_optional_question_remains():
    state = _validation_state(unknowns=[API_ACCESS_QUESTION])
    result = validation_agent(
        state,
        _ValidationScriptProvider(non_blocking=[API_ACCESS_QUESTION]),
    )
    asked = _question_text(result["validation"]["non_blocking_questions"])
    assert API_ACCESS_QUESTION.lower() in asked


def test_non_substantive_optional_answer_does_not_suppress():
    for answer in ("TBD", "I don't know", "not decided"):
        assert is_non_substantive_clarification_answer(answer) is True
        state = _validation_state(
            history=[{"question": API_ACCESS_QUESTION, "answer": answer}],
            unknowns=[API_ACCESS_QUESTION],
        )
        result = validation_agent(
            state,
            _ValidationScriptProvider(non_blocking=[API_ACCESS_QUESTION]),
        )
        asked = _question_text(result["validation"]["non_blocking_questions"])
        assert API_ACCESS_QUESTION.lower() in asked, answer


def test_different_follow_up_question_remains():
    history = [{"question": "Do we have API access?", "answer": API_ACCESS_ANSWER}]
    state = _validation_state(
        history=history,
        unknowns=[FOLLOW_UP_RATE_LIMITS],
    )
    result = validation_agent(
        state,
        _ValidationScriptProvider(non_blocking=[FOLLOW_UP_RATE_LIMITS]),
    )
    asked = _question_text(result["validation"]["non_blocking_questions"])
    assert FOLLOW_UP_RATE_LIMITS.lower() in asked
    assert "do we have api access?" not in asked


def test_forced_roles_volume_question_suppressed_when_answered():
    history = [
        {
            "question": ROLES_VOLUME_QUESTION,
            "answer": "About 200 enterprise users with admin and requester roles.",
        }
    ]
    state = _validation_state(history=history)
    result = validation_agent(state, _ValidationScriptProvider(non_blocking=[]))
    asked = _question_text(result["validation"]["non_blocking_questions"])
    assert ROLES_VOLUME_QUESTION.lower() not in asked
    assert VOLUME_FOLLOW_UP_QUESTION.lower() not in asked
    assert ROLES_FOLLOW_UP_QUESTION.lower() not in asked


def test_answered_optional_question_does_not_return_after_clarify():
    class ReaskProvider(MockProvider):
        def generate_json(self, prompt: str, schema: dict) -> dict:
            payload = super().generate_json(prompt, schema)
            if "whether the project definition is" in (prompt or "").lower():
                payload = dict(payload)
                current = list(payload.get("non_blocking_questions") or [])
                if API_ACCESS_QUESTION not in current:
                    current.insert(0, API_ACCESS_QUESTION)
                payload["non_blocking_questions"] = current
            return payload

    app.dependency_overrides[get_provider] = ReaskProvider
    try:
        first = client.post("/analyze", json={"user_request": COMPLETE_REQUEST}).json()
        prior = dict(first)
        discovery = dict(prior.get("discovery") or {})
        discovery["unknowns"] = list(discovery.get("unknowns") or []) + [
            API_ACCESS_QUESTION
        ]
        prior["discovery"] = discovery
        second = client.post(
            "/clarify",
            json={
                "user_request": COMPLETE_REQUEST,
                "answers": [
                    {
                        "question": API_ACCESS_QUESTION,
                        "answer": API_ACCESS_ANSWER,
                    }
                ],
                "iteration": first["iteration"],
                "run_id": first["run_id"],
                "prior_state": prior,
                "clarification_history": first.get("clarification_history") or [],
            },
        )
        assert second.status_code == 200
        data = second.json()
        asked = _question_text(data.get("non_blocking_questions"))
        asked += " " + _question_text(
            (data.get("validation") or {}).get("non_blocking_questions")
        )
        asked += " " + _question_text((data.get("assessment") or {}).get("ask_next"))
        assert API_ACCESS_QUESTION.lower() not in asked
    finally:
        app.dependency_overrides[get_provider] = MockProvider


def test_legacy_ui_payload_suppresses_exact_optional_question():
    history = [{
        "question": "Customer clarification",
        "answer": IMMEDIATE_ACCESS_BLOB,
    }]
    state = _validation_state(
        history=history,
        new_records=[{"question": "", "answer": history[0]["answer"]}],
        unknowns=[IMMEDIATE_ACCESS_QUESTION],
    )
    answered = _answered_question_texts(state)
    assert _normalize_question_text(IMMEDIATE_ACCESS_QUESTION) in answered
    assert "customer clarification" not in answered
    result = validation_agent(
        state,
        _ValidationScriptProvider(non_blocking=[IMMEDIATE_ACCESS_QUESTION]),
    )
    asked = _question_text(result["validation"]["non_blocking_questions"])
    assert IMMEDIATE_ACCESS_QUESTION.lower() not in asked


def test_legacy_clarify_payload_without_structured_answers():
    class ReaskProvider(MockProvider):
        def generate_json(self, prompt: str, schema: dict) -> dict:
            payload = super().generate_json(prompt, schema)
            if "whether the project definition is" in (prompt or "").lower():
                payload = dict(payload)
                current = list(payload.get("non_blocking_questions") or [])
                if IMMEDIATE_ACCESS_QUESTION not in current:
                    current.insert(0, IMMEDIATE_ACCESS_QUESTION)
                payload["non_blocking_questions"] = current
            return payload

    app.dependency_overrides[get_provider] = ReaskProvider
    try:
        first = client.post("/analyze", json={"user_request": COMPLETE_REQUEST}).json()
        prior = dict(first)
        discovery = dict(prior.get("discovery") or {})
        discovery["unknowns"] = list(discovery.get("unknowns") or []) + [
            IMMEDIATE_ACCESS_QUESTION
        ]
        prior["discovery"] = discovery
        second = client.post(
            "/clarify",
            json={
                "user_request": COMPLETE_REQUEST,
                "clarification_answers": [IMMEDIATE_ACCESS_BLOB],
                "iteration": first["iteration"],
                "run_id": first["run_id"],
                "prior_state": prior,
                "clarification_history": first.get("clarification_history") or [],
            },
        )
        assert second.status_code == 200
        data = second.json()
        asked = _question_text(data.get("non_blocking_questions"))
        asked += " " + _question_text(
            (data.get("validation") or {}).get("non_blocking_questions")
        )
        asked += " " + _question_text((data.get("assessment") or {}).get("ask_next"))
        assert IMMEDIATE_ACCESS_QUESTION.lower() not in asked
        history = data.get("clarification_history") or []
        assert any(
            str(item.get("question") or "") == "Customer clarification"
            for item in history
            if isinstance(item, dict)
        )
    finally:
        app.dependency_overrides[get_provider] = MockProvider


def test_legacy_non_substantive_answer_does_not_suppress():
    for answer in ("TBD", "I don't know"):
        assert is_non_substantive_clarification_answer(answer) is True
        blob = f"{IMMEDIATE_ACCESS_QUESTION}: {answer}"
        state = _validation_state(
            history=[{"question": "Customer clarification", "answer": blob}],
            unknowns=[IMMEDIATE_ACCESS_QUESTION],
        )
        result = validation_agent(
            state,
            _ValidationScriptProvider(non_blocking=[IMMEDIATE_ACCESS_QUESTION]),
        )
        asked = _question_text(result["validation"]["non_blocking_questions"])
        assert IMMEDIATE_ACCESS_QUESTION.lower() in asked, answer
        assert _normalize_question_text(IMMEDIATE_ACCESS_QUESTION) not in _answered_question_texts(state)


def test_legacy_follow_up_question_remains():
    blob = "Do we have API access?: yes, we have access"
    state = _validation_state(
        history=[{"question": "Customer clarification", "answer": blob}],
        unknowns=[FOLLOW_UP_RATE_LIMITS],
    )
    result = validation_agent(
        state,
        _ValidationScriptProvider(non_blocking=[FOLLOW_UP_RATE_LIMITS]),
    )
    asked = _question_text(result["validation"]["non_blocking_questions"])
    assert FOLLOW_UP_RATE_LIMITS.lower() in asked
    assert "do we have api access?" not in asked
    assert _normalize_question_text("Do we have API access?") in _answered_question_texts(state)


INTEGRATION_COMPLEXITY_QUESTION = (
    "What is the integration complexity and API availability for the ERP "
    "and payment provider?"
)
INTEGRATION_COMPLEXITY_UNKNOWN = (
    "Integration complexity and API availability for the ERP and payment provider"
)
DEADLINE_TYPE_QUESTIONS = [
    "Is the 2-month date a target or a contractual deadline?",
    "Whether the 2-month date is a contractual deadline or an internal target",
    "Is the 2-month delivery date a contractual deadline with penalties, or is it a target planning date?",
    "Is the 2-month date a contractual deadline or a flexible target?",
]
PENALTY_ONLY_QUESTION = (
    "Are there contractual penalties or liquidated damages for missing the deadline?"
)
VOLUME_ANSWER = "About 500 enterprise users with 50 concurrent users during peak."
ROLES_ANSWER = "Admin and requester roles with role-based access."


def test_integration_interrogative_stem_dedupes_to_one_question():
    assert _question_dedup_key(INTEGRATION_COMPLEXITY_QUESTION) == _question_dedup_key(
        INTEGRATION_COMPLEXITY_UNKNOWN
    )
    state = _validation_state(unknowns=[INTEGRATION_COMPLEXITY_UNKNOWN])
    result = validation_agent(
        state,
        _ValidationScriptProvider(non_blocking=[INTEGRATION_COMPLEXITY_QUESTION]),
    )
    items = [
        q for q in result["validation"]["non_blocking_questions"]
        if _question_dedup_key(q) == _question_dedup_key(INTEGRATION_COMPLEXITY_QUESTION)
    ]
    assert len(items) == 1
    assert items[0] == INTEGRATION_COMPLEXITY_QUESTION


def test_deadline_type_paraphrases_collapse_to_one_question():
    for question in DEADLINE_TYPE_QUESTIONS:
        assert _question_topic(question) == "deadline_type"
    assert _question_topic("What is the target delivery timeline?") is None
    state = _validation_state(unknowns=[DEADLINE_TYPE_QUESTIONS[1]])
    result = validation_agent(
        state,
        _ValidationScriptProvider(non_blocking=DEADLINE_TYPE_QUESTIONS),
    )
    items = [
        q for q in result["validation"]["non_blocking_questions"]
        if _question_topic(q) == "deadline_type"
    ]
    assert len(items) == 1
    assert items[0] == DEADLINE_TYPE_QUESTIONS[0]


def test_answered_deadline_type_suppresses_later_paraphrases():
    history = [{
        "question": DEADLINE_TYPE_QUESTIONS[0],
        "answer": "The 2-month date is a planning target, not a contractual deadline.",
    }]
    state = _validation_state(history=history)
    assert "deadline_type" in _answered_clarification_topics(state)
    result = validation_agent(
        state,
        _ValidationScriptProvider(non_blocking=DEADLINE_TYPE_QUESTIONS[2:]),
    )
    items = [
        q for q in result["validation"]["non_blocking_questions"]
        if _question_topic(q) == "deadline_type"
    ]
    assert items == []


def test_penalty_only_follow_up_remains_after_contractual_date():
    assert _question_topic(PENALTY_ONLY_QUESTION) != "deadline_type"
    history = [{
        "question": DEADLINE_TYPE_QUESTIONS[0],
        "answer": "The date is contractual.",
    }]
    state = _validation_state(history=history)
    result = validation_agent(
        state,
        _ValidationScriptProvider(
            non_blocking=[DEADLINE_TYPE_QUESTIONS[3], PENALTY_ONLY_QUESTION]
        ),
    )
    asked = _question_text(result["validation"]["non_blocking_questions"])
    assert PENALTY_ONLY_QUESTION.lower() in asked
    assert DEADLINE_TYPE_QUESTIONS[3].lower() not in asked


def test_volume_and_roles_both_present_when_neither_answered():
    state = _validation_state()
    result = validation_agent(state, _ValidationScriptProvider(non_blocking=[]))
    items = result["validation"]["non_blocking_questions"]
    volume = [q for q in items if _question_topic(q) == "user_volume"]
    roles = [q for q in items if _question_topic(q) == "roles_permissions"]
    assert len(volume) == 1
    assert len(roles) == 1
    assert volume[0] == VOLUME_FOLLOW_UP_QUESTION
    assert roles[0] == ROLES_FOLLOW_UP_QUESTION


def test_volume_answered_leaves_roles_question():
    history = [{"question": VOLUME_FOLLOW_UP_QUESTION, "answer": VOLUME_ANSWER}]
    state = _validation_state(history=history)
    result = validation_agent(state, _ValidationScriptProvider(non_blocking=[]))
    items = result["validation"]["non_blocking_questions"]
    assert not [q for q in items if _question_topic(q) == "user_volume"]
    roles = [q for q in items if _question_topic(q) == "roles_permissions"]
    assert len(roles) == 1


def test_roles_answered_leaves_volume_question():
    history = [{"question": ROLES_FOLLOW_UP_QUESTION, "answer": ROLES_ANSWER}]
    state = _validation_state(history=history)
    result = validation_agent(state, _ValidationScriptProvider(non_blocking=[]))
    items = result["validation"]["non_blocking_questions"]
    assert not [q for q in items if _question_topic(q) == "roles_permissions"]
    volume = [q for q in items if _question_topic(q) == "user_volume"]
    assert len(volume) == 1


def test_volume_and_roles_both_answered_return_neither():
    history = [
        {"question": VOLUME_FOLLOW_UP_QUESTION, "answer": VOLUME_ANSWER},
        {"question": ROLES_FOLLOW_UP_QUESTION, "answer": ROLES_ANSWER},
    ]
    state = _validation_state(history=history)
    result = validation_agent(state, _ValidationScriptProvider(non_blocking=[]))
    items = result["validation"]["non_blocking_questions"]
    assert not [q for q in items if _question_topic(q) == "user_volume"]
    assert not [q for q in items if _question_topic(q) == "roles_permissions"]

