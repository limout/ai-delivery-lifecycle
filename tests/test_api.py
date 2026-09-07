from fastapi.testclient import TestClient

from app.api import app, get_provider
from app.providers import MockProvider


app.dependency_overrides[get_provider] = MockProvider

client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
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