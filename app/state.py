from typing import TypedDict


class DeliveryState(TypedDict, total=False):
    """
    Shared state passed through the delivery lifecycle graph.
    """

    user_request: str

    clarification_answers: list[str]
    clarification_questions: list[str]

    discovery: dict
    requirements: dict
    validation: dict

    iteration: int