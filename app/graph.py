from functools import partial

from langgraph.graph import END, START, StateGraph

from app.agents import discovery_agent, requirements_agent
from app.providers import AIProvider, GeminiProvider
from app.state import DeliveryState


def build_graph(provider: AIProvider | None = None):
    """
    Build the delivery lifecycle graph.

    If no provider is supplied, Gemini is used.
    Tests can inject MockProvider.
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

    graph.add_edge(START, "discovery")
    graph.add_edge("discovery", "requirements")
    graph.add_edge("requirements", END)

    return graph.compile()