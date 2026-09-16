from functools import partial
from typing import Callable

from langgraph.graph import END, START, StateGraph

from app.agents import (
    clarification_agent,
    delivery_planning_agent,
    delivery_review_agent,
    discovery_agent,
    estimation_agent,
    ai_optimization_agent,
    proposal_agent,
    requirements_agent,
    solution_shaping_agent,
    sow_agent,
    validation_agent,
)
from app.providers import AIProvider, GeminiProvider
from app.resume import apply_clarification_facts, route_after_start
from app.state import DeliveryState


ProgressCallback = Callable[[str, str], None]


def route_after_validation(state: DeliveryState) -> str:
    """Route from validation based on the agent's decision."""
    validation = state.get("validation", {}) or {}
    blocking_questions = validation.get("blocking_questions", []) or []
    return "needs_info" if blocking_questions else "ready"


def route_after_delivery_review(state: DeliveryState) -> str:
    """Route the final delivery gate without reopening customer clarification.

    Validation owns the customer-question boundary. Delivery Review is a
    deterministic delivery gate: if it has a blocker, the workflow stops as
    BLOCKED; if it has no blocker, the workflow continues to Proposal. LLM
    questions and advisory diagnostics must never create a new clarification
    loop here.
    """
    review = state.get("delivery_review", {}) or {}
    blocking_issues = review.get("blocking_issues", []) or []

    if not blocking_issues and review.get("status") == "READY":
        return "ready"

    return "review_blocked"


def _wrap_node(
    name: str,
    node: Callable[[DeliveryState], dict],
    progress_callback: ProgressCallback | None,
):
    """Wrap a graph node so the API can expose start/end progress events."""

    def wrapped(state: DeliveryState) -> dict:
        if progress_callback:
            progress_callback(name, "running")
        try:
            result = node(state)
        except Exception:
            if progress_callback:
                progress_callback(name, "error")
            raise
        if progress_callback:
            progress_callback(name, "complete")
        return result

    return wrapped



def build_optimization_graph(
    provider: AIProvider | None = None,
    progress_callback: ProgressCallback | None = None,
):
    """Build the explicit user-triggered AI delivery optimization graph."""
    if provider is None:
        provider = GeminiProvider()

    graph = StateGraph(DeliveryState)
    graph.add_node(
        "ai_optimization",
        _wrap_node(
            "ai_optimization",
            partial(ai_optimization_agent, provider=provider),
            progress_callback,
        ),
    )
    graph.add_node(
        "optimization_complete",
        _wrap_node(
            "optimization_complete",
            lambda state: {
                "workflow_status": "COMPLETE",
                "current_stage": "ai_optimization",
                "awaiting_customer": False,
            },
            progress_callback,
        ),
    )
    graph.add_edge(START, "ai_optimization")
    graph.add_edge("ai_optimization", "optimization_complete")
    graph.add_edge("optimization_complete", END)
    return graph.compile()


def build_gap_close_graph(
    provider: AIProvider | None = None,
    progress_callback: ProgressCallback | None = None,
):
    """Build the explicit user-triggered hard-deadline gap-closing graph."""
    from app.gap_close import deadline_gap_plan_agent

    if provider is None:
        provider = GeminiProvider()

    graph = StateGraph(DeliveryState)
    graph.add_node(
        "deadline_gap_plan",
        _wrap_node(
            "deadline_gap_plan",
            partial(deadline_gap_plan_agent, provider=provider),
            progress_callback,
        ),
    )
    graph.add_node(
        "gap_close_complete",
        _wrap_node(
            "gap_close_complete",
            lambda state: {
                "workflow_status": "COMPLETE",
                "current_stage": "deadline_gap_plan",
                "awaiting_customer": False,
            },
            progress_callback,
        ),
    )
    graph.add_edge(START, "deadline_gap_plan")
    graph.add_edge("deadline_gap_plan", "gap_close_complete")
    graph.add_edge("gap_close_complete", END)
    return graph.compile()

def build_graph(
    provider: AIProvider | None = None,
    progress_callback: ProgressCallback | None = None,
):
    """
    Build the agent graph.

    The graph is state-driven: agents produce structured state and
    conditional routers decide whether to continue, ask the customer,
    or stop on an internal delivery blocker.

    When progress_callback is provided, every graph node reports a
    running/complete/error lifecycle event. This is used by the API's
    streaming endpoint to show the current module while the workflow runs.

    Human clarification is a graph boundary. The clarification node
    emits a WAITING_FOR_CUSTOMER state and ends that execution. The API
    resumes the same graph with the customer's answers. When the answers
    only resolve unknowns or metadata (for example timeline), Discovery
    and Requirements are preserved and Validation continues. When answers
    materially change scope, Discovery and Requirements are regenerated.
    """
    if provider is None:
        provider = GeminiProvider()

    graph = StateGraph(DeliveryState)

    graph.add_node(
        "apply_clarification",
        _wrap_node("apply_clarification", apply_clarification_facts, progress_callback),
    )
    graph.add_node(
        "discovery",
        _wrap_node(
            "discovery",
            partial(discovery_agent, provider=provider),
            progress_callback,
        ),
    )
    graph.add_node(
        "requirements",
        _wrap_node(
            "requirements",
            partial(requirements_agent, provider=provider),
            progress_callback,
        ),
    )
    graph.add_node(
        "validation",
        _wrap_node(
            "validation",
            partial(validation_agent, provider=provider),
            progress_callback,
        ),
    )
    graph.add_node(
        "clarification",
        _wrap_node("clarification", clarification_agent, progress_callback),
    )
    graph.add_node(
        "solution",
        _wrap_node(
            "solution",
            partial(solution_shaping_agent, provider=provider),
            progress_callback,
        ),
    )
    graph.add_node(
        "delivery_plan",
        _wrap_node(
            "delivery_plan",
            partial(delivery_planning_agent, provider=provider),
            progress_callback,
        ),
    )
    graph.add_node(
        "estimate",
        _wrap_node(
            "estimate",
            partial(estimation_agent, provider=provider),
            progress_callback,
        ),
    )
    graph.add_node(
        "delivery_review",
        _wrap_node(
            "delivery_review",
            partial(delivery_review_agent, provider=provider),
            progress_callback,
        ),
    )
    graph.add_node(
        "proposal",
        _wrap_node(
            "proposal",
            partial(proposal_agent, provider=provider),
            progress_callback,
        ),
    )
    graph.add_node(
        "sow",
        _wrap_node(
            "sow",
            partial(sow_agent, provider=provider),
            progress_callback,
        ),
    )

    graph.add_node(
        "await_customer",
        _wrap_node(
            "await_customer",
            lambda state: {
                "workflow_status": "NEEDS_INFO",
                "current_stage": "clarification",
                "awaiting_customer": True,
            },
            progress_callback,
        ),
    )
    graph.add_node(
        "blocked",
        _wrap_node(
            "blocked",
            lambda state: {
                "workflow_status": "BLOCKED",
                "current_stage": "delivery_review",
                "awaiting_customer": False,
            },
            progress_callback,
        ),
    )
    graph.add_node(
        "complete",
        _wrap_node(
            "complete",
            lambda state: {
                "workflow_status": "COMPLETE",
                "current_stage": "complete",
                "awaiting_customer": False,
            },
            progress_callback,
        ),
    )

    graph.add_conditional_edges(
        START,
        route_after_start,
        {
            "discovery": "discovery",
            "apply_clarification": "apply_clarification",
        },
    )
    graph.add_edge("apply_clarification", "validation")
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

    # Human-in-the-loop boundary. The next /clarify request resumes
    # with stored upstream artifacts unless scope has changed.
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
            "review_blocked": "blocked",
        },
    )

    graph.add_edge("proposal", "sow")
    graph.add_edge("sow", "complete")
    graph.add_edge("blocked", END)
    graph.add_edge("complete", END)

    return graph.compile()
