from app.providers import AIProvider
from app.state import DeliveryState


DISCOVERY_SCHEMA = {
    "type": "object",
    "properties": {
        "problem": {
            "type": "string",
            "description": "The business problem or need expressed by the customer.",
        },
        "business_goal": {
            "type": "string",
            "description": "The desired business outcome. Do not invent information.",
        },
        "users": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Known or explicitly mentioned target users.",
        },
        "stakeholders": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Known or explicitly mentioned stakeholders.",
        },
        "existing_systems": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Existing systems, platforms, or integrations explicitly mentioned.",
        },
        "constraints": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Known constraints explicitly mentioned by the customer.",
        },
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Reasonable assumptions. Clearly distinguish assumptions from facts.",
        },
        "unknowns": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Important information that is missing and needs clarification.",
        },
        "clarification_questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Questions that should be asked to clarify the discovery.",
        },
    },
    "required": [
        "problem",
        "business_goal",
        "users",
        "stakeholders",
        "existing_systems",
        "constraints",
        "assumptions",
        "unknowns",
        "clarification_questions",
    ],
}


def discovery_agent(
    state: DeliveryState,
    provider: AIProvider,
) -> dict:
    """
    AI Discovery Agent.

    The agent owns the discovery role.
    The provider owns the actual LLM interaction.
    """

    request = state["user_request"]

    prompt = f"""
You are a senior software delivery discovery consultant.

Your job is to analyze a customer's initial request and produce
a structured discovery assessment.

IMPORTANT RULES:

1. Separate facts from assumptions.
2. Never invent budget, timeline, users, systems, or business goals.
3. Identify missing information explicitly.
4. Generate useful clarification questions.
5. Think like a Delivery Lead preparing the project for requirements
   and later estimation.
6. The input may be vague, incomplete, or informal.

Customer request:

{request}
"""

    discovery = provider.generate_json(
        prompt=prompt,
        schema=DISCOVERY_SCHEMA,
    )

    return {"discovery": discovery}


def requirements_agent(state: DeliveryState) -> dict:
    """
    Second workflow node.

    Currently deterministic Python logic.
    It will become an AI Requirements Agent later.
    """

    discovery = state["discovery"]

    requirements = {
        "functional_requirements": [],
        "non_functional_requirements": [],
        "acceptance_criteria": [],
        "open_questions": discovery["unknowns"],
    }

    return {"requirements": requirements}