from typing import TypedDict


class DeliveryState(TypedDict, total=False):
    """
    Shared state passed through the delivery lifecycle graph.
    """

    user_request: str
    discovery: dict
    requirements: dict