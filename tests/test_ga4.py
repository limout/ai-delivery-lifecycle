"""GA4 frontend tracking: analyze_started / analyze_completed only."""

from pathlib import Path
from urllib.parse import parse_qs

from fastapi.testclient import TestClient

from app.main import app
from tests.test_api import resolve_client_name


INDEX = Path("app/static/index.html").read_text(encoding="utf-8")
GA4 = Path("app/static/ga4.js").read_text(encoding="utf-8")
client = TestClient(app)

FORBIDDEN_PAYLOAD_MARKERS = (
    "user_request",
    "location.href",
    "document.cookie",
)


def analytics_client_params(search: str) -> dict:
    """Mirrors DeliveryAnalytics.analyticsClientParams() in app/static/ga4.js."""
    query = search[1:] if search.startswith("?") else search
    values = parse_qs(query, keep_blank_values=True).get("client")
    if not values or not values[0].strip():
        return {}
    return {"client": resolve_client_name(search)}


def _analyze_function_source() -> str:
    return INDEX.split("async function analyze()", 1)[1].split(
        "async function clarify()", 1
    )[0]


def test_ga4_measurement_id_is_configured_once():
    assert GA4.count("G-2ZHCXEWVMY") == 1
    assert "G-2ZHCXEWVMY" not in INDEX
    assert "15829444650" in GA4
    assert INDEX.count("/static/ga4.js") == 1


def test_ga4_script_is_served():
    response = client.get("/static/ga4.js")
    assert response.status_code == 200
    assert "G-2ZHCXEWVMY" in response.text
    assert "analyze_started" in response.text
    assert "analyze_completed" in response.text


def test_analyze_started_fires_at_actual_analyze_start():
    source = _analyze_function_source()
    before_try, after_try = source.split("try {", 1)
    assert "Please enter a customer request." in before_try
    assert "trackAnalyzeStarted" in before_try
    assert "consumeWorkflowStream" in after_try
    assert source.index("trackAnalyzeStarted") < source.index("consumeWorkflowStream")
    assert "trackAnalyzeStarted" not in INDEX.split("async function clarify()", 1)[1]


def test_analyze_completed_fires_only_after_successful_analyze():
    source = _analyze_function_source()
    _before, rest = source.split("try {", 1)
    success_block, catch_block = rest.split("} catch (error)", 1)
    assert "trackAnalyzeCompleted" in success_block
    assert success_block.index("consumeWorkflowStream") < success_block.index(
        "trackAnalyzeCompleted"
    )
    assert "trackAnalyzeCompleted" not in catch_block
    assert "trackAnalyzeCompleted" not in _before


def test_analytics_includes_resolved_client_when_present():
    assert analytics_client_params("?client=AMDARIS") == {"client": "AMDARIS"}
    assert analytics_client_params("?client=Insight") == {"client": "Insight"}
    assert "resolveClientName" in GA4
    assert "params.client = window.resolveClientName" in GA4


def test_analytics_omits_client_when_absent():
    assert analytics_client_params("") == {}
    assert analytics_client_params("?client=") == {}
    assert analytics_client_params("?client=%20") == {}
    assert 'new URLSearchParams(query).get("client")' in GA4
    assert "!String(raw).trim()" in GA4


def test_analytics_does_not_send_request_or_analysis_content():
    for marker in FORBIDDEN_PAYLOAD_MARKERS:
        assert marker not in GA4
    source = _analyze_function_source()
    assert "trackAnalyzeStarted();" in source
    assert "trackAnalyzeCompleted();" in source
    assert "trackAnalyzeStarted(request" not in source
    assert "trackAnalyzeCompleted(request" not in source
    assert "trackAnalyzeCompleted(data" not in source
    assert 'gtag("event", eventName, analyticsClientParams())' in GA4
