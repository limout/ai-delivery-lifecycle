from app.graph import build_graph
from app.providers import MockProvider


class ReadyMockProvider(MockProvider):
    def generate_json(self, prompt: str, schema: dict) -> dict:
        if "whether the project definition is" in prompt:
            return {
                "status": "READY",
                "reasons": [],
                "questions": [],
            }

        return super().generate_json(prompt, schema)


class ClarificationAwareMockProvider(MockProvider):
    def generate_json(self, prompt: str, schema: dict) -> dict:
        if "requirements definition" in prompt:
            if "Salesforce" in prompt:
                return {
                    "functional_requirements": [
                        "The portal must integrate with Salesforce."
                    ],
                    "non_functional_requirements": [],
                    "acceptance_criteria": [
                        "The portal can exchange data with Salesforce."
                    ],
                    "open_questions": [],
                    "contradictions": [],
                }

        if "whether the project definition is" in prompt:
            if "Salesforce" in prompt:
                return {
                    "status": "READY",
                    "reasons": [
                        "Customer provided the previously missing "
                        "integration information."
                    ],
                    "questions": [],
                }

            return {
                "status": "NEEDS_INFO",
                "reasons": [
                    "The target delivery timeline is not known."
                ],
                "questions": [
                    "What is the target delivery timeline?"
                ],
            }

        if "discovery assessment" in prompt:
            if "Salesforce" in prompt:
                return {
                    "problem": (
                        "Customer needs a software solution."
                    ),
                    "business_goal": (
                        "Solve the customer's business need."
                    ),
                    "users": [],
                    "stakeholders": [],
                    "existing_systems": [
                        "Salesforce"
                    ],
                    "constraints": [],
                    "assumptions": [],
                    "unknowns": [],
                    "clarification_questions": [],
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
    assert result["clarification_questions"]


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


def test_clarification_answers_restart_the_workflow():
    graph = build_graph(ClarificationAwareMockProvider())

    first_result = graph.invoke(
        {
            "user_request": (
                "We want to build a customer self-service portal."
            )
        }
    )

    assert first_result["validation"]["status"] == "NEEDS_INFO"
    assert first_result["clarification_questions"]

    second_result = graph.invoke(
        {
            "user_request": (
                "We want to build a customer self-service portal."
            ),
            "clarification_answers": [
                "The portal must integrate with Salesforce."
            ],
            "iteration": first_result["iteration"],
        }
    )

    assert second_result["validation"]["status"] == "READY"
    assert second_result["iteration"] == 2