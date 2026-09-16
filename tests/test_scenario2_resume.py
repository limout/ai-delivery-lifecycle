from app.api import get_provider
from app.evidence import (
    customer_authored_text,
    has_first_release_scope,
    has_named_integration,
    is_estimable,
    material_evidence_gaps,
    needs_integration_clarity,
)
from app.main import app
from app.providers import MockProvider
from app.resume import apply_clarification_facts
from app.timeline import parse_requested_deadline
from fastapi.testclient import TestClient
from tests.test_phase0 import COMPLETE_REQUEST
from tests.test_phase01 import SCENARIO_3


app.dependency_overrides[get_provider] = MockProvider
client = TestClient(app)

SCENARIO_2 = (
    "We need a new AI-powered customer portal for our enterprise customers. "
    "It should integrate with our existing systems and automate several manual "
    "processes. We want it ready for an important customer event in about two "
    "months. The exact scope is still being discussed, but we would like a "
    "proposal and delivery estimate as soon as possible."
)

SYSTEMS_ANSWER = (
    "The first release must integrate with Salesforce for customer/account data "
    "and ServiceNow for support requests. Salesforce is the source of truth for "
    "customer and account information, while ServiceNow is the source of truth "
    "for support tickets."
)

SYSTEMS_QUESTION = (
    "Which systems must the first release integrate with, and what is the source of truth?"
)


def _blocking_text(data: dict) -> str:
    items = data.get("blocking_questions") or []
    parts = []
    for item in items:
        if isinstance(item, dict):
            parts.append(str(item.get("question") or ""))
        else:
            parts.append(str(item))
    return " ".join(parts).lower()


def test_parses_about_two_months_as_deadline():
    hit = parse_requested_deadline([
        "We want it ready for an important customer event in about two months."
    ])
    assert hit is not None
    assert hit.weeks > 8
    assert "month" in hit.display.lower()
    assert "2" in hit.display


def test_scenario_2_scope_is_not_estimable_even_after_systems_answer():
    assert has_first_release_scope(SCENARIO_2) is False
    accumulated = {
        "user_request": SCENARIO_2,
        "clarification_history": [
            {"question": SYSTEMS_QUESTION, "answer": SYSTEMS_ANSWER}
        ],
    }
    text = customer_authored_text(accumulated)
    assert "about two months" in text
    assert "Salesforce" in text
    assert has_first_release_scope(text) is False
    codes = {gap.code for gap in material_evidence_gaps(accumulated)}
    assert "first_release_scope" in codes
    assert "integrations" not in codes
    assert is_estimable(accumulated) is False


def test_evidence_gate_uses_request_plus_answers_not_answer_only():
    answer_only = {"user_request": "", "clarification_history": [
        {"question": SYSTEMS_QUESTION, "answer": SYSTEMS_ANSWER}
    ]}
    full = {
        "user_request": SCENARIO_2,
        "clarification_history": [
            {"question": SYSTEMS_QUESTION, "answer": SYSTEMS_ANSWER}
        ],
    }
    assert "two months" not in customer_authored_text(answer_only).lower()
    assert "two months" in customer_authored_text(full).lower()
    assert parse_requested_deadline([customer_authored_text(full)]) is not None


def test_apply_clarification_preserves_original_deadline_constraint():
    merged = apply_clarification_facts({
        "user_request": SCENARIO_2,
        "discovery": {
            "problem": "Portal",
            "constraints": [],
            "unknowns": [],
        },
        "requirements": {"functional_requirements": [], "open_questions": []},
        "clarification_history": [
            {"question": SYSTEMS_QUESTION, "answer": SYSTEMS_ANSWER}
        ],
    })
    constraints = " ".join(str(item) for item in merged["discovery"]["constraints"]).lower()
    assert "month" in constraints
    assert "2" in constraints


def test_scenario_2_clarify_systems_keeps_deadline_and_stays_needs_info():
    first = client.post("/analyze", json={"user_request": SCENARIO_2}).json()
    assert first["status"] == "NEEDS_INFO"
    first_deadline = (first.get("assessment") or {}).get("deadline") or {}
    assert first_deadline.get("requested")
    assert "not provided" not in str(first_deadline.get("requested") or "").lower()

    second = client.post(
        "/clarify",
        json={
            "user_request": SCENARIO_2,
            "answers": [{"question": SYSTEMS_QUESTION, "answer": SYSTEMS_ANSWER}],
            "iteration": first["iteration"],
            "run_id": first["run_id"],
            "prior_state": first,
            "clarification_history": first.get("clarification_history") or [],
        },
    ).json()

    assert second["status"] == "NEEDS_INFO"
    assert second["status"] != "COMPLETE"
    deadline = second["assessment"]["deadline"]
    assert deadline["requested"]
    assert "not provided" not in deadline["requested"].lower()
    assert "month" in deadline["requested"].lower()
    assert "2" in deadline["requested"]
    assert deadline["independent_estimate"] == "Not yet estimable"
    estimate = second.get("estimate") or {}
    duration = str(estimate.get("duration_range") or "")
    assert duration == "" or "not yet estimable" in duration.lower()
    assert not any(ch.isdigit() for ch in duration) or "not yet" in duration.lower()
    blocking = _blocking_text(second)
    assert "scope" in blocking or "capabilit" in blocking
    next_step = " ".join(second["assessment"]["recommended_next_step"]).lower()
    assert "explicit deadline" not in next_step
    assert "provide a deadline" not in next_step
    assert "target delivery timeline" not in next_step
    assert "scope" in next_step or "capabilit" in next_step


def test_scenario_1_and_3_still_complete():
    one = client.post("/analyze", json={"user_request": COMPLETE_REQUEST}).json()
    assert one["status"] == "COMPLETE"
    assert any(ch.isdigit() for ch in one["estimate"]["duration_range"])
    three = client.post("/analyze", json={"user_request": SCENARIO_3}).json()
    assert three["status"] == "COMPLETE"
    assert three["estimate"]["standard_deadline_fit"] == "EXCEEDS"
    assert three["verdict"]["code"] == "DEADLINE_AT_RISK"


IDENTITY_SYSTEMS_ANSWER = (
    "The only external system required for the first release is the customer's existing identity provider.\n\n"
    "The identity provider is the source of truth for:\n"
    "- user identity\n"
    "- authentication\n"
    "- user status\n\n"
    "The portal is the source of truth for:\n"
    "- documents\n"
    "- search index\n"
    "- application roles and permissions\n"
    "- analytics\n"
    "- administration settings\n\n"
    "No other external system integrations are required for the first release."
)

IDENTITY_PORTAL_REQUEST = (
    "We need to build a new customer support knowledge portal in 8 weeks. "
    "Users: support agents and customers. "
    "It will include document ingestion, search, role-based access, analytics "
    "and an admin interface. "
    "The team estimates 12-16 weeks using the standard delivery approach. "
    "It must integrate with our existing systems."
)


def test_unnamed_existing_systems_still_need_integration_clarity():
    assert needs_integration_clarity(IDENTITY_PORTAL_REQUEST) is True
    assert has_named_integration(IDENTITY_PORTAL_REQUEST) is False
    assert has_named_integration(IDENTITY_SYSTEMS_ANSWER) is True
    accumulated = {
        "user_request": IDENTITY_PORTAL_REQUEST,
        "clarification_history": [
            {"question": SYSTEMS_QUESTION, "answer": IDENTITY_SYSTEMS_ANSWER}
        ],
    }
    source = customer_authored_text(accumulated)
    assert "identity provider" in source.lower()
    assert needs_integration_clarity(source) is False
    assert "integrations" not in {gap.code for gap in material_evidence_gaps(accumulated)}


def test_other_evidence_gaps_still_block_when_systems_are_unnamed():
    vague = "We want a portal that must integrate with our existing systems."
    codes = {gap.code for gap in material_evidence_gaps({"user_request": vague})}
    assert "integrations" in codes
    assert "first_release_scope" in codes
    assert is_estimable({"user_request": vague}) is False


def test_identity_provider_answer_clears_integration_blocker_on_resume():
    first = client.post("/analyze", json={"user_request": IDENTITY_PORTAL_REQUEST}).json()
    assert first["status"] == "NEEDS_INFO"
    assert SYSTEMS_QUESTION.lower() in _blocking_text(first)
    gaps_before = material_evidence_gaps(first)
    assert any(gap.code == "integrations" for gap in gaps_before)
    assert any("systems are not named" in gap.reason for gap in gaps_before)

    history = list(first.get("clarification_history") or [])
    payload = {
        "user_request": IDENTITY_PORTAL_REQUEST,
        "answers": [{"question": SYSTEMS_QUESTION, "answer": IDENTITY_SYSTEMS_ANSWER}],
        "iteration": first["iteration"],
        "run_id": first["run_id"],
        "prior_state": first,
        "clarification_history": history,
    }
    second = client.post("/clarify", json=payload).json()
    answers = " ".join(
        str(item.get("answer") or "")
        for item in (second.get("clarification_history") or [])
        if isinstance(item, dict)
    )
    assert "identity provider" in answers.lower()
    accumulated = customer_authored_text(second)
    assert "identity provider" in accumulated.lower()
    assert IDENTITY_SYSTEMS_ANSWER.split("\n")[0] in accumulated or "identity provider" in accumulated.lower()
    assert needs_integration_clarity(accumulated) is False
    assert "integrations" not in {gap.code for gap in material_evidence_gaps(second)}
    assert SYSTEMS_QUESTION.lower() not in _blocking_text(second)
    blob = str(second).lower()
    assert "major integration work is implied but the systems are not named" not in blob
    assert "integrat" not in _blocking_text(second)
    if second["status"] == "COMPLETE":
        assert any(ch.isdigit() for ch in str((second.get("estimate") or {}).get("duration_range") or ""))
    else:
        assert second["status"] == "NEEDS_INFO"
