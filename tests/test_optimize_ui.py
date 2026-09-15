"""Frontend contract tests for Optimize-with-AI visibility.

These tests cover the HTML/JS contract that JSON-only API tests miss:
tab availability, Estimate UI summary, Copy/Print separation, and tab selection.
The helpers below must stay aligned with app/static/index.html.
"""

from pathlib import Path

from app.main import app
from app.api import get_provider
from app.providers import MockProvider
from fastapi.testclient import TestClient
from tests.test_phase0 import COMPLETE_REQUEST
from tests.test_phase01 import _sse_result

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


def preferred_tab_after_result(data, source="analyze"):
    """Mirrors preferredTabAfterResult() in app/static/index.html."""
    if source == "optimize" and has_ai_optimization_result(data):
        return "ai_optimization"
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


def test_frontend_js_exposes_optimize_visibility_helpers():
    assert "function hasAiOptimizationResult" in INDEX
    assert "function preferredTabAfterResult" in INDEX
    assert "data.ai_optimization" in INDEX
    assert "artifact_texts.ai_optimization" in INDEX
    assert 'if (name === "ai_optimization")' in INDEX
    assert "return hasAiOptimizationResult(data)" in INDEX
    assert 'payload => renderResult(payload, "optimize")' in INDEX
    assert "selectTab(preferredTabAfterResult(data, source || \"analyze\"))" in INDEX
    assert 'consumeWorkflowStream(\n                "/analyze/stream"' in INDEX or (
        '"/analyze/stream"' in INDEX and "renderResult\n            )" in INDEX
    )
    assert 'id="estimateAiSummary"' in INDEX
    assert "Optional AI-assisted scenario" in INDEX
    assert "View full AI-assisted scenario" in INDEX
    assert 'id="panel-ai_optimization"' in INDEX
    assert 'data-print-artifact="ai_optimization"' in INDEX
    assert "panel.id === `panel-${name}`" in INDEX


def test_analyze_stream_still_uses_default_render_result():
    analyze_idx = INDEX.index("/analyze/stream")
    optimize_idx = INDEX.index("/optimize/stream")
    analyze_block = INDEX[analyze_idx:analyze_idx + 400]
    optimize_block = INDEX[optimize_idx:optimize_idx + 400]
    assert "renderResult" in analyze_block
    assert 'renderResult(payload, "optimize")' not in analyze_block
    assert 'renderResult(payload, "optimize")' in optimize_block


def test_optimize_result_contains_duration_range_and_artifact_text():
    data = _optimize(_analyze())
    assert data["ai_optimization"]["duration_range"]
    assert str(data["ai_optimization"]["duration_range"]).strip()
    assert data["artifact_texts"]["ai_optimization"].strip()


def test_ai_tab_available_only_after_optimization():
    before = _analyze()
    after = _optimize(before)
    assert not has_ai_optimization_result(before)
    assert not preferred_tab_after_result(before, "analyze") == "ai_optimization"
    assert "ai_optimization" not in (before.get("artifact_texts") or {})
    assert has_ai_optimization_result(after)
    assert has_ai_optimization_result({
        "ai_optimization": {"duration_range": after["ai_optimization"]["duration_range"]},
    })
    assert has_ai_optimization_result({
        "artifact_texts": {"ai_optimization": after["artifact_texts"]["ai_optimization"]},
    })
    assert preferred_tab_after_result(after, "optimize") == "ai_optimization"
    assert preferred_tab_after_result(after, "analyze") == "assessment"


def test_estimate_ui_labels_optional_ai_scenario_separately_from_baseline():
    assert "Optional AI-assisted scenario" in INDEX
    assert "Independent human-only baseline" in INDEX
    estimate_panel = INDEX.split('id="panel-estimate"', 1)[1].split('id="panel-ai_optimization"', 1)[0]
    assert "Optional AI-assisted scenario" in estimate_panel
    assert 'id="estimateAiSummary"' in estimate_panel
    assert "AI Delivery Optimization" in estimate_panel
    assert "never replaces the independent estimate" in estimate_panel


def test_optimize_keeps_baseline_estimate_independent():
    first = _analyze()
    baseline = first["estimate"]["duration_range"]
    baseline_text = first["artifact_texts"]["estimate"]
    data = _optimize(first)
    assert data["estimate"]["duration_range"] == baseline
    assert "OPTIONAL AI-ASSISTED SCENARIO" not in data["artifact_texts"]["estimate"]
    assert data["artifact_texts"]["estimate"] == baseline_text or "INDEPENDENT ESTIMATE" in data["artifact_texts"]["estimate"]
    assert "OPTIONAL AI-ASSISTED SCENARIO" in data["artifact_texts"]["ai_optimization"]
    assert data["ai_optimization"]["duration_range"] in data["artifact_texts"]["ai_optimization"]


def test_ai_print_target_is_ai_panel_not_estimate():
    assert 'id="panel-ai_optimization"' in INDEX
    assert "function printArtifact" in INDEX
    assert "panel.id === `panel-${name}`" in INDEX
    print_fn = INDEX.split("function printArtifact", 1)[1].split("function ", 1)[0]
    assert "panel-ai_optimization" in INDEX
    assert 'data-print-sheet="ai_optimization"' in INDEX
    assert 'data-print-sheet="estimate"' in INDEX
    assert "estimateContent" not in print_fn or "panel-${name}" in print_fn


def test_failed_optimize_does_not_select_ai_tab():
    failed = {"status": "ERROR", "estimate": {"duration_range": "12-16 weeks"}}
    assert preferred_tab_after_result(failed, "optimize") == "assessment"
    assert not has_ai_optimization_result(failed)
