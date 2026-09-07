from typing import TypedDict


class DeliveryState(TypedDict, total=False):
    user_request: str
    clarification_answers: list[str]
    clarification_questions: list[str]
    discovery: dict
    requirements: dict
    validation: dict
    solution: dict
    delivery_plan: dict
    estimate: dict
    delivery_review: dict
    proposal: dict
    sow: dict
    iteration: int
