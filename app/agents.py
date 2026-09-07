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
        },
        "non_functional_requirements": {
            "type": "array",
            "items": {"type": "string"},
        },
        "acceptance_criteria": {
            "type": "array",
            "items": {"type": "string"},
        },
        "open_questions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "contradictions": {
            "type": "array",
            "items": {"type": "string"},
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


VALIDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["READY", "NEEDS_INFO"],
        },
        "reasons": {
            "type": "array",
            "items": {"type": "string"},
        },
        "questions": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "status",
        "reasons",
        "questions",
    ],
}


def discovery_agent(
    state: DeliveryState,
    provider: AIProvider,
) -> dict:
    """
    AI Discovery Agent.

    Converts the customer request and any clarification answers
    into structured discovery information.
    """

    request = state["user_request"]
    clarification_answers = state.get("clarification_answers", [])

    clarification_context = ""

    if clarification_answers:
        clarification_context = f"""
Previous clarification answers from the customer:

{clarification_answers}

Use these answers as new customer-provided facts.
Re-evaluate the discovery using the updated information.
"""

    prompt = f"""
You are a senior software delivery discovery consultant.

Analyze the customer's request and produce a structured
discovery assessment.

IMPORTANT RULES:

1. Separate facts from assumptions.
2. Never invent budget, timeline, users, systems, or business goals.
3. Identify missing information explicitly.
4. Generate useful clarification questions.
5. Customer clarification answers are authoritative customer input.
6. If a previous unknown has now been answered, remove it from
   unknowns where appropriate.
7. Think like a Delivery Lead preparing the project for requirements
   and later estimation.
8. The input may be vague, incomplete, or informal.

Original customer request:

{request}

{clarification_context}
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

Transform the structured discovery below into an initial
requirements definition.

DISCOVERY:

{discovery}

IMPORTANT RULES:

1. Only derive requirements supported by the discovery.
2. Do not invent detailed features.
3. Distinguish requirements from open questions.
4. Functional requirements describe what the system should do.
5. Non-functional requirements describe justified qualities or
   constraints such as security, performance, availability,
   accessibility, or compliance.
6. Acceptance criteria must be observable and testable.
7. If information is insufficient, put it into open_questions.
8. Identify contradictions.
9. Do not treat assumptions as confirmed requirements.
"""

    requirements = provider.generate_json(
        prompt=prompt,
        schema=REQUIREMENTS_SCHEMA,
    )

    return {"requirements": requirements}


def validation_agent(
    state: DeliveryState,
    provider: AIProvider,
) -> dict:
    """
    AI Validation Agent.

    Reviews Discovery and Requirements and decides whether the
    workflow has enough information to continue.
    """

    discovery = state["discovery"]
    requirements = state["requirements"]

    prompt = f"""
You are a senior Delivery Lead reviewing a project before
solution shaping and estimation.

Review the Discovery and Requirements below.

DISCOVERY:

{discovery}

REQUIREMENTS:

{requirements}

Decide whether the project definition is sufficiently clear
to continue.

Return READY only when the information is sufficiently clear
for the next delivery stage.

Return NEEDS_INFO when important information is still missing.

IMPORTANT:

1. Focus on information that materially affects scope, solution,
   security, integrations, delivery feasibility, or estimation.
2. Do not invent answers.
3. If information is missing, explain why it matters.
4. Provide concrete clarification questions.
5. If requirements contradict discovery, return NEEDS_INFO.
"""

    validation = provider.generate_json(
        prompt=prompt,
        schema=VALIDATION_SCHEMA,
    )

    return {"validation": validation}


def clarification_agent(state: DeliveryState) -> dict:
    """
    Prepare the clarification request that should be sent to
    the customer.

    The actual customer interaction will be added later through
    the API/UI.
    """

    validation = state["validation"]

    return {
        "clarification_answers": [],
        "iteration": state.get("iteration", 1) + 1,
    }