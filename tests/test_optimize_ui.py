"""Frontend contract tests for Optimize-with-AI visibility inside Estimate."""

from pathlib import Path

from app.api import get_provider
from app.main import app
from app.providers import MockProvider
from fastapi.testclient import TestClient
from tests.test_phase0 import COMPLETE_REQUEST
from tests.test_phase01 import _sse_result
from app.artifact_export import format_deadline_gap_plan_text

app.dependency_overrides[get_provider] = MockProvider
client = TestClient(app)

INDEX = Path("app/static/index.html").read_text(encoding="utf-8")


def has_ai_optimization_result(data):
    """Mirrors hasAiOptimizationResult() in app/static/index.html."""
    if not isinstance(data, dict):
        return False
    opt = data.get("ai_optimization")
    duration = ""
    if isinstance(opt, dict):
        duration = str(opt.get("duration_range") or "").strip()
    texts = data.get("artifact_texts") if isinstance(data.get("artifact_texts"), dict) else {}
    text = texts.get("ai_optimization")
    return bool(duration) or (isinstance(text, str) and bool(text.strip()))


def format_export_section(title, value):
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        if not items:
            return ""
        return title + "\n" + "\n".join(f"- {item}" for item in items)
    body = "" if value is None else str(value).strip()
    if not body:
        return ""
    return f"{title}\n{body}"


def format_ai_scenario_export_text(data):
    """Mirrors formatAiScenarioExportText() in app/static/index.html."""
    if not isinstance(data, dict):
        return ""
    duration = str(data.get("duration_range") or "").strip()
    if not duration:
        return ""
    status = str(data.get("deadline_feasibility") or "NOT_DEMONSTRATED").replace("_", " ")
    parts = [
        "AI-ASSISTED SCENARIO",
        "AI-assisted scenario. It never replaces the independent estimate and is not a guaranteed acceleration.",
        format_export_section("AI-assisted duration", duration),
        format_export_section("Customer estimate", data.get("customer_baseline_duration")),
        format_export_section("Independent estimate", data.get("standard_duration_range")),
        format_export_section("AI effort", data.get("effort_range")),
        format_export_section("Deadline", data.get("customer_deadline")),
        format_export_section("Deadline feasibility", status),
        format_export_section("Delivery gap", data.get("deadline_gap")),
        format_export_section("Confidence", data.get("confidence")),
        format_export_section("Team model", data.get("optimization_team_model")),
        format_export_section("Optimization summary", data.get("optimization_summary")),
        format_export_section("Optimization levers", data.get("optimization_levers") or []),
        format_export_section("Feasibility conditions", data.get("feasibility_conditions") or []),
        format_export_section("Scope trade-offs", data.get("scope_tradeoffs") or []),
        format_export_section("Recommendations", data.get("recommendations") or []),
    ]
    return "\n\n".join(part for part in parts if part) + "\n"


def estimate_export_text(data):
    """Mirrors estimateExportText() in app/static/index.html (state path)."""
    texts = data.get("artifact_texts") if isinstance(data, dict) else {}
    if not isinstance(texts, dict):
        texts = {}
    baseline = texts.get("estimate") or ""
    if not has_ai_optimization_result(data):
        return baseline
    ai = format_ai_scenario_export_text(data.get("ai_optimization") or {})
    gap = format_deadline_gap_plan_text(data.get("deadline_gap_plan"))
    chunks = [baseline.strip(), (ai or "").strip(), (gap or "").strip()]
    chunks = [item for item in chunks if item]
    if not chunks:
        return baseline
    return "\n\n".join(chunks) + "\n"


def preferred_tab_after_result(data, source="analyze"):
    """Mirrors preferredTabAfterResult() in app/static/index.html."""
    if source == "optimize" and has_ai_optimization_result(data):
        return "estimate"
    review = data.get("delivery_review") if isinstance(data, dict) else None
    if isinstance(review, dict) and str(review.get("status") or "").upper() == "BLOCKED":
        return "delivery_review"
    return "assessment"


def _analyze():
    return client.post("/analyze", json={"user_request": COMPLETE_REQUEST}).json()


def _optimize(analysis):
    response = client.post(
        "/optimize/stream",
        json={"user_request": COMPLETE_REQUEST, "analysis": analysis},
    )
    return _sse_result(response)


def _estimate_panel():
    start = INDEX.split('id="panel-estimate"', 1)[1]
    next_panel = start.find('id="panel-')
    return start if next_panel < 0 else start[:next_panel]


def test_optimize_with_ai_button_is_present():
    assert ">Optimize with AI<" in INDEX
    assert 'id="optimizeButton"' in INDEX
    assert 'id="optimizeButtonPanel"' in INDEX
    assert "Optional: Optimize with AI" not in INDEX


def test_optimization_ui_does_not_use_optional_wording():
    action_row = INDEX.split('class="action-row"', 1)[1].split("</div>", 1)[0]
    estimate_panel = _estimate_panel()
    render_fn = INDEX.split("function renderAIOptimization", 1)[1].split("function renderResult", 1)[0]
    for chunk in (action_row, estimate_panel, render_fn):
        assert "Optional" not in chunk
        assert "optional" not in chunk
    assert "Optional: Optimize with AI" not in INDEX


def test_no_ai_assisted_scenario_tab():
    assert 'data-tab="ai_optimization"' not in INDEX
    assert 'id="tab-ai_optimization"' not in INDEX
    assert 'id="panel-ai_optimization"' not in INDEX
    assert "AI-assisted Scenario" not in INDEX
    tabs = INDEX.split('id="artifactTabs"', 1)[1].split("</div>", 1)[0]
    assert "AI-assisted" not in tabs
    assert 'data-tab="estimate"' in INDEX


def test_ai_optimization_results_render_inside_estimate_tab():
    estimate_panel = _estimate_panel()
    assert 'id="aiOptimizationContent"' in estimate_panel
    assert "AI Delivery Optimization" in estimate_panel
    assert "AI-assisted scenario" in estimate_panel
    assert "never replaces the independent estimate" in estimate_panel
    assert "Independent human-only baseline" in estimate_panel
    assert 'id="estimateContent"' in estimate_panel
    assert INDEX.count('id="aiOptimizationContent"') == 1
    assert 'function renderAIOptimization' in INDEX
    assert "function estimateExportText" in INDEX
    assert "function formatAiScenarioExportText" in INDEX
    assert 'if (name === "estimate") return estimateExportText(currentData)' in INDEX


def test_successful_optimize_selects_estimate_not_assessment():
    after = {"ai_optimization": {"duration_range": "8-10 weeks"}}
    assert preferred_tab_after_result(after, "optimize") == "estimate"
    assert preferred_tab_after_result(after, "analyze") == "assessment"
    failed = {"status": "ERROR", "estimate": {"duration_range": "12-16 weeks"}}
    assert preferred_tab_after_result(failed, "optimize") == "assessment"


def test_estimate_copy_print_before_optimize_is_baseline_only():
    data = _analyze()
    copied = estimate_export_text(data)
    printed = copied
    assert "INDEPENDENT ESTIMATE" in copied
    assert data["estimate"]["duration_range"] in copied
    assert "AI-ASSISTED SCENARIO" not in copied
    assert "AI-assisted duration" not in copied
    assert "Optimize with AI" not in copied
    assert "Copy text" not in copied
    assert "Print / save as PDF" not in printed
    assert "INDEPENDENT ESTIMATE" in printed
    assert "AI-ASSISTED SCENARIO" not in printed


def test_estimate_copy_print_after_optimize_includes_ai_section():
    first = _analyze()
    baseline = first["estimate"]["duration_range"]
    data = _optimize(first)
    copied = estimate_export_text(data)
    printed = copied
    assert data["estimate"]["duration_range"] == baseline
    assert "INDEPENDENT ESTIMATE" in copied
    assert baseline in copied
    assert "AI-ASSISTED SCENARIO" in copied
    assert "AI-assisted duration" in copied
    assert data["ai_optimization"]["duration_range"] in copied
    assert "not a guaranteed acceleration" in copied.lower()
    for label in ("AI effort", "Confidence", "Deadline", "Deadline feasibility", "Delivery gap"):
        assert label in copied
    assert "Optimize with AI" not in copied
    assert "Copy text" not in copied
    assert "Print / save as PDF" not in printed
    assert "AI-ASSISTED SCENARIO" in printed
    assert baseline in printed
    assert data["ai_optimization"]["duration_range"] in printed
    assert "Optional" not in copied
    estimate_panel = _estimate_panel()
    assert 'id="aiOptimizationContent"' in estimate_panel
    assert 'data-tab="ai_optimization"' not in INDEX
    render_fn = INDEX.split("function renderAIOptimization", 1)[1].split("function renderResult", 1)[0]
    export_fn = INDEX.split("function formatAiScenarioExportText", 1)[1].split("function visibleEstimateAiText", 1)[0]
    for chunk in (estimate_panel, render_fn, export_fn):
        assert "Optional" not in chunk
    assert 'if (name === "estimate") return estimateExportText(currentData)' in INDEX
    assert "function copyArtifact" in INDEX
    assert "function printArtifact" in INDEX
    assert "const text = artifactText(name)" in INDEX
