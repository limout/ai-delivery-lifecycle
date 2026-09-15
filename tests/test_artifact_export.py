from app.api import get_provider, workflow_response
from app.artifact_export import (
    build_artifact_texts,
    format_ai_scenario_text,
    format_estimate_text,
    format_proposal_text,
    format_sow_text,
)
from app.main import app
from app.providers import MockProvider
from fastapi.testclient import TestClient
from tests.test_phase0 import COMPLETE_REQUEST
from tests.test_phase01 import VAGUE_REQUEST, _sse_result


app.dependency_overrides[get_provider] = MockProvider
client = TestClient(app)

COPY_PRINT_ARTIFACTS = (
    "assessment",
    "solution",
    "delivery_plan",
    "estimate",
    "proposal",
    "sow",
)


def test_home_page_has_copy_and_print_actions_for_each_artifact():
    html = client.get("/").text
    assert "Copy text" in html
    assert "Print / save as PDF" in html
    for name in COPY_PRINT_ARTIFACTS:
        assert f'data-copy-artifact="{name}"' in html
        assert f'data-print-artifact="{name}"' in html
        assert f'data-artifact-toolbar="{name}"' in html
        assert f'data-print-sheet="{name}"' in html
    assert 'data-tab="ai_optimization"' not in html
    assert 'data-copy-artifact="ai_optimization"' not in html
    assert "function copyArtifact" in html
    assert "function printArtifact" in html
    assert "artifact-panel.printing" in html


def test_complete_run_exposes_copy_text_for_generated_artifacts_only():
    data = client.post("/analyze", json={"user_request": COMPLETE_REQUEST}).json()
    texts = data["artifact_texts"]
    for name in ("assessment", "solution", "delivery_plan", "estimate", "proposal", "sow"):
        assert name in texts
        assert texts[name].strip()
    assert "ai_optimization" not in texts
    assert "SOLUTION" in texts["solution"]
    assert "DELIVERY PLAN" in texts["delivery_plan"]
    assert "INDEPENDENT ESTIMATE" in texts["estimate"]
    assert "PROPOSAL" in texts["proposal"]
    assert "STATEMENT OF WORK" in texts["sow"]
    assert "Executive summary" in texts["proposal"] or "EXECUTIVE" in texts["proposal"].upper()
    assert "Objectives" in texts["sow"] or "OBJECTIVES" in texts["sow"].upper()
    assert texts["assessment"] != texts["proposal"]
    assert texts["proposal"] != texts["sow"]
    assert "OPTIONAL AI-ASSISTED SCENARIO" not in texts["estimate"]


def test_needs_info_does_not_expose_ungenerated_artifact_text():
    data = client.post("/analyze", json={"user_request": VAGUE_REQUEST}).json()
    assert data["status"] == "NEEDS_INFO"
    texts = data["artifact_texts"]
    assert "assessment" in texts
    for name in ("solution", "delivery_plan", "estimate", "ai_optimization", "proposal", "sow"):
        assert name not in texts


def test_ai_scenario_copy_stays_separate_from_baseline():
    first = client.post("/analyze", json={"user_request": COMPLETE_REQUEST}).json()
    baseline = first["artifact_texts"]["estimate"]
    assert "OPTIONAL AI-ASSISTED SCENARIO" not in baseline
    response = client.post(
        "/optimize/stream",
        json={"user_request": COMPLETE_REQUEST, "analysis": first},
    )
    data = _sse_result(response)
    texts = data["artifact_texts"]
    assert texts["estimate"] == baseline or "INDEPENDENT ESTIMATE" in texts["estimate"]
    assert "OPTIONAL AI-ASSISTED SCENARIO" not in texts["estimate"]
    assert "ai_optimization" in texts
    ai = texts["ai_optimization"]
    assert ai.startswith("OPTIONAL AI-ASSISTED SCENARIO")
    assert "not a guaranteed" in ai.lower() or "scenario analysis" in ai.lower()
    assert data["estimate"]["duration_range"] in texts["estimate"]
    assert data["ai_optimization"]["duration_range"] in ai
    assert data["ai_optimization"]["duration_range"] not in texts["estimate"] or (
        data["ai_optimization"]["duration_range"] == data["estimate"]["duration_range"]
    )


def test_formatters_preserve_proposal_and_sow_headings():
    proposal = format_proposal_text({
        "executive_summary": "Build the portal.",
        "scope": ["Request tracking"],
        "timeline": "Indicative only",
        "next_steps": ["Review with delivery lead"],
    })
    sow = format_sow_text({
        "objectives": ["Enable self-service"],
        "deliverables": ["Portal increment"],
        "in_scope": ["Requests"],
        "out_of_scope": ["Billing"],
        "timeline": "See independent estimate",
    })
    assert proposal.startswith("PROPOSAL")
    assert "Executive summary" in proposal
    assert "Build the portal." in proposal
    assert sow.startswith("STATEMENT OF WORK")
    assert "Objectives" in sow
    assert "Out of scope" in sow
    assert format_ai_scenario_text({}) == ""
    assert "OPTIONAL AI-ASSISTED" not in format_estimate_text({
        "duration_range": "10-12 weeks",
        "effort_range": "40 person-days",
    })


def test_workflow_response_omits_empty_artifact_texts():
    payload = workflow_response({
        "workflow_status": "NEEDS_INFO",
        "user_request": VAGUE_REQUEST,
        "discovery": {"problem": "Portal", "unknowns": ["Scope"]},
        "blocking_questions": ["What is in scope for the first production release?"],
    })
    texts = build_artifact_texts(payload)
    assert "assessment" in texts
    assert "proposal" not in texts
    assert "sow" not in texts
    assert "estimate" not in texts
