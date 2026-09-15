from app.agents import _extract_explicit_timeline_facts, estimation_agent
from app.api import workflow_response
from app.timeline import parse_customer_estimate, parse_requested_deadline
from tests.test_phase0 import ScriptedProvider, _estimate_state


SCENARIO_1 = (
    "The customer wants the first production release in 12 weeks.\n"
    "We currently estimate approximately 10–12 weeks of work."
)

SCENARIO_1_FULL = (
    "Enterprise customers can view account information, submit service requests, "
    "and track status.\n"
    + SCENARIO_1
)


def test_parses_in_12_weeks_as_deadline():
    hit = parse_requested_deadline(["The customer wants the first production release in 12 weeks."])
    assert hit is not None
    assert hit.weeks == 12
    assert "12" in hit.display
    assert "week" in hit.display.lower()


def test_parses_within_12_weeks_as_deadline():
    hit = parse_requested_deadline(["Ship within 12 weeks."])
    assert hit is not None
    assert hit.weeks == 12


def test_parses_12_weeks_from_now_as_deadline():
    hit = parse_requested_deadline(["Go live 12 weeks from now."])
    assert hit is not None
    assert hit.weeks == 12


def test_parses_in_three_months_as_deadline():
    hit = parse_requested_deadline(["Deliver in three months."])
    assert hit is not None
    assert hit.display.lower().startswith("3")
    assert "month" in hit.display.lower()


def test_bare_three_months_is_not_a_deadline():
    assert parse_requested_deadline(["The work is three months."]) is None


def test_customer_estimate_is_not_the_deadline():
    texts = [SCENARIO_1]
    deadline = parse_requested_deadline(texts)
    estimate = parse_customer_estimate(texts)
    assert deadline is not None
    assert deadline.weeks == 12
    assert estimate is not None
    assert "10" in estimate.display and "12" in estimate.display
    assert estimate.kind == "estimate"
    assert deadline.kind == "deadline"


def test_extract_facts_keep_deadline_and_estimate_separate():
    facts = _extract_explicit_timeline_facts(SCENARIO_1)
    joined = " ".join(facts).lower()
    assert any("12 week" in item.lower() and "timeline" in item.lower() for item in facts)
    assert any("estimate" in item.lower() and "10" in item for item in facts)
    assert "business_goal" not in joined


def test_scenario_1_canonical_deadline_and_fit():
    facts = _extract_explicit_timeline_facts(SCENARIO_1)
    provider = ScriptedProvider({
        "effort_range": "40-80 person-days",
        "duration_range": "10-14 weeks",
        "confidence": "MEDIUM",
        "assumptions": [],
        "risks_affecting_estimate": ["Integration uncertainty"],
    })
    state = _estimate_state(facts, "unused")
    state["user_request"] = SCENARIO_1_FULL
    estimate = estimation_agent(state, provider)["estimate"]

    assert "12" in estimate["customer_deadline"]
    assert "week" in estimate["customer_deadline"].lower()
    assert "10" in estimate["customer_baseline_duration"]
    assert "12" in estimate["customer_baseline_duration"]
    assert estimate["duration_range"] == "10-14 weeks"
    assert estimate["baseline_duration_range"] == "10-14 weeks"
    assert estimate["standard_deadline_fit"] == "EXCEEDS"
    assert estimate["customer_deadline_weeks"] == 12

    payload = workflow_response({
        "workflow_status": "COMPLETE",
        "user_request": SCENARIO_1,
        "discovery": {
            "problem": "First production release",
            "business_goal": "Deliver the first production release within 12 weeks",
            "constraints": facts,
            "unknowns": [],
        },
        "estimate": estimate,
        "solution": {"delivery_risks": []},
        "blocking_questions": [],
        "non_blocking_questions": [],
    })
    requested = payload["assessment"]["deadline"]["requested"]
    assert requested
    assert "not provided" not in requested.lower()
    assert "12" in requested
    assert payload["assessment"]["deadline"]["fit"] == "EXCEEDS"
    assert payload["assessment"]["deadline"]["customer_estimate"]
    assert "10" in payload["assessment"]["deadline"]["customer_estimate"]
    assert "Requested deadline: Not provided" not in payload["assessment_text"]
    assert "Deadline not provided" not in payload["assessment_text"]
    assert payload["assessment"]["deadline"]["fit"] != "NOT_DEMONSTRATED"


def test_scenario_1_fit_uses_deadline_not_customer_estimate():
    facts = _extract_explicit_timeline_facts(SCENARIO_1)
    provider = ScriptedProvider({
        "effort_range": "40-80 person-days",
        "duration_range": "8-10 weeks",
        "confidence": "MEDIUM",
        "assumptions": [],
        "risks_affecting_estimate": [],
    })
    state = _estimate_state(facts, "unused")
    state["user_request"] = SCENARIO_1_FULL
    estimate = estimation_agent(state, provider)["estimate"]
    assert estimate["standard_deadline_fit"] == "FITS"
    assert estimate["customer_deadline_weeks"] == 12
    assert estimate["duration_range"] == "8-10 weeks"


def test_does_not_treat_business_goal_as_deadline_source():
    provider = ScriptedProvider({
        "effort_range": "40-80 person-days",
        "duration_range": "10-14 weeks",
        "confidence": "MEDIUM",
        "assumptions": [],
        "risks_affecting_estimate": [],
    })
    state = _estimate_state([], "unused")
    state["user_request"] = "Build a portal."
    state["discovery"]["business_goal"] = "Deliver the first production release within 12 weeks"
    estimate = estimation_agent(state, provider)["estimate"]
    assert estimate["customer_deadline"] == ""
    assert estimate["standard_deadline_fit"] == "NOT_DEMONSTRATED"
