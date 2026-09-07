from app.graph import build_graph
from app.providers import MockProvider


class RoutingMockProvider(MockProvider):
    """
    Mock provider that can return a chosen validation status.
    """

    def __init__(self, validation_status: str):
        self.validation_status = validation_status

    def generate_json(self, prompt: str, schema: dict) -> dict:
        if "whether the project definition is" in prompt:
            return {
                "status": self.validation_status,
                "reasons": [
                    "Mock validation result for deterministic testing."
                ],
                "questions": (
                    []
                    if self.validation_status == "READY"
                    else ["What is the target delivery timeline?"]
                ),
            }

        return super().generate_json(prompt, schema)


def test_delivery_graph_runs_end_to_end():
    graph = build_graph(RoutingMockProvider("READY"))

    result = graph.invoke(
        {
            "user_request": (
                "We want to build a customer self-service portal "
                "for enterprise clients."
            )
        }
    )

    assert "discovery" in result
    assert "requirements" in result
    assert "validation" in result

    assert result["validation"]["status"] == "READY"


def test_ready_route_reaches_end():
    graph = build_graph(RoutingMockProvider("READY"))

    result = graph.invoke(
        {
            "user_request": "We need an AI support assistant."
        }
    )

    assert result["validation"]["status"] == "READY"


def test_needs_info_route_reaches_end():
    graph = build_graph(RoutingMockProvider("NEEDS_INFO"))

    result = graph.invoke(
        {
            "user_request": "We need an AI support assistant."
        }
    )

    assert result["validation"]["status"] == "NEEDS_INFO"
    assert result["validation"]["questions"]