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


def test_home_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "AI Delivery Lifecycle" in response.text
    assert "Customer Request" in response.text
