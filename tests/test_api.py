from fastapi.testclient import TestClient

from app.main import app
from app.api import get_provider
from app.providers import (
    AIProvider,
    AIProviderQuotaError,
    MockProvider,
)


app.dependency_overrides[get_provider] = MockProvider

client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
    }


def test_config_returns_mock_provider(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")

    response = client.get("/config")

    assert response.status_code == 200
    assert response.json() == {
        "ai_provider": "mock",
    }


def test_analyze_needs_info():
    response = client.post(
        "/analyze",
        json={
            "user_request": (
                "We want to build a customer self-service portal."
            )
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "NEEDS_INFO"
    assert data["discovery"]
    assert data["requirements"]
    assert data["validation"]
    assert data["clarification_questions"]


def test_analyze_rejects_empty_request():
    response = client.post(
        "/analyze",
        json={
            "user_request": "",
        },
    )

    assert response.status_code == 422


def test_clarify_accepts_customer_answers():
    response = client.post(
        "/clarify",
        json={
            "user_request": (
                "We want to build a customer self-service portal."
            ),
            "clarification_answers": [
                "The portal must integrate with Salesforce.",
            ],
            "iteration": 2,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] in {
        "READY",
        "NEEDS_INFO",
    }

    assert data["discovery"]
    assert data["requirements"]
    assert data["validation"]


class QuotaMockProvider(AIProvider):
    def generate_json(self, prompt: str, schema: dict) -> dict:
        raise AIProviderQuotaError(
            "AI provider quota has been exceeded."
        )


def test_analyze_returns_503_when_ai_quota_is_exceeded():
    app.dependency_overrides[get_provider] = QuotaMockProvider

    response = client.post(
        "/analyze",
        json={
            "user_request": (
                "We want to build a customer self-service portal."
            )
        },
    )

    assert response.status_code == 503

    data = response.json()

    assert data["error"] == "AI_PROVIDER_QUOTA_EXCEEDED"

    app.dependency_overrides[get_provider] = MockProvider


def test_mock_provider_is_selected_from_environment(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")

    provider = get_provider()

    assert isinstance(provider, MockProvider)


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "unknown")

    try:
        get_provider()
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "Unsupported AI_PROVIDER" in str(exc)


def test_home_page():
    response = client.get("/")

    assert response.status_code == 200
    assert "AI Delivery Lifecycle" in response.text
    assert "Customer Request" in response.text

def test_analyze_returns_full_lifecycle_artifacts():
    response = client.post(
        "/analyze",
        json={
            "user_request": (
                "We want to build a customer self-service portal for enterprise customers. "
                "We currently use Salesforce. Enterprise users authenticate through Microsoft Entra ID. "
                "We want to launch within two months."
            )
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "READY"
    assert data["solution"]
    assert data["delivery_plan"]
    assert data["estimate"]
    assert data["delivery_review"]
    assert data["proposal"]
    assert data["sow"]

