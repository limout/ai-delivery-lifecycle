from functools import partial

from langgraph.graph import END, START, StateGraph

from app.agents import (
    clarification_agent,
    discovery_agent,
    requirements_agent,
    validation_agent,
)
from app.providers import AIProvider, GeminiProvider
from app.state import DeliveryState


def route_after_validation(state: DeliveryState) -> str:
    """
    Decide where the workflow should go after validation.
    """

    status = state["validation"]["status"]

    if status == "READY":
        return "ready"

    return "needs_info"


def build_graph(provider: AIProvider | None = None):
    """
    Build the delivery lifecycle graph.
    """

    if provider is None:
        provider = GeminiProvider()

    graph = StateGraph(DeliveryState)

    graph.add_node(
        "discovery",
        partial(discovery_agent, provider=provider),
    )

    graph.add_node(
        "requirements",
        partial(requirements_agent, provider=provider),
    )

    graph.add_node(
        "validation",
        partial(validation_agent, provider=provider),
    )

    graph.add_node(
        "clarification",
        clarification_agent,
    )

    graph.add_node(
        "ready",
        lambda state: {},
    )

    graph.add_edge(START, "discovery")
    graph.add_edge("discovery", "requirements")
    graph.add_edge("requirements", "validation")

    graph.add_conditional_edges(
        "validation",
        route_after_validation,
        {
            "ready": "ready",
            "needs_info": "clarification",
        },
    )

    graph.add_edge("ready", END)
    graph.add_edge("clarification", END)

    return graph.compile()