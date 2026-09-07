from typing import TypedDict


class DeliveryState(TypedDict, total=False):
    user_request: str
    clarification_answers: list[str]
    clarification_questions: list[dict]
    blocking_questions: list[dict]
    non_blocking_questions: list[dict]
    clarification_history: list[dict]
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
    current_stage: str
    workflow_status: str
    awaiting_customer: bool
