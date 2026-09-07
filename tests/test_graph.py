from app.graph import build_graph
from app.providers import MockProvider


class ReadyMockProvider(MockProvider):
    """
    Mock provider that returns READY during validation.
    """

    def generate_json(self, prompt: str, schema: dict) -> dict:
        if "whether the project definition is" in prompt:
            return {
                "status": "READY",
                "reasons": [],
                "questions": [],
            }

        return super().generate_json(prompt, schema)


def test_delivery_graph_runs_to_needs_info():
    graph = build_graph(MockProvider())

    result = graph.invoke(
        {
            "user_request": (
                "We want to build a customer self-service portal."
            )
        }
    )

    assert "discovery" in result
    assert "requirements" in result
    assert "validation" in result

    assert result["validation"]["status"] == "NEEDS_INFO"
    assert result["iteration"] == 2


def test_delivery_graph_runs_to_ready():
    graph = build_graph(ReadyMockProvider())

    result = graph.invoke(
        {
            "user_request": (
                "We want to build a customer self-service portal."
            )
        }
    )

    assert result["validation"]["status"] == "READY"
    assert "iteration" not in result


def test_clarification_questions_are_available():
    graph = build_graph(MockProvider())

    result = graph.invoke(
        {
            "user_request": "We need an AI support assistant."
        }
    )

    assert result["validation"]["status"] == "NEEDS_INFO"
    assert result["validation"]["questions"]


def test_requirements_are_structured():
    graph = build_graph(ReadyMockProvider())

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