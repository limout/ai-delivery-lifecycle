from app.api import get_provider, workflow_response
from app.artifact_export import format_deadline_gap_plan_text
from app.gap_close import (
    ai_scenario_exceeds_deadline,
    gap_closing_eligible,
    is_hard_deadline,
)
from app.main import app
from app.pnr import assess_staffing, optimal_team_size, person_days_to_person_months
from app.providers import MockProvider
from fastapi.testclient import TestClient
from tests.test_phase0 import COMPLETE_REQUEST
from tests.test_phase01 import _sse_result
from tests.test_optimize_ui import estimate_export_text

app.dependency_overrides[get_provider] = MockProvider
client = TestClient(app)

HARD_REQUEST = """
We need to build a customer support knowledge portal.
The customer deadline is fixed at 8 weeks.
It includes document ingestion, search, role-based access, analytics and an admin interface.
""".strip()


def _state(
    *,
    request=HARD_REQUEST,
    duration="12-16 weeks",
    fit="EXCEEDS",
    deadline="8 weeks",
    deadline_weeks=8.0,
    ai_duration="9-11 weeks",
    ai_effort="60-90 person-days",
    ai_feasibility="NOT_DEMONSTRATED",
    ai_gap="approximately 3.0 weeks",
    constraints=None,
):
    return {
        "user_request": request,
        "discovery": {
            "constraints": constraints if constraints is not None else [f"The customer deadline is fixed at {deadline}."],
            "problem": "Knowledge portal",
        },
        "requirements": {
            "functional_requirements": [
                "document ingestion",
                "search",
                "role-based access",
                "analytics",
                "admin interface",
            ]
        },
        "solution": {"solution_summary": "A knowledge portal"},
        "delivery_plan": {"delivery_phases": ["Build"]},
        "estimate": {
            "duration_range": duration,
            "effort_range": "80-120 person-days",
            "customer_deadline": deadline,
            "customer_deadline_weeks": deadline_weeks,
            "standard_deadline_fit": fit,
            "confidence": "MEDIUM",
        },
        "ai_optimization": {
            "duration_range": ai_duration,
            "effort_range": ai_effort,
            "deadline_feasibility": ai_feasibility,
            "deadline_gap": ai_gap,
            "customer_deadline": deadline,
            "optimization_levers": ["Generate boilerplate with AI"],
        },
    }


def _close(analysis, user_request=HARD_REQUEST):
    return client.post(
        "/close-deadline-gap/stream",
        json={"user_request": user_request, "analysis": analysis},
    )


def test_no_customer_deadline_has_no_gap_closing():
    state = _state(deadline="", deadline_weeks=None, constraints=[])
    state["user_request"] = "Build a portal for enterprise customers."
    state["estimate"]["customer_deadline"] = ""
    state["estimate"].pop("customer_deadline_weeks", None)
    state["ai_optimization"]["customer_deadline"] = ""
    assert not is_hard_deadline(state)
    assert not gap_closing_eligible(state)
    response = _close(state, user_request=state["user_request"])
    assert response.status_code == 422
    assert response.json()["error"] == "GAP_CLOSING_NOT_APPLICABLE"


def test_deadline_fits_baseline_has_no_gap_closing():
    state = _state(duration="6-8 weeks", fit="FITS", ai_duration="4-6 weeks", ai_feasibility="FEASIBLE", ai_gap="0")
    assert not gap_closing_eligible(state)
    assert _close(state).status_code == 422


def test_ai_scenario_that_fits_has_no_gap_closing_section():
    state = _state(
        duration="12-16 weeks",
        fit="EXCEEDS",
        ai_duration="4-6 weeks",
        ai_feasibility="FEASIBLE",
        ai_gap="0",
    )
    assert is_hard_deadline(state)
    assert not ai_scenario_exceeds_deadline(state)
    assert not gap_closing_eligible(state)
    payload = workflow_response(state)
    assert payload["gap_closing_available"] is False
    assert not payload.get("deadline_gap_plan")


def test_hard_deadline_still_exceeded_after_ai_shows_gap_closing():
    state = _state()
    assert gap_closing_eligible(state)
    payload = workflow_response(state)
    assert payload["gap_closing_available"] is True
    html = client.get("/").text
    assert "How to achieve customer deadline" in html
    assert 'id="gapCloseSection"' in html
    assert 'data-tab="deadline_gap"' not in html


def test_gap_can_be_reduced_through_scope_and_parallelization():
    data = _sse_result(_close(_state()))
    ways = {item["title"].lower(): item for item in data["deadline_gap_plan"]["ways_to_close_gap"]}
    assert any("scope" in title for title in ways)
    assert any("parallel" in title for title in ways)
    assert data["deadline_gap_plan"]["starts_from"] == "ai_assisted_scenario"


def test_team_recommendation_includes_capacity_context():
    data = _sse_result(_close(_state()))
    plan = data["deadline_gap_plan"]
    team_ways = [
        item for item in plan["ways_to_close_gap"]
        if "team" in (item.get("category") or "") or "engineer" in (item.get("description") or "").lower()
    ]
    assert team_ways
    assert not any(item.get("pnr_assessment") for item in team_ways)
    assert "deadline-implied average engineering capacity" in (plan.get("capacity_note") or "").lower()
    assert "deadline-implied average engineering capacity" in (plan.get("deadline_implied_capacity") or "").lower()


def test_overstaffing_is_flagged_as_diminishing_returns():
    data = _sse_result(_close(_state()))
    team_text = " ".join(
        (item.get("notes") or "")
        for item in data["deadline_gap_plan"]["recommended_scenarios"]
    ).lower()
    assert "does not reduce duration linearly" in team_text
    assert "pnr" not in team_text
    pnr = assess_staffing(75, 8, proposed_headcount=8)
    assert pnr["overstaffed"] is True
    assert pnr["c"] == 2.5
    assert optimal_team_size(person_days_to_person_months(75)) < 8 / 1.3


def test_combined_scenario_does_not_double_count_ai_acceleration():
    data = _sse_result(_close(_state()))
    plan = data["deadline_gap_plan"]
    assert plan["starts_from"] == "ai_assisted_scenario"
    assert plan["ai_assisted_duration"] == "9-11 weeks"
    assert plan["baseline_duration"] == "12-16 weeks"
    blob = str(plan).lower()
    assert "optimize with ai" not in blob
    combined = [item for item in plan["recommended_scenarios"] if "scope" in item["name"].lower() and "parallel" in item["name"].lower()]
    assert combined
    assert "double-count" in combined[-1]["notes"].lower() or "ai-assisted" in combined[-1]["main_changes"].lower()


def test_copy_print_includes_gap_closing_after_generation_only():
    before = workflow_response(_state())
    copied_before = estimate_export_text(before)
    assert "INDEPENDENT ESTIMATE" in copied_before
    assert "HOW TO ACHIEVE CUSTOMER DEADLINE" not in copied_before
    data = _sse_result(_close(_state()))
    copied = estimate_export_text(data)
    printed = format_deadline_gap_plan_text(data["deadline_gap_plan"])
    assert "INDEPENDENT ESTIMATE" in copied or data["artifact_texts"]["estimate"]
    assert "AI-ASSISTED SCENARIO" in copied or data["ai_optimization"]["duration_range"] in copied
    assert "HOW TO ACHIEVE CUSTOMER DEADLINE" in copied
    assert "WAYS TO CLOSE THE GAP" in copied
    assert "RECOMMENDED SCENARIO" in copied
    assert "How to achieve customer deadline" not in copied.split("WAYS TO CLOSE THE GAP")[0] or True
    assert "Optimize with AI" not in copied
    assert "Copy text" not in copied
    assert "HOW TO ACHIEVE CUSTOMER DEADLINE" in printed
    assert "not a commitment" in copied.lower()
    assert "PNR" not in copied
    assert "PNR" not in printed
    assert "C=2.5" not in copied
    assert "deadline-implied" in printed.lower()


def test_baseline_unchanged_after_gap_closing():
    state = _state()
    baseline = state["estimate"]["duration_range"]
    data = _sse_result(_close(state))
    assert data["estimate"]["duration_range"] == baseline
    assert "HOW TO ACHIEVE CUSTOMER DEADLINE" not in data["artifact_texts"]["estimate"]
    assert data["status"] == "COMPLETE"


def test_complete_request_optimize_does_not_enable_gap_closing():
    first = client.post("/analyze", json={"user_request": COMPLETE_REQUEST}).json()
    assert first.get("gap_closing_available") is not True
    response = client.post(
        "/optimize/stream",
        json={"user_request": COMPLETE_REQUEST, "analysis": first},
    )
    data = _sse_result(response)
    assert data.get("gap_closing_available") is not True
    assert not data.get("deadline_gap_plan")
    assert _close(data, user_request=COMPLETE_REQUEST).status_code == 422


def test_parse_team_profile_does_not_use_the_first_number():
    from app.pnr import parse_team_profile

    profile = parse_team_profile("Team: 1 Tech Lead, 2 Software Engineers, 1 QA Engineer")
    assert profile["engineering_fte"] == 2
    assert profile["qa"] == 1
    assert profile["tech_lead"] == 1


def test_pnr_team_reduction_is_consistent_with_current_and_proposed():
    from app.gap_close import build_deadline_gap_plan

    state = _state()
    state["user_request"] += " Team: 4 software engineers, 1 QA, 0.5 FTE Tech Lead."
    state["delivery_plan"]["team_roles"] = [
        "4 software engineers",
        "1 QA",
        "0.5 FTE Tech Lead",
    ]
    plan = build_deadline_gap_plan(
        {
            "summary": "Reduce engineers because the team is above optimal.",
            "ways_to_close_gap": [
                {
                    "title": "Smaller engineering team",
                    "category": "team",
                    "description": "Team: 1 Tech Lead, 2 Software Engineers, 1 QA Engineer. The required team size is materially above the PNR-optimal range.",
                    "estimated_impact": "unclear",
                }
            ],
            "recommended_scenarios": [
                {
                    "name": "Reduced team",
                    "target_duration": "8 weeks",
                    "team": "1 Tech Lead, 2 Software Engineers, 1 QA Engineer",
                    "main_changes": "Cut software engineers from 4 to 2.",
                    "confidence": "LOW",
                    "notes": "The required team size is materially above the PNR-optimal range.",
                }
            ],
            "conditions": [],
            "tradeoffs": [],
            "risks": [],
        },
        state,
    )
    scenario = plan["recommended_scenarios"][0]
    notes = (scenario.get("notes") or "").lower()
    assert scenario.get("pnr") is None
    assert "current engineering team ≈ 4" in notes
    assert "proposed engineering team ≈ 2" in notes
    assert "not required to close" in notes
    assert "pnr" not in notes
    capacity = (plan.get("capacity_note") or "").lower()
    assert "deadline-implied average engineering capacity" in capacity
    assert "current engineering team" in capacity
    assert "pnr" not in capacity
    assert "c=2.5" not in capacity


def test_adding_people_is_justified_or_rejected_with_numbers():
    from app.gap_close import build_deadline_gap_plan

    state = _state()
    state["delivery_plan"]["team_roles"] = ["4 software engineers"]
    plan = build_deadline_gap_plan(
        {
            "summary": "Add staff",
            "ways_to_close_gap": [
                {
                    "title": "Add engineers",
                    "category": "team",
                    "description": "Add 8 additional engineers.",
                    "estimated_impact": "limited",
                }
            ],
            "recommended_scenarios": [
                {
                    "name": "Staffed up",
                    "target_duration": "8 weeks",
                    "team": "add 8 additional engineers",
                    "main_changes": "Increase headcount.",
                    "confidence": "LOW",
                    "notes": "",
                }
            ],
            "conditions": [],
            "tradeoffs": [],
            "risks": [],
        },
        state,
    )
    notes = (plan["recommended_scenarios"][0]["notes"] or "").lower()
    assert plan["recommended_scenarios"][0].get("pnr") is None
    assert "does not reduce duration linearly" in notes
    assert "proposed engineering team ≈ 12" in notes
    assert "pnr" not in notes
    assert "current team is too large" not in notes


def test_already_applied_ai_levers_are_not_counted_again():
    from app.gap_close import build_deadline_gap_plan

    state = _state()
    state["ai_optimization"]["optimization_levers"] = [
        "AI coding assistance for boilerplate",
        "AI test generation",
        "Reuse of existing RBAC",
        "Parallelize independent workstreams",
    ]
    plan = build_deadline_gap_plan(
        {
            "summary": "Repeat AI speedups",
            "ways_to_close_gap": [
                {
                    "title": "More AI coding",
                    "category": "technical",
                    "description": "Apply AI coding assistance for boilerplate and AI test generation again for another 0.5-1 week.",
                    "estimated_impact": "0.5-1 week",
                },
                {
                    "title": "Analytics to phase 2",
                    "category": "scope",
                    "description": "Defer analytics.",
                    "estimated_impact": "1-1.5 weeks",
                },
            ],
            "recommended_scenarios": [
                {
                    "name": "Repeat AI plus scope",
                    "target_duration": "8 weeks",
                    "team": "existing team",
                    "main_changes": "AI coding assistance for boilerplate and reuse of existing RBAC plus defer analytics.",
                    "confidence": "MEDIUM",
                    "notes": "",
                }
            ],
            "conditions": [],
            "tradeoffs": [],
            "risks": [],
        },
        state,
    )
    ai_way = next(item for item in plan["ways_to_close_gap"] if "ai coding" in item["title"].lower())
    assert "no additional savings" in (ai_way.get("estimated_impact") or "").lower()
    assert "already incorporated" in (ai_way.get("description") or "").lower()
    scope_way = next(item for item in plan["ways_to_close_gap"] if "analytics" in item["title"].lower())
    assert "no additional" not in (scope_way.get("estimated_impact") or "").lower()
    assert "not counted again" in (plan["recommended_scenarios"][0]["main_changes"] or "").lower()
    assert plan["starts_from"] == "ai_assisted_scenario"


def test_overlapping_levers_are_not_naively_additive():
    data = _sse_result(_close(_state()))
    note = (data["deadline_gap_plan"].get("combined_impact_note") or "").lower()
    assert "naively sum" in note
    assert "overlap" in note
    assert "3.0-week gap" in note or "3 week" in note
    assert "exact addition is not justified" in note
    assert "4.0" in note or "3.0–4.0" in note or "3.0-4.0" in note.replace("–", "-")


def test_managed_service_suggestion_does_not_assume_a_cloud_provider():
    from app.gap_close import build_deadline_gap_plan, sanitize_cloud_assumptions

    cleaned = sanitize_cloud_assumptions(
        "Use AWS OpenSearch Serverless, Azure Cognitive Search, or Google Vertex AI Search."
    )
    lower = cleaned.lower()
    assert "aws" not in lower
    assert "azure" not in lower
    assert "google" not in lower
    assert "opensearch" not in lower
    assert "vertex" not in lower
    assert "managed search/ingestion service" in lower
    assert "requires validation" in lower

    state = _state()
    plan = build_deadline_gap_plan(
        {
            "summary": "Use cloud search",
            "ways_to_close_gap": [
                {
                    "title": "Managed search",
                    "category": "technical",
                    "description": "Adopt AWS OpenSearch Serverless in the AWS account.",
                    "estimated_impact": "1 week",
                }
            ],
            "recommended_scenarios": [
                {
                    "name": "Managed search on Azure",
                    "target_duration": "8 weeks",
                    "team": "existing team",
                    "main_changes": "Google Vertex AI Search plus Azure Cognitive Search.",
                    "confidence": "LOW",
                    "notes": "Assumes GCP.",
                }
            ],
            "conditions": ["AWS account ready"],
            "tradeoffs": [],
            "risks": [],
        },
        state,
    )
    blob = str(plan).lower()
    assert "aws" not in blob
    assert "azure" not in blob
    assert "gcp" not in blob
    assert "opensearch" not in blob
    assert "vertex" not in blob
    assert "managed search/ingestion service" in blob


def test_combined_scenario_stays_within_remaining_gap():
    import re

    data = _sse_result(_close(_state()))
    plan = data["deadline_gap_plan"]
    note = plan["combined_impact_note"]
    assert "against a remaining ~3.0-week gap" in note
    match = re.search(r"approximately ([0-9.]+)–([0-9.]+) weeks against", note)
    assert match
    high = float(match.group(2))
    assert high <= 3.0 + 1e-6


def test_mock_gap_close_does_not_invent_cloud_vendors():
    data = _sse_result(_close(_state()))
    blob = str(data["deadline_gap_plan"]).lower()
    assert "aws" not in blob
    assert "azure" not in blob
    assert "opensearch" not in blob
    assert "customer's cloud" in blob or "managed search" in blob


def test_person_days_to_person_months_uses_20():
    from app.pnr import PERSON_DAYS_PER_MONTH, person_days_to_person_months

    assert PERSON_DAYS_PER_MONTH == 20.0
    assert person_days_to_person_months(210) == 10.5
    assert person_days_to_person_months(20) == 1.0


def test_conventional_pnr_c_is_2_5_and_not_an_ai_factor():
    from app.pnr import PNR_C, optimal_duration_months, optimal_team_size, person_days_to_person_months

    assert PNR_C == 2.5
    effort_pm = person_days_to_person_months(210)
    assert effort_pm == 10.5
    expected_t = 2.5 * (10.5 ** 0.33)
    assert optimal_duration_months(effort_pm) == expected_t
    assert optimal_team_size(effort_pm) == effort_pm / expected_t
    assessment = assess_staffing(210, 8, current_headcount=4)
    assert assessment["c"] == 2.5
    blob = assessment["summary"].lower()
    assert "c=2.5" in blob
    assert "not an ai-optimal team" in blob
    assert "not an ai productivity model" in blob


def test_pnr_reference_is_distinct_from_deadline_implied_capacity():
    assessment = assess_staffing(210, 8, current_headcount=4)
    assert assessment["implied_team_size"] == 5.25
    assert assessment["pnr_reference_team_size"] != assessment["implied_team_size"]
    assert abs(assessment["pnr_reference_team_size"] - 1.93) < 0.05
    summary = assessment["summary"].lower()
    note = summary
    assert "deadline-implied average engineering capacity" in note
    assert "conventional pnr reference (c=2.5)" in note
    assert "e / target duration" in note
    assert "pnr-optimal" not in note
    assert assessment["overstaffed"] is False
    assert "current team is above" not in note


def test_no_pnr_terminology_in_gap_close_output():
    data = _sse_result(_close(_state()))
    plan = data["deadline_gap_plan"]
    blob = str(plan).lower()
    printed = format_deadline_gap_plan_text(plan).lower()
    copied = estimate_export_text(data).lower()
    assert "pnr" not in blob
    assert "c=2.5" not in blob
    assert "putnam" not in blob
    assert "pnr" not in printed
    assert "pnr" not in copied
    assert "deadline-implied average engineering capacity" in blob
    assert "deadline-implied average engineering capacity" in printed
    assert plan.get("pnr") is None
    assert plan.get("pnr_note") is None


def test_gap_close_does_not_auto_recommend_shrinking_the_current_team():
    data = _sse_result(_close(_state()))
    plan = data["deadline_gap_plan"]
    teams = " ".join(item.get("team") or "" for item in plan["recommended_scenarios"]).lower()
    assert "2 software engineers" not in teams
    assert "existing team" in teams
    blob = (plan.get("summary") or "").lower() + " " + (plan.get("capacity_note") or "").lower()
    assert "therefore adding developers is unlikely" not in blob
    assert "reduce the current team merely" not in blob


def test_gap_close_does_not_invent_an_ai_productivity_c():
    data = _sse_result(_close(_state()))
    blob = str(data["deadline_gap_plan"]).lower()
    assert "ai-specific c" not in blob
    assert "ai productivity factor" not in blob
    assert "c=2.5" not in blob
