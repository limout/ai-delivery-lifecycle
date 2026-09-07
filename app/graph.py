from functools import partial

from langgraph.graph import END, START, StateGraph

from app.agents import (
    clarification_agent,
    delivery_planning_agent,
    discovery_agent,
    estimation_agent,
    proposal_agent,
    requirements_agent,
    solution_shaping_agent,
    sow_agent,
    validation_agent,
)
from app.providers import AIProvider, GeminiProvider
from app.state import DeliveryState


def route_after_validation(state: DeliveryState) -> str:
    status = state["validation"]["status"]

    if status == "READY":
        return "ready"

    return "needs_info"


def build_graph(provider: AIProvider | None = None):

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
        "solution",
        partial(solution_shaping_agent, provider=provider),
    )

    graph.add_node(
        "delivery_plan",
        partial(delivery_planning_agent, provider=provider),
    )

    graph.add_node(
        "estimate",
        partial(estimation_agent, provider=provider),
    )

    graph.add_node(
        "proposal",
        partial(proposal_agent, provider=provider),
    )

    graph.add_node(
        "sow",
        partial(sow_agent, provider=provider),
    )

    graph.add_node(
        "ready",
        lambda state: {},
    )

    graph.add_node(
        "needs_info",
        lambda state: {},
    )

    graph.add_node(
        "complete",
        lambda state: {},
    )

    graph.add_edge(START, "discovery")

    graph.add_edge(
        "discovery",
        "requirements",
    )

    graph.add_edge(
        "requirements",
        "validation",
    )

    graph.add_conditional_edges(
        "validation",
        route_after_validation,
        {
            "ready": "ready",
            "needs_info": "clarification",
        },
    )

    graph.add_edge(
        "clarification",
        "needs_info",
    )

    graph.add_edge(
        "ready",
        "solution",
    )

    graph.add_edge(
        "solution",
        "delivery_plan",
    )

    graph.add_edge(
        "delivery_plan",
        "estimate",
    )

    graph.add_edge(
        "estimate",
        "proposal",
    )

    graph.add_edge(
        "proposal",
        "sow",
    )

    graph.add_edge(
        "sow",
        "complete",
    )

    graph.add_edge(
        "needs_info",
        END,
    )

    graph.add_edge(
        "complete",
        END,
    )

    return graph.compile()