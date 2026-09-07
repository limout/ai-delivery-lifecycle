from app.providers import AIProvider
from app.state import DeliveryState


DISCOVERY_SCHEMA = {
    "type": "object",
    "properties": {
        "problem": {"type": "string"},
        "business_goal": {"type": "string"},
        "users": {
            "type": "array",
            "items": {"type": "string"},
        },
        "stakeholders": {
            "type": "array",
            "items": {"type": "string"},
        },
        "existing_systems": {
            "type": "array",
            "items": {"type": "string"},
        },
        "constraints": {
            "type": "array",
            "items": {"type": "string"},
        },
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "unknowns": {
            "type": "array",
            "items": {"type": "string"},
        },
        "clarification_questions": {
            "type": "array",
            "items": {"type": "string"},
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


REQUIREMENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "functional_requirements": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Specific system capabilities or user-facing behaviors "
                "that are supported by the discovery information."
            ),
        },
        "non_functional_requirements": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Quality attributes or technical constraints such as "
                "security, performance, availability, accessibility, "
                "or compliance. Only include justified requirements."
            ),
        },
        "acceptance_criteria": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Observable conditions that can be used to determine "
                "whether the requirements have been satisfied."
            ),
        },
        "open_questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Questions that must be answered before the requirements "
                "can be considered sufficiently defined."
            ),
        },
        "contradictions": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Contradictions or inconsistencies found in the discovery "
                "information. Empty if none are identified."
            ),
        },
    },
    "required": [
        "functional_requirements",
        "non_functional_requirements",
        "acceptance_criteria",
        "open_questions",
        "contradictions",
    ],
}


def discovery_agent(
    state: DeliveryState,
    provider: AIProvider,
) -> dict:
    """
    AI Discovery Agent.

    Converts a raw customer request into structured discovery
    information.
    """

    request = state["user_request"]

    prompt = f"""
You are a senior software delivery discovery consultant.

Analyze the customer's initial request and produce a structured
discovery assessment.

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


def requirements_agent(
    state: DeliveryState,
    provider: AIProvider,
) -> dict:
    """
    AI Requirements Agent.

    Takes structured discovery information and converts it into
    an initial requirements definition.
    """

    discovery = state["discovery"]

    prompt = f"""
You are a senior Business Analyst and Software Requirements Engineer.

Your job is to transform structured discovery information into
an initial requirements definition.

DISCOVERY:

{discovery}

IMPORTANT RULES:

1. Only derive requirements that are supported by the discovery.
2. Do not invent detailed features simply because they are common
   for this type of product.
3. Distinguish clearly between requirements and open questions.
4. Functional requirements describe what the system should do.
5. Non-functional requirements describe qualities or constraints
   such as security, performance, availability, accessibility,
   or compliance.
6. Acceptance criteria must be observable and testable.
7. If discovery information is insufficient, put the missing
   information into open_questions.
8. Identify contradictions if the discovery contains conflicting
   information.
9. Do not treat assumptions as confirmed requirements.
"""

    requirements = provider.generate_json(
        prompt=prompt,
        schema=REQUIREMENTS_SCHEMA,
    )

    return {"requirements": requirements}