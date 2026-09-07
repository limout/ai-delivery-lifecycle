from app.providers import AIProvider
from app.state import DeliveryState


DISCOVERY_SCHEMA = {
    "type": "object",
    "properties": {
        "problem": {"type": "string"},
        "business_goal": {"type": "string"},
        "users": {"type": "array", "items": {"type": "string"}},
        "stakeholders": {"type": "array", "items": {"type": "string"}},
        "existing_systems": {"type": "array", "items": {"type": "string"}},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "unknowns": {"type": "array", "items": {"type": "string"}},
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
        "non_blocking_questions": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "status",
        "reasons",
        "questions",
        "non_blocking_questions",
    ],
}


SOLUTION_SCHEMA = {
    "type": "object",
    "properties": {
        "solution_summary": {"type": "string"},
        "key_capabilities": {
            "type": "array",
            "items": {"type": "string"},
        },
        "integration_approach": {
            "type": "array",
            "items": {"type": "string"},
        },
        "technical_considerations": {
            "type": "array",
            "items": {"type": "string"},
        },
        "delivery_risks": {
            "type": "array",
            "items": {"type": "string"},
        },
        "dependencies": {
            "type": "array",
            "items": {"type": "string"},
        },
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "solution_summary",
        "key_capabilities",
        "integration_approach",
        "technical_considerations",
        "delivery_risks",
        "dependencies",
        "assumptions",
    ],
}


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "delivery_phases": {
            "type": "array",
            "items": {"type": "string"},
        },
        "workstreams": {
            "type": "array",
            "items": {"type": "string"},
        },
        "dependencies": {
            "type": "array",
            "items": {"type": "string"},
        },
        "milestones": {
            "type": "array",
            "items": {"type": "string"},
        },
        "team_roles": {
            "type": "array",
            "items": {"type": "string"},
        },
        "delivery_risks": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "delivery_phases",
        "workstreams",
        "dependencies",
        "milestones",
        "team_roles",
        "delivery_risks",
    ],
}


ESTIMATE_SCHEMA = {
    "type": "object",
    "properties": {
        "effort_range": {"type": "string"},
        "duration_range": {"type": "string"},
        "confidence": {
            "type": "string",
            "enum": ["LOW", "MEDIUM", "HIGH"],
        },
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "risks_affecting_estimate": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "effort_range",
        "duration_range",
        "confidence",
        "assumptions",
        "risks_affecting_estimate",
    ],
}


PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "executive_summary": {"type": "string"},
        "scope": {
            "type": "array",
            "items": {"type": "string"},
        },
        "delivery_approach": {
            "type": "array",
            "items": {"type": "string"},
        },
        "timeline": {"type": "string"},
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "risks": {
            "type": "array",
            "items": {"type": "string"},
        },
        "next_steps": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "executive_summary",
        "scope",
        "delivery_approach",
        "timeline",
        "assumptions",
        "risks",
        "next_steps",
    ],
}


SOW_SCHEMA = {
    "type": "object",
    "properties": {
        "objectives": {
            "type": "array",
            "items": {"type": "string"},
        },
        "deliverables": {
            "type": "array",
            "items": {"type": "string"},
        },
        "in_scope": {
            "type": "array",
            "items": {"type": "string"},
        },
        "out_of_scope": {
            "type": "array",
            "items": {"type": "string"},
        },
        "dependencies": {
            "type": "array",
            "items": {"type": "string"},
        },
        "acceptance": {
            "type": "array",
            "items": {"type": "string"},
        },
        "timeline": {"type": "string"},
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "objectives",
        "deliverables",
        "in_scope",
        "out_of_scope",
        "dependencies",
        "acceptance",
        "timeline",
        "assumptions",
    ],
}



DELIVERY_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["READY", "BLOCKED"]},
        "blocking_issues": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "checks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "blocking_issues", "warnings", "checks"],
}

def discovery_agent(
    state: DeliveryState,
    provider: AIProvider,
) -> dict:

    request = state["user_request"]
    clarification_answers = state.get("clarification_answers", [])

    clarification_context = ""

    if clarification_answers:
        clarification_context = f"""
Previous clarification answers from the customer:

{clarification_answers}

Use these answers as new customer-provided facts.

Re-evaluate the discovery using the updated information.

Do not treat unanswered questions as answered.
Do not invent information that is not present in the answers.
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

    result = {
        "discovery": discovery,
    }

    if "iteration" in state:
        result["iteration"] = state["iteration"]

    return result


def requirements_agent(
    state: DeliveryState,
    provider: AIProvider,
) -> dict:

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
3. Every concrete customer capability in discovery must be
   represented by at least one functional requirement when it is
   specific enough to state as system behavior.
4. Functional requirements describe what the system should do.
5. Non-functional requirements describe only justified qualities or
   explicit constraints such as security, performance, accessibility,
   or compliance.
6. Acceptance criteria must be observable and testable.
7. If information is insufficient, put the missing detail into
   open_questions rather than inventing an answer.
8. Identify contradictions between discovery facts and requirements.
9. Do not treat assumptions as confirmed requirements.
10. Do not return empty requirement lists when the discovery contains
    concrete capabilities or constraints.
"""

    requirements = provider.generate_json(
        prompt=prompt,
        schema=REQUIREMENTS_SCHEMA,
    )

    has_any_requirements = any(
        requirements.get(key)
        for key in (
            "functional_requirements",
            "non_functional_requirements",
            "acceptance_criteria",
        )
    )

    if not has_any_requirements and (
        discovery.get("problem")
        or discovery.get("business_goal")
        or discovery.get("users")
        or discovery.get("constraints")
    ):
        retry_prompt = f"""
The previous requirements response was empty. Re-do the requirements
analysis using ONLY the discovery below.

DISCOVERY:
{discovery}

Return at least the concrete functional and/or non-functional
requirements that are directly supported by the discovery. Do not
invent features. Put unresolved details into open_questions.
Acceptance criteria must be testable.
"""
        requirements = provider.generate_json(
            prompt=retry_prompt,
            schema=REQUIREMENTS_SCHEMA,
        )

    return {
        "requirements": requirements,
    }

def validation_agent(
    state: DeliveryState,
    provider: AIProvider,
) -> dict:

    discovery = state["discovery"]
    requirements = state["requirements"]

    prompt = f"""
You are a senior Delivery Lead reviewing a project before
solution shaping and preliminary estimation.

Review the Discovery and Requirements below.

DISCOVERY:

{discovery}

REQUIREMENTS:

{requirements}

Your job is NOT to decide whether every question has been answered.

Your job is to decide whether there is enough information to
perform the NEXT stage: solution shaping and preliminary delivery
planning.

Use two categories of uncertainty:

1. BLOCKING uncertainty
   Missing information that materially prevents the next stage.
   Examples:
   - fundamental ambiguity about the product or business outcome
   - unresolved contradiction in scope or requirements
   - a critical integration/source-of-truth question that makes
     the solution direction impossible to define
   - a critical security/compliance constraint that could completely
     change the solution
   - missing information that makes even a preliminary delivery
     approach impossible

2. NON-BLOCKING uncertainty
   Useful details that should eventually be clarified, but do not
   prevent a reasonable preliminary solution and delivery approach.
   Examples:
   - exact account fields
   - detailed documentation categories
   - branding preferences
   - expected user volume when it does not currently determine the
     architecture
   - detailed support-request categories
   - budget when the current stage is solution shaping rather than
     commercial approval

Decision rules:

- Return NEEDS_INFO only when BLOCKING uncertainty exists.
- Return READY when the next stage can proceed using explicit
  assumptions and carrying forward non-blocking questions.
- Never turn every open question into a blocker.
- Existing open_questions from Requirements are NOT automatically
  blockers.
- If a question can reasonably be handled as an assumption, risk,
  dependency, or later refinement, classify it as non-blocking.
- Do not invent answers.
- If requirements contradict discovery, return NEEDS_INFO.

Output rules:

- "reasons" explains the decision.
- "questions" contains ONLY questions that must be answered before
  the next stage and therefore justify NEEDS_INFO.
- "non_blocking_questions" contains useful unresolved questions that
  should be carried forward without stopping the workflow.
- For READY, "questions" must be empty.
- For NEEDS_INFO, "questions" must contain the blocking questions.

DISCOVERY:

{discovery}

REQUIREMENTS:

{requirements}
"""

    validation = provider.generate_json(
        prompt=prompt,
        schema=VALIDATION_SCHEMA,
    )

    return {
        "validation": validation,
    }


def clarification_agent(state: DeliveryState) -> dict:
    """
    Prepare the graph output for the customer clarification step.
    """

    validation = state["validation"]

    return {
        "clarification_questions": validation.get("questions", []),
        "iteration": state.get("iteration", 1) + 1,
    }


def solution_shaping_agent(
    state: DeliveryState,
    provider: AIProvider,
) -> dict:

    discovery = state["discovery"]
    requirements = state["requirements"]

    prompt = f"""
You are a senior Solution Architect and Delivery Lead.

Create an initial solution shaping assessment from the
confirmed Discovery and Requirements.

DISCOVERY:

{discovery}

REQUIREMENTS:

{requirements}

Rules:

1. Stay within the information provided.
2. Do not invent confirmed technologies.
3. Clearly separate assumptions from facts.
4. Identify integration and technical considerations.
5. Identify delivery risks and dependencies.
6. Produce a practical solution direction suitable for planning.
"""

    solution = provider.generate_json(
        prompt=prompt,
        schema=SOLUTION_SCHEMA,
    )

    return {
        "solution": solution,
    }


def delivery_planning_agent(
    state: DeliveryState,
    provider: AIProvider,
) -> dict:

    discovery = state["discovery"]
    requirements = state["requirements"]
    solution = state["solution"]

    prompt = f"""
You are a senior Delivery Manager.

Create an initial delivery plan based on the Discovery,
Requirements and Solution Shaping.

DISCOVERY:

{discovery}

REQUIREMENTS:

{requirements}

SOLUTION:

{solution}

Rules:

1. Create logical delivery phases.
2. Identify workstreams and dependencies.
3. Identify realistic milestones.
4. Identify roles needed.
5. Do not invent a specific team size.
6. Highlight delivery risks.
"""

    plan = provider.generate_json(
        prompt=prompt,
        schema=PLAN_SCHEMA,
    )

    return {
        "delivery_plan": plan,
    }


def estimation_agent(
    state: DeliveryState,
    provider: AIProvider,
) -> dict:

    discovery = state["discovery"]
    requirements = state["requirements"]
    solution = state["solution"]
    delivery_plan = state["delivery_plan"]

    prompt = f"""
You are a senior Delivery Manager preparing a preliminary estimate.

Use the information below.

DISCOVERY:

{discovery}

REQUIREMENTS:

{requirements}

SOLUTION:

{solution}

DELIVERY PLAN:

{delivery_plan}

Produce a preliminary estimate.

IMPORTANT:

1. This is an indicative estimate, not a contractual commitment.
2. Do not present false precision.
3. Provide a range rather than an exact number.
4. State assumptions.
5. State confidence.
6. Identify risks that could materially change the estimate.
"""

    estimate = provider.generate_json(
        prompt=prompt,
        schema=ESTIMATE_SCHEMA,
    )

    return {
        "estimate": estimate,
    }


def proposal_agent(
    state: DeliveryState,
    provider: AIProvider,
) -> dict:

    discovery = state["discovery"]
    requirements = state["requirements"]
    solution = state["solution"]
    delivery_plan = state["delivery_plan"]
    estimate = state["estimate"]

    prompt = f"""
You are a senior Delivery Manager preparing a customer proposal.

Create a concise proposal based only on the information below.

DISCOVERY:

{discovery}

REQUIREMENTS:

{requirements}

SOLUTION:

{solution}

DELIVERY PLAN:

{delivery_plan}

ESTIMATE:

{estimate}

Rules:

1. Clearly describe the customer problem and proposed solution.
2. Describe scope without inventing unsupported features.
3. Use the estimate as indicative.
4. Include assumptions and risks.
5. Include practical next steps.
"""

    proposal = provider.generate_json(
        prompt=prompt,
        schema=PROPOSAL_SCHEMA,
    )

    return {
        "proposal": proposal,
    }


def sow_agent(
    state: DeliveryState,
    provider: AIProvider,
) -> dict:

    discovery = state["discovery"]
    requirements = state["requirements"]
    solution = state["solution"]
    delivery_plan = state["delivery_plan"]
    estimate = state["estimate"]

    prompt = f"""
You are a senior Delivery Manager preparing a Statement of Work.

Create a structured SOW draft from the confirmed project
information.

DISCOVERY:

{discovery}

REQUIREMENTS:

{requirements}

SOLUTION:

{solution}

DELIVERY PLAN:

{delivery_plan}

ESTIMATE:

{estimate}

Rules:

1. Objectives must reflect the business goal.
2. Deliverables must be derived from requirements and solution.
3. Separate in-scope and out-of-scope items.
4. Include dependencies and acceptance criteria.
5. Treat timeline and estimate as indicative unless explicitly
   confirmed by the customer.
6. Do not invent commercial or contractual terms.
"""

    sow = provider.generate_json(
        prompt=prompt,
        schema=SOW_SCHEMA,
    )

    return {
        "sow": sow,
    }

def _flatten_confirmed_discovery(discovery: dict) -> str:
    """Return only customer-confirmed discovery content for provenance checks."""
    confirmed_keys = (
        "problem",
        "business_goal",
        "users",
        "stakeholders",
        "existing_systems",
        "constraints",
    )
    values = [discovery.get(key, "") for key in confirmed_keys]
    return " ".join(str(value) for value in values).lower()


def _parse_max_weeks(duration_text: str) -> float | None:
    """Extract the largest week value from an estimate duration range."""
    import re

    text = str(duration_text or "").lower().replace("–", "-").replace("—", "-")
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*weeks?", text)
    if matches:
        return max(float(high) for _, high in matches)

    single = re.findall(r"(\d+(?:\.\d+)?)\s*weeks?", text)
    if single:
        return max(float(value) for value in single)

    return None


def _parse_max_months(constraints: list[str]) -> float | None:
    """Extract the smallest explicit month-based deadline from constraints."""
    import re

    values: list[float] = []
    for item in constraints or []:
        text = str(item).lower()
        for number in re.findall(r"(\d+(?:\.\d+)?)\s*months?", text):
            values.append(float(number))
        if "two months" in text:
            values.append(2.0)

    return min(values) if values else None


def _deterministic_delivery_gate(
    discovery: dict,
    requirements: dict,
    estimate: dict,
) -> tuple[list[str], list[str], list[str]]:
    """Enforce objective delivery invariants independently of the LLM."""
    blocking: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    # 1. Customer deadline must not be shorter than the preliminary estimate.
    deadline_months = _parse_max_months(discovery.get("constraints", []))
    estimate_max_weeks = _parse_max_weeks(estimate.get("duration_range", ""))

    if deadline_months is not None and estimate_max_weeks is not None:
        deadline_weeks = deadline_months * 4.345
        if estimate_max_weeks > deadline_weeks:
            blocking.append(
                "The preliminary estimate exceeds the explicit customer launch deadline. "
                f"Customer deadline is {deadline_months:g} month(s) while the estimate reaches "
                f"{estimate_max_weeks:g} weeks."
            )
        else:
            checks.append("Preliminary estimate does not exceed the explicit customer deadline.")
    else:
        warnings.append("A machine-checkable customer deadline or estimate duration was not available.")

    # 2. Quantified requirements must be grounded in confirmed discovery.
    #    This catches invented SLOs, user-volume targets, response times, etc.
    import re

    confirmed_text = _flatten_confirmed_discovery(discovery)
    quantified_requirements = [
        *requirements.get("functional_requirements", []),
        *requirements.get("non_functional_requirements", []),
        *requirements.get("acceptance_criteria", []),
    ]
    for requirement in quantified_requirements:
        text = str(requirement)
        numbers = re.findall(
            r"(?:\b\d+(?:\.\d+)?\s*%|\b\d+(?:\.\d+)?\s*(?:users?|customers?|seconds?|ms|minutes?|hours?|days?|weeks?|months?))",
            text.lower(),
        )
        if numbers and not any(token in confirmed_text for token in numbers):
            blocking.append(
                f"Requirement contains an ungrounded quantified commitment: {text}"
            )

    if not any("Requirement contains an ungrounded quantified commitment" in item for item in blocking):
        checks.append("No ungrounded quantified commitments were detected in requirements.")

    # 3. Unknowns must not silently become confirmed commitments.
    unknown_text = " ".join(str(item) for item in discovery.get("unknowns", [])).lower()
    requirement_text = " ".join(str(item) for item in quantified_requirements).lower()
    unknown_markers = (
        ("user volume", "user volume"),
        ("data privacy regulations", "privacy regulations"),
        ("security and compliance requirements", "compliance"),
    )
    for source_phrase, requirement_phrase in unknown_markers:
        if source_phrase in unknown_text and requirement_phrase in requirement_text:
            blocking.append(
                f"A customer unknown ('{source_phrase}') was converted into a confirmed requirement."
            )

    if not any("customer unknown" in item for item in blocking):
        checks.append("Customer unknowns were not promoted into confirmed requirements by deterministic checks.")

    return blocking, warnings, checks


def delivery_review_agent(
    state: DeliveryState,
    provider: AIProvider,
) -> dict:
    discovery = state["discovery"]
    requirements = state["requirements"]
    solution = state["solution"]
    delivery_plan = state["delivery_plan"]
    estimate = state["estimate"]

    prompt = f"""
You are a senior Delivery Lead performing a cross-agent quality gate
before a customer proposal and Statement of Work are produced.

Review the artifacts below for grounding, consistency, and delivery
feasibility.

DISCOVERY:
{discovery}

REQUIREMENTS:
{requirements}

SOLUTION:
{solution}

DELIVERY PLAN:
{delivery_plan}

ESTIMATE:
{estimate}

Rules:
1. A requirement or explicit customer statement is the source of truth.
2. Flag as BLOCKING any confirmed scope item that cannot be traced to
   discovery or requirements.
3. Flag as BLOCKING any direct contradiction between the customer
   timeline and the proposed delivery duration.
4. Check that effort and duration are at least plausibly consistent
   with the delivery plan; flag a material mismatch as BLOCKING.
5. Estimates remain indicative, but must be internally coherent.
6. Unresolved detail that can safely remain an assumption is a warning,
   not a blocker.
7. Do not invent missing facts while reviewing.
8. If an objective rule is violated, it MUST be BLOCKED, not READY.
9. If there are no material blockers, return READY.
"""

    review = provider.generate_json(
        prompt=prompt,
        schema=DELIVERY_REVIEW_SCHEMA,
    )

    deterministic_blocking, deterministic_warnings, deterministic_checks = _deterministic_delivery_gate(
        discovery=discovery,
        requirements=requirements,
        estimate=estimate,
    )

    blocking_issues = list(review.get("blocking_issues", []))
    warnings = list(review.get("warnings", []))
    checks = list(review.get("checks", []))

    for issue in deterministic_blocking:
        if issue not in blocking_issues:
            blocking_issues.append(issue)
    for warning in deterministic_warnings:
        if warning not in warnings:
            warnings.append(warning)
    for check in deterministic_checks:
        if check not in checks:
            checks.append(check)

    status = "BLOCKED" if blocking_issues else "READY"

    return {
        "delivery_review": {
            "status": status,
            "blocking_issues": blocking_issues,
            "warnings": warnings,
            "checks": checks,
        },
    }
