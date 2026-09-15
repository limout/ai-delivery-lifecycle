from app.agents import estimation_agent, proposal_agent, sow_agent
from app.api import get_provider, run_workflow, workflow_response
from app.assessment import (
    ASSESSMENT_DISCLAIMER,
    ESTIMATE_DISCLAIMER,
    build_assessment,
    format_assessment_text,
    standard_deadline_fit,
)
from app.main import app
from app.providers import AIProvider, MockProvider
from app.resume import answers_require_upstream_regen, apply_clarification_facts
from fastapi.testclient import TestClient


app.dependency_overrides[get_provider] = MockProvider
client = TestClient(app)


COMPLETE_REQUEST = """
We need a self-service portal for enterprise customers.
Users: Enterprise customers.
Existing systems: Salesforce.
Target delivery timeline: 2 months.
Customers can view account information, submit service requests, and track status.
""".strip()


class CountingProvider(MockProvider):
    def __init__(self):
        self.calls = []

    def generate_json(self, prompt: str, schema: dict) -> dict:
        required = tuple((schema or {}).get("required") or [])
        self.calls.append(required[:3] or prompt[:40])
        return super().generate_json(prompt, schema)


class ScriptedProvider(AIProvider):
    def __init__(self, payload: dict):
        self.payload = payload

    def generate_json(self, prompt: str, schema: dict) -> dict:
        return dict(self.payload)


def _estimate_state(constraints: list[str], duration: str) -> dict:
    return {
        "user_request": (
            "Build a portal for enterprise customers who can submit service requests "
            "and track status."
        ),
        "discovery": {
            "problem": "Enterprise customers need self-service",
            "business_goal": "Reduce support effort",
            "users": ["Enterprise customers"],
            "stakeholders": [],
            "existing_systems": ["Salesforce"],
            "constraints": constraints,
            "assumptions": [],
            "unknowns": [],
        },
        "requirements": {
            "functional_requirements": ["Submit service requests"],
            "non_functional_requirements": [],
            "acceptance_criteria": [],
            "open_questions": [],
            "contradictions": [],
        },
        "solution": {"solution_summary": "A portal", "delivery_risks": ["Integration risk"]},
        "delivery_plan": {"delivery_phases": ["Build"], "delivery_risks": []},
    }


def test_analyze_complete_is_success_and_lands_on_assessment():
    response = client.post("/analyze", json={"user_request": COMPLETE_REQUEST})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMPLETE"
    assert data["verdict"]["code"] in {"DEADLINE_FIT", "DEADLINE_AT_RISK", "DEADLINE_UNCLEAR", "READY"}
    assert data["default_view"] == "assessment"
    assert data["estimate"]["standard_deadline_fit"] in {"FITS", "EXCEEDS", "NOT_DEMONSTRATED"}
    assert ESTIMATE_DISCLAIMER.split("—")[0].strip() in data["assessment"]["estimate_disclaimer"]
    text = data["assessment_text"]
    assert "AI DELIVERY ASSESSMENT" in text
    assert "EXECUTIVE VERDICT" in text
    assert "DEADLINE" in text
    assert "WHAT WE KNOW" in text
    assert "WHAT IS STILL UNCERTAIN" in text
    assert "TOP DELIVERY RISKS" in text
    assert "WHAT WE WOULD ASK NEXT" in text
    assert "DELIVERY OPTIONS" in text
    assert "RECOMMENDED NEXT STEP" in text
    assert "DISCLAIMER" in text
    assert ASSESSMENT_DISCLAIMER[:20] in text


def test_blocking_questions_are_canonical_and_non_blocking_do_not_block():
    response = client.post(
        "/analyze",
        json={"user_request": "We want to build a customer self-service portal."},
    )
    data = response.json()
    assert data["status"] == "NEEDS_INFO"
    assert data["blocking_questions"]
    assert data["validation"]["blocking_questions"]
    assert "blocking_uncertainty" not in data["validation"]
    non_blocking = data["non_blocking_questions"] or data["validation"].get("non_blocking_questions") or []
    blocking_text = " ".join(
        item["question"] if isinstance(item, dict) else str(item)
        for item in data["blocking_questions"]
    )
    for item in non_blocking:
        text = item["question"] if isinstance(item, dict) else str(item)
        assert text not in blocking_text or item != data["blocking_questions"][0]


def test_analyze_stream_emits_sse_events():
    with client.stream(
        "POST",
        "/analyze/stream",
        json={"user_request": "We want to build a customer self-service portal."},
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())
    assert "event: started" in body
    assert "event: stage" in body
    assert "event: result" in body
    assert "event: done" in body
    assert "NEEDS_INFO" in body
    assert "blocking_questions" in body


def test_clarification_preserves_state_and_skips_discovery():
    first = client.post(
        "/analyze",
        json={"user_request": "We want to build a customer self-service portal."},
    ).json()
    assert first["status"] == "NEEDS_INFO"
    assert first["run_id"]

    provider = CountingProvider()
    app.dependency_overrides[get_provider] = lambda: provider
    try:
        second = client.post(
            "/clarify",
            json={
                "user_request": "We want to build a customer self-service portal.",
                "answers": [
                    {
                        "question": "What is the target delivery timeline?",
                        "answer": "2 months",
                    }
                ],
                "iteration": first["iteration"],
                "run_id": first["run_id"],
                "prior_state": first,
                "clarification_history": first.get("clarification_history") or [],
            },
        )
    finally:
        app.dependency_overrides[get_provider] = MockProvider

    assert second.status_code == 200
    data = second.json()
    assert data["clarification_history"]
    execution = data["execution"]
    assert "discovery" not in execution["nodes_executed"]
    assert "requirements" not in execution["nodes_executed"]
    assert execution["nodes_skipped"] == ["discovery", "requirements"]
    assert data["discovery"]["problem"] == first["discovery"]["problem"]
    assert data["status"] == "NEEDS_INFO"
    assert data["estimate"] is None or str(data.get("estimate", {}).get("duration_range") or "").lower().find("not yet") >= 0 or not data.get("estimate")


def test_scope_answer_requires_upstream_regen():
    state = {
        "discovery": {"problem": "Portal", "unknowns": []},
        "requirements": {"functional_requirements": ["Submit requests"], "open_questions": []},
        "new_clarification_records": [
            {
                "question": "What are the main capabilities the portal should provide, and who will use it?",
                "answer": "Customers must also manage invoices and invoices become in scope.",
            }
        ],
    }
    assert answers_require_upstream_regen(state) is True


def test_timeline_answer_does_not_require_upstream_regen():
    state = {
        "discovery": {"problem": "Portal", "constraints": [], "unknowns": ["Target delivery timeline"]},
        "requirements": {"functional_requirements": ["Submit requests"], "open_questions": []},
        "new_clarification_records": [
            {"question": "What is the target delivery timeline?", "answer": "2 months"}
        ],
    }
    assert answers_require_upstream_regen(state) is False
    merged = apply_clarification_facts(state)
    assert any("timeline" in str(item).lower() for item in merged["discovery"]["constraints"])


def test_deadline_fits():
    provider = ScriptedProvider({
        "effort_range": "40-60 person-days",
        "duration_range": "4-6 weeks",
        "confidence": "MEDIUM",
        "assumptions": [],
        "risks_affecting_estimate": [],
    })
    result = estimation_agent(
        _estimate_state(["Target delivery timeline: 6 months"], "unused"),
        provider,
    )["estimate"]
    assert result["standard_deadline_fit"] == "FITS"


def test_deadline_exceeds():
    provider = ScriptedProvider({
        "effort_range": "40-60 person-days",
        "duration_range": "8-12 weeks",
        "confidence": "MEDIUM",
        "assumptions": [],
        "risks_affecting_estimate": [],
    })
    result = estimation_agent(
        _estimate_state(["Target delivery timeline: 1 month"], "unused"),
        provider,
    )["estimate"]
    assert result["standard_deadline_fit"] == "EXCEEDS"


def test_deadline_not_demonstrated():
    provider = ScriptedProvider({
        "effort_range": "40-60 person-days",
        "duration_range": "",
        "confidence": "LOW",
        "assumptions": [],
        "risks_affecting_estimate": [],
    })
    result = estimation_agent(
        _estimate_state(["Target delivery timeline: 2 months"], "unused"),
        provider,
    )["estimate"]
    assert result["standard_deadline_fit"] == "NOT_DEMONSTRATED"


def test_proposal_and_sow_respect_exceeds():
    estimate = {
        "standard_deadline_fit": "EXCEEDS",
        "customer_deadline": "1 month",
        "baseline_duration_range": "8-12 weeks",
        "duration_range": "8-12 weeks",
    }
    provider = ScriptedProvider({
        "executive_summary": "We will complete within one month.",
        "scope": ["Portal"],
        "delivery_approach": ["Phased"],
        "timeline": "Complete within one month",
        "assumptions": [],
        "risks": [],
        "next_steps": ["Sign"],
        "objectives": ["Ship"],
        "deliverables": ["Portal"],
        "in_scope": ["Portal"],
        "out_of_scope": [],
        "dependencies": [],
        "acceptance": [],
    })
    state = _estimate_state(["Target delivery timeline: 1 month"], "8-12 weeks")
    state["estimate"] = estimate
    proposal = proposal_agent(state, provider)["proposal"]
    sow = sow_agent(state, provider)["sow"]
    assert "EXCEEDS" in proposal["timeline"]
    assert "commitment" in proposal["timeline"].lower()
    assert "complete within one month" not in proposal["timeline"].lower()
    assert "EXCEEDS" in sow["timeline"]
    assert "commitment" in sow["timeline"].lower()


def test_assessment_contains_required_sections():
    payload = workflow_response({
        "workflow_status": "COMPLETE",
        "user_request": COMPLETE_REQUEST,
        "discovery": {
            "problem": "Need a portal",
            "business_goal": "Reduce effort",
            "users": ["Enterprise customers"],
            "existing_systems": ["Salesforce"],
            "constraints": ["Target delivery timeline: 2 months"],
            "unknowns": [],
        },
        "requirements": {"open_questions": ["What branding is required?"]},
        "estimate": {
            "duration_range": "6-10 weeks",
            "baseline_duration_range": "6-10 weeks",
            "customer_deadline": "2 months",
            "standard_deadline_fit": "FITS",
            "risks_affecting_estimate": ["Integration risk"],
        },
        "solution": {"delivery_risks": ["Integration risk"]},
        "blocking_questions": [],
        "non_blocking_questions": ["What branding is required?"],
    })
    text = payload["assessment_text"]
    for heading in (
        "AI DELIVERY ASSESSMENT",
        "EXECUTIVE VERDICT",
        "DEADLINE",
        "WHAT WE KNOW",
        "WHAT IS STILL UNCERTAIN",
        "TOP DELIVERY RISKS",
        "WHAT WE WOULD ASK NEXT",
        "DELIVERY OPTIONS",
        "RECOMMENDED NEXT STEP",
        "DISCLAIMER",
    ):
        assert heading in text
    assert payload["verdict"]["code"] == "DEADLINE_FIT"
    assert standard_deadline_fit(payload["estimate"]) == "FITS"


def test_mock_provider_still_used_for_analyze():
    response = client.post(
        "/analyze",
        json={"user_request": "We want to build a customer self-service portal."},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "NEEDS_INFO"
