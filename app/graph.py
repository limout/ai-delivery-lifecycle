from functools import partial

from langgraph.graph import END, START, StateGraph

from app.agents import (
    clarification_agent,
    delivery_planning_agent,
    delivery_review_agent,
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
    """Route from validation based on the agent's decision."""
    validation = state.get("validation", {}) or {}
    blocking_questions = validation.get("blocking_questions", []) or []
    return "needs_info" if blocking_questions else "ready"


def route_after_delivery_review(state: DeliveryState) -> str:
    """Route from the delivery quality gate using explicit blocking semantics."""
    review = state.get("delivery_review", {}) or {}
    if review.get("status") == "READY" and not review.get("blocking_issues"):
        return "ready"

    clarification_questions = review.get("clarification_questions", []) or []
    if any(
        isinstance(question, dict) and question.get("blocks_workflow") is True
        for question in clarification_questions
    ):
        return "needs_info"

    return "review_blocked"


def build_graph(provider: AIProvider | None = None):
    """
    Build the agent graph.

    The graph is state-driven: agents produce structured state and
    conditional routers decide whether to continue, ask the customer,
    or stop on an internal delivery blocker.

    Human clarification is a graph boundary. The clarification node
    emits a WAITING_FOR_CUSTOMER state and ends that execution. The API
    starts the same graph again with the customer's answers; the graph
    then re-evaluates Discovery -> Requirements -> Validation. This is
    the lifecycle loop, not a second hard-coded workflow.
    """
    if provider is None:
        provider = GeminiProvider()

    graph = StateGraph(DeliveryState)

    graph.add_node("discovery", partial(discovery_agent, provider=provider))
    graph.add_node("requirements", partial(requirements_agent, provider=provider))
    graph.add_node("validation", partial(validation_agent, provider=provider))
    graph.add_node("clarification", clarification_agent)
    graph.add_node("solution", partial(solution_shaping_agent, provider=provider))
    graph.add_node("delivery_plan", partial(delivery_planning_agent, provider=provider))
    graph.add_node("estimate", partial(estimation_agent, provider=provider))
    graph.add_node("delivery_review", partial(delivery_review_agent, provider=provider))
    graph.add_node("proposal", partial(proposal_agent, provider=provider))
    graph.add_node("sow", partial(sow_agent, provider=provider))

    graph.add_node("await_customer", lambda state: {
        "workflow_status": "NEEDS_INFO",
        "current_stage": "clarification",
        "awaiting_customer": True,
    })
    graph.add_node("blocked", lambda state: {
        "workflow_status": "BLOCKED",
        "current_stage": "delivery_review",
        "awaiting_customer": False,
    })
    graph.add_node("complete", lambda state: {
        "workflow_status": "COMPLETE",
        "current_stage": "complete",
        "awaiting_customer": False,
    })

    graph.add_edge(START, "discovery")
    graph.add_edge("discovery", "requirements")
    graph.add_edge("requirements", "validation")

    graph.add_conditional_edges(
        "validation",
        route_after_validation,
        {
            "ready": "solution",
            "needs_info": "clarification",
        },
    )

    # Human-in-the-loop boundary. The next /clarify request re-enters
    # the graph at START with customer answers in state.
    graph.add_edge("clarification", "await_customer")
    graph.add_edge("await_customer", END)

    graph.add_edge("solution", "delivery_plan")
    graph.add_edge("delivery_plan", "estimate")
    graph.add_edge("estimate", "delivery_review")

    graph.add_conditional_edges(
        "delivery_review",
        route_after_delivery_review,
        {
            "ready": "proposal",
            "needs_info": "clarification",
            "review_blocked": "blocked",
        },
    )

    graph.add_edge("proposal", "sow")
    graph.add_edge("sow", "complete")
    graph.add_edge("blocked", END)
    graph.add_edge("complete", END)

    return graph.compile()
