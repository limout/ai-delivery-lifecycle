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
    assert result["discovery"]["clarification_questions"]

    assert result["requirements"]["functional_requirements"]
    assert result["requirements"]["non_functional_requirements"]
    assert result["requirements"]["acceptance_criteria"]


def test_requirements_receive_discovery_state():
    graph = build_graph(MockProvider())

    result = graph.invoke(
        {
            "user_request": "We need an AI support assistant."
        }
    )

    assert result["requirements"]["open_questions"]


def test_requirements_have_structured_output():
    graph = build_graph(MockProvider())

    result = graph.invoke(
        {
            "user_request": "We need an AI support assistant."
        }
    )

    requirements = result["requirements"]

    assert "functional_requirements" in requirements
    assert "non_functional_requirements" in requirements
    assert "acceptance_criteria" in requirements
    assert "open_questions" in requirements
    assert "contradictions" in requirements