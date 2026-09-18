from fastapi.testclient import TestClient

from app.main import app
from app.api import get_provider
from app.providers import AIProvider, AIProviderQuotaError, MockProvider


app.dependency_overrides[get_provider] = MockProvider
client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_needs_info_has_structured_questions():
    response = client.post(
        "/analyze",
        json={"user_request": "We want to build a customer self-service portal."},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "NEEDS_INFO"
    assert data["awaiting_customer"] is True
    assert isinstance(data["blocking_questions"], list)

    for item in data["clarification_questions"]:
        assert set(item) >= {
            "question",
            "priority",
            "reason",
            "blocks_workflow",
        }
        assert item["priority"] in {"REQUIRED", "RECOMMENDED", "OPTIONAL"}
        assert isinstance(item["blocks_workflow"], bool)

    assert all(
        item["blocks_workflow"] is True
        for item in data["blocking_questions"]
    )


def test_analyze_rejects_empty_request():
    response = client.post("/analyze", json={"user_request": ""})
    assert response.status_code == 422


def test_clarify_accepts_structured_answers_and_increments_iteration():
    response = client.post(
        "/clarify",
        json={
            "user_request": "We want to build a customer self-service portal.",
            "answers": [
                {
                    "question": "Which identity provider is required?",
                    "answer": "Microsoft Entra ID",
                }
            ],
            "iteration": 1,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["iteration"] == 2
    assert data["clarification_history"] == [
        {
            "question": "Which identity provider is required?",
            "answer": "Microsoft Entra ID",
        }
    ]
    assert data["discovery"]
    assert data["requirements"]
    assert data["validation"]


class QuotaMockProvider(AIProvider):
    def generate_json(self, prompt: str, schema: dict) -> dict:
        raise AIProviderQuotaError("AI provider quota has been exceeded.")


def test_analyze_returns_503_when_ai_quota_is_exceeded():
    app.dependency_overrides[get_provider] = QuotaMockProvider

    response = client.post(
        "/analyze",
        json={"user_request": "We want to build a customer self-service portal."},
    )

    assert response.status_code == 503
    assert response.json()["error"] == "AI_PROVIDER_QUOTA_EXCEEDED"

    app.dependency_overrides[get_provider] = MockProvider


from urllib.parse import parse_qs


def resolve_client_name(search: str) -> str:
    """Mirrors resolveClientName() in app/static/index.html."""
    query = search[1:] if search.startswith("?") else search
    values = parse_qs(query, keep_blank_values=True).get("client")
    if not values:
        return "LIMOUT"
    name = values[0].strip()
    if not name or "<" in name or ">" in name:
        return "LIMOUT"
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        return "LIMOUT"
    return name


def test_client_branding_query_param():
    assert resolve_client_name("") == "LIMOUT"
    assert resolve_client_name("?client=AMDARIS") == "AMDARIS"
    assert resolve_client_name("?client=Insight") == "Insight"
    assert resolve_client_name("?client=Some%20Company") == "Some Company"
    assert resolve_client_name("?client=") == "LIMOUT"
    assert resolve_client_name("?client=%20") == "LIMOUT"
    assert resolve_client_name("?client=Bad<script>") == "LIMOUT"
    assert resolve_client_name("?client=ok>no") == "LIMOUT"


def test_home_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "AI Delivery Copilot" in response.text
    assert "before you commit to a date" in response.text
    assert "Tell the Copilot what needs to be delivered" in response.text
    assert 'class="app-shell"' in response.text
    assert "data-client-name" in response.text
    assert "function resolveClientName" in response.text
    assert 'id="optimizeButton"' not in response.text
    assert "Delivery request" in response.text
    assert "validation.blocking_questions" in response.text
    assert "validation.blockers" not in response.text
    assert "Indicative estimate" in response.text
    assert "statusClassFor" in response.text
    assert "COMPLETE" in response.text
    assert 'data-tab="assessment"' in response.text
    assert 'data-tab="discovery"' in response.text
    assert 'data-tab="estimate"' in response.text
    assert 'data-tab="requirements"' in response.text
    assert 'data-tab="validation"' in response.text
    assert 'data-tab="solution"' in response.text
    assert 'data-tab="delivery_plan"' in response.text
    assert 'data-tab="delivery_review"' in response.text
    assert 'data-tab="proposal"' in response.text
    assert 'data-tab="sow"' in response.text
    assert 'id="questions"' in response.text
    assert 'id="verdictNext"' in response.text
    assert 'id="optimizeButtonPanel"' in response.text
    sidebar = response.text.split('class="app-sidebar', 1)[1].split('class="app-main"', 1)[0]
    assert 'id="artifactTabs"' in sidebar
    assert "Analysis" in sidebar
    assert "Evidence" in sidebar
    assert "Outputs" in sidebar
    result_html = response.text.split('id="result"', 1)[1].split("<script>", 1)[0]
    assert 'id="artifactTabs"' not in result_html
    assert ">Workspaces<" not in response.text
    for panel in (
        "assessment", "discovery", "requirements", "validation", "solution",
        "delivery_plan", "estimate", "delivery_review", "proposal", "sow",
    ):
        assert f'id="panel-{panel}"' in response.text
        assert f'data-tab="{panel}"' in sidebar
    estimate_panel = response.text.split('id="panel-estimate"', 1)[1]
    next_panel = estimate_panel.find('id="panel-')
    estimate_panel = estimate_panel if next_panel < 0 else estimate_panel[:next_panel]
    assert 'id="optimizeButtonPanel"' in estimate_panel
    assert 'id="gapCloseSection"' in estimate_panel
    assert 'data-tab="ai_optimization"' not in response.text
    assert 'data-tab="deadline_gap"' not in response.text
    assert "Additional questions — useful later" in response.text
    assert "printAssessment" in response.text
