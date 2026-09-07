from app.graph import build_graph
from app.providers import MockProvider


CUSTOMER_REQUEST = (
    "We want to build a customer self-service portal "
    "for enterprise clients."
)


def test_graph_stops_for_blocking_missing_timeline():
    graph = build_graph(provider=MockProvider())

    result = graph.invoke({"user_request": CUSTOMER_REQUEST})

    assert result["validation"]["status"] == "NEEDS_INFO"
    assert result["validation"]["questions"] == [
        "What is the target delivery timeline?"
    ]
    assert result["validation"]["non_blocking_questions"] == []
    assert "clarification_questions" in result
    assert result["solution"] if "solution" in result else True


def test_graph_reaches_solution_after_timeline_clarification():
    graph = build_graph(provider=MockProvider())

    result = graph.invoke(
        {
            "user_request": CUSTOMER_REQUEST,
            "clarification_answers": [
                "The target delivery timeline is 2 months."
            ],
            "iteration": 2,
        }
    )

    assert result["validation"]["status"] == "READY"
    assert result["validation"]["questions"] == []
    assert result["validation"]["non_blocking_questions"]

    assert "solution" in result
    assert "delivery_plan" in result
    assert "estimate" in result
    assert "delivery_review" in result
    assert result["delivery_review"]["status"] == "READY"
    assert "proposal" in result
    assert "sow" in result


def test_complete_project_does_not_stop_for_non_blocking_questions():
    request = (
        "We want to build a customer self-service portal for enterprise "
        "customers. Customers should be able to view account information, "
        "submit and track support requests, and access documentation. "
        "We currently use Salesforce. Enterprise users authenticate through "
        "Microsoft Entra ID. We want to launch within two months."
    )

    graph = build_graph(provider=MockProvider())
    result = graph.invoke({"user_request": request})

    assert result["validation"]["status"] == "READY"
    assert result["validation"]["questions"] == []
    assert result["validation"]["non_blocking_questions"]
    assert result.get("iteration") is None

    for artifact in (
        "discovery",
        "requirements",
        "validation",
        "solution",
        "delivery_plan",
        "estimate",
        "delivery_review",
        "proposal",
        "sow",
    ):
        assert artifact in result

class ReviewBlockingProvider(MockProvider):
    def generate_json(self, prompt: str, schema: dict) -> dict:
        if "blocking_issues" in schema.get("properties", {}):
            return {
                "status": "BLOCKED",
                "blocking_issues": ["The preliminary estimate conflicts with the requested timeline."],
                "warnings": [],
                "checks": ["Cross-agent consistency check failed."],
            }
        return super().generate_json(prompt, schema)


def test_graph_stops_before_proposal_when_delivery_review_is_blocked():
    graph = build_graph(provider=ReviewBlockingProvider())

    result = graph.invoke({
        "user_request": (
            "We want to build a customer self-service portal for enterprise customers. "
            "We currently use Salesforce and want to launch within two months."
        )
    })

    assert result["delivery_review"]["status"] == "BLOCKED"
    assert result["delivery_review"]["blocking_issues"]
    assert "proposal" not in result
    assert "sow" not in result



class DeterministicConflictProvider(MockProvider):
    def generate_json(self, prompt: str, schema: dict) -> dict:
        properties = set(schema.get("properties", {}))
        if "functional_requirements" in properties:
            return {
                "functional_requirements": [
                    "The portal must provide customer self-service."
                ],
                "non_functional_requirements": [
                    "The portal must provide 99.9% uptime."
                ],
                "acceptance_criteria": [
                    "The portal achieves 99.9% uptime."
                ],
                "open_questions": [],
                "contradictions": [],
            }
        if "effort_range" in properties:
            return {
                "effort_range": "Indicative: 400-600 person-days",
                "duration_range": "Indicative: 12-16 weeks",
                "confidence": "MEDIUM",
                "assumptions": [],
                "risks_affecting_estimate": [],
            }
        return super().generate_json(prompt, schema)


def test_delivery_review_deterministically_blocks_deadline_and_ungrounded_commitment():
    graph = build_graph(provider=DeterministicConflictProvider())

    result = graph.invoke({
        "user_request": (
            "We want to build a customer self-service portal for enterprise customers. "
            "We want to launch within two months."
        )
    })

    assert result["delivery_review"]["status"] == "BLOCKED"
    assert any("deadline" in issue.lower() for issue in result["delivery_review"]["blocking_issues"])
    assert any("99.9%" in issue for issue in result["delivery_review"]["blocking_issues"])
    assert "proposal" not in result
    assert "sow" not in result
