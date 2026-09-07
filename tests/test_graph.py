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
        "proposal",
        "sow",
    ):
        assert artifact in result
