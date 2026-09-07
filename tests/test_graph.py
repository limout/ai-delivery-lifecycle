from app.graph import build_graph
from app.providers import MockProvider


def test_delivery_graph_runs_end_to_end():
    graph = build_graph(MockProvider())

    result = graph.invoke(
        {
            "user_request": (
                "We want to build a customer self-service portal "
                "for enterprise clients."
            )
        }
    )

    assert result["user_request"].startswith(
        "We want to build a customer self-service portal"
    )
    assert "discovery" in result
    assert "requirements" in result
    assert result["discovery"]["unknowns"]
    assert result["requirements"]["open_questions"]


def test_requirements_receive_discovery_state():
    graph = build_graph(MockProvider())

    result = graph.invoke(
        {
            "user_request": "We need an AI support assistant."
        }
    )

    assert (
        result["requirements"]["open_questions"]
        == result["discovery"]["unknowns"]
    )