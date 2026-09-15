from app.agents import estimation_agent, ai_optimization_agent
from app.api import get_provider, workflow_response
from app.assessment import format_print_assessment
from app.evidence import is_estimable, material_evidence_gaps, statement_is_explicit
from app.main import app
from app.providers import MockProvider
from app.risks import normalize_delivery_risks
from app.resume import answers_require_upstream_regen, apply_clarification_facts
from fastapi.testclient import TestClient
from tests.test_phase0 import COMPLETE_REQUEST, ScriptedProvider, _estimate_state


app.dependency_overrides[get_provider] = MockProvider
client = TestClient(app)

VAGUE_REQUEST = "We want to build a customer self-service portal."

SCENARIO_3 = """
We need a self-service portal for enterprise customers.
Users: Enterprise customers.
Existing systems: Salesforce.
The customer wants the first production release in 4 weeks.
Customers can view account information, submit service requests, and track status.
""".strip()

SCENARIO_4 = """
Build an internal reporting portal for approximately 500 employees.
We already have an existing reporting API.
The target is 8 weeks.
""".strip()

SCOPE_ANSWER = (
    "First release: enterprise customers can view account information, "
    "submit service requests, and track status. Out of scope: billing."
)


def _sse_result(response) -> dict:
    payload = None
    for line in response.text.splitlines():
        if line.startswith("data:"):
            import json
            chunk = line[5:].strip()
            if chunk.startswith("{"):
                data = json.loads(chunk)
                if data.get("status") or data.get("estimate") or data.get("ai_optimization"):
                    payload = data
    assert payload, response.text[:500]
    return payload


def test_complete_sufficient_evidence_allows_numeric_estimate():
    data = client.post("/analyze", json={"user_request": COMPLETE_REQUEST}).json()
    assert data["status"] == "COMPLETE"
    assert data["estimate"]
    assert any(ch.isdigit() for ch in data["estimate"]["duration_range"])
    assert "not yet estimable" not in data["estimate"]["duration_range"].lower()


def test_missing_material_scope_stops_without_numeric_estimate():
    data = client.post("/analyze", json={"user_request": VAGUE_REQUEST}).json()
    assert data["status"] == "NEEDS_INFO"
    assert data["blocking_questions"]
    assert data.get("estimate") in (None, {}) or data.get("estimate", {}).get("not_yet_estimable")
    if data.get("estimate"):
        assert "not yet estimable" in str(data["estimate"].get("duration_range") or "").lower()
    else:
        assert data["assessment"]["deadline"]["independent_estimate"] == "Not yet estimable"
    assert data["verdict"]["code"] == "NEEDS_INFORMATION"


def test_known_deadline_insufficient_scope_keeps_deadline_and_not_estimable():
    data = client.post("/analyze", json={"user_request": SCENARIO_4}).json()
    assert data["status"] == "NEEDS_INFO"
    requested = data["assessment"]["deadline"]["requested"]
    assert requested
    assert "8" in requested
    assert data["assessment"]["deadline"]["independent_estimate"] == "Not yet estimable"
    next_step = " ".join(data["assessment"]["recommended_next_step"]).lower()
    assert "scope" in next_step or "first-release" in next_step or "first release" in next_step


def test_non_blocking_unknown_does_not_stop_complete_request():
    data = client.post("/analyze", json={"user_request": COMPLETE_REQUEST}).json()
    assert data["status"] == "COMPLETE"
    later = " ".join(str(item) for item in (data.get("non_blocking_questions") or [])).lower()
    assert "brand" in later or "roles" in later or "volume" in later or data["non_blocking_questions"] is not None


def test_timeline_only_clarification_skips_upstream():
    first = client.post("/analyze", json={"user_request": VAGUE_REQUEST}).json()
    second = client.post(
        "/clarify",
        json={
            "user_request": VAGUE_REQUEST,
            "answers": [{"question": "What is the target delivery timeline?", "answer": "8 weeks"}],
            "iteration": first["iteration"],
            "run_id": first["run_id"],
            "prior_state": first,
            "clarification_history": first.get("clarification_history") or [],
        },
    ).json()
    assert second["execution"]["nodes_skipped"] == ["discovery", "requirements"]
    assert second["status"] == "NEEDS_INFO"


def test_scope_changing_clarification_regenerates_upstream():
    state = {
        "discovery": {"problem": "Portal", "unknowns": []},
        "requirements": {"functional_requirements": ["Submit requests"], "open_questions": []},
        "new_clarification_records": [
            {
                "question": "What is in scope for the first production release?",
                "answer": SCOPE_ANSWER,
            }
        ],
    }
    assert answers_require_upstream_regen(state) is True


def test_scenario_3_deadline_exceeds():
    provider = ScriptedProvider({
        "effort_range": "40-80 person-days",
        "duration_range": "10-14 weeks",
        "confidence": "MEDIUM",
        "assumptions": [],
        "risks_affecting_estimate": ["Integration uncertainty"],
    })
    state = _estimate_state(["Target delivery timeline: 4 weeks"], "unused")
    state["user_request"] = SCENARIO_3
    estimate = estimation_agent(state, provider)["estimate"]
    assert estimate["standard_deadline_fit"] == "EXCEEDS"
    payload = workflow_response({
        "workflow_status": "COMPLETE",
        "user_request": SCENARIO_3,
        "discovery": state["discovery"],
        "estimate": estimate,
        "solution": {"delivery_risks": ["High risk of missing the deadline"]},
        "blocking_questions": [],
    })
    assert payload["verdict"]["code"] == "DEADLINE_AT_RISK"
    assert payload["estimate"]["standard_deadline_fit"] == "EXCEEDS"


def test_optional_ai_optimization_keeps_baseline_separate():
    first = client.post("/analyze", json={"user_request": COMPLETE_REQUEST}).json()
    assert first["status"] == "COMPLETE"
    baseline = first["estimate"]["duration_range"]
    fit = first["estimate"]["standard_deadline_fit"]
    response = client.post(
        "/optimize/stream",
        json={"user_request": COMPLETE_REQUEST, "analysis": first},
    )
    assert response.status_code == 200
    data = _sse_result(response)
    assert data["estimate"]["duration_range"] == baseline
    assert data["estimate"]["standard_deadline_fit"] == fit
    opt = data["ai_optimization"]
    assert opt["duration_range"]
    assert opt["duration_range"] != baseline or opt.get("optimization_summary")
    assert data["assessment"]["delivery_options"]["ai_assisted"]
    assert "guarantee" not in (opt.get("optimization_summary") or "").lower() or "not" in (opt.get("optimization_summary") or "").lower()
    assert "not a guaranteed" in (opt.get("optimization_summary") or "").lower() or "scenario analysis" in (opt.get("optimization_summary") or "").lower() or "optional" in (opt.get("optimization_summary") or "").lower()


def test_risk_deduplication_collapses_deadline_duplicates():
    risks = normalize_delivery_risks(
        [
            "High risk of missing the deadline",
            "High risk of missing the fixed deadline",
            "Salesforce integration approach is uncertain",
            "Salesforce API integration remains unclear",
            "Branding colors are undecided",
        ],
        deadline_fit="EXCEEDS",
        evidence="Independent estimate is 10-14 weeks vs requested 4 weeks.",
        limit=5,
    )
    joined = " ".join(risks).lower()
    assert len(risks) <= 4
    assert joined.count("deadline") >= 1
    assert "10-14" in joined or "compression" in joined
    assert joined.count("salesforce") <= 2


def test_facts_do_not_include_unsupported_user_inference():
    payload = workflow_response({
        "workflow_status": "COMPLETE",
        "user_request": "Build a claims workflow. Users can submit a claim and track status.",
        "discovery": {
            "problem": "Claims workflow",
            "users": ["Internal migration team"],
            "existing_systems": [],
            "constraints": [],
            "unknowns": [],
        },
        "estimate": {
            "duration_range": "10-12 weeks",
            "baseline_duration_range": "10-12 weeks",
            "customer_deadline": "",
            "standard_deadline_fit": "NOT_DEMONSTRATED",
        },
        "solution": {"delivery_risks": []},
    })
    known = " ".join(payload["assessment"]["what_we_know"]).lower()
    assert "internal migration team" not in known
    uncertain = " ".join(payload["assessment"]["what_is_uncertain"]).lower()
    assert "internal migration team" in uncertain or "inferred" in uncertain
    assert statement_is_explicit("Internal migration team", payload["user_request"]) is False


def test_recommended_next_step_for_undefined_scope():
    data = client.post("/analyze", json={"user_request": SCENARIO_4}).json()
    steps = " ".join(data["assessment"]["recommended_next_step"]).lower()
    assert "provide more information" not in steps
    assert "scope" in steps or "first release" in steps or "first-release" in steps
    assert "8" in steps or "date" in steps


def test_print_assessment_is_compact_one_page_structure():
    data = client.post("/analyze", json={"user_request": COMPLETE_REQUEST}).json()
    text = data["print_assessment_text"]
    for heading in (
        "AI DELIVERY ASSESSMENT",
        "VERDICT",
        "DEADLINE",
        "WHY",
        "TOP RISKS",
        "WHAT'S UNCERTAIN",
        "RECOMMENDED NEXT STEP",
        "DISCLAIMER",
    ):
        assert heading in text
    assert "WHAT WE WOULD ASK NEXT" not in text
    assert "REQUEST / PROJECT" not in text
    assert len(text) < len(data["assessment_text"])
    assert format_print_assessment(data["assessment"]).splitlines()[0] == "AI DELIVERY ASSESSMENT"


def test_evidence_gaps_for_vague_vs_complete():
    assert material_evidence_gaps({"user_request": VAGUE_REQUEST})
    assert is_estimable({"user_request": COMPLETE_REQUEST})
    assert not is_estimable({"user_request": SCENARIO_4})
