import re
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
        "clarification_questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "priority": {"type": "string", "enum": ["REQUIRED", "RECOMMENDED", "OPTIONAL"]},
                    "reason": {"type": "string"},
                    "blocks_workflow": {"type": "boolean"},
                },
                "required": ["question", "priority", "reason", "blocks_workflow"],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
        "checks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "blocking_issues", "clarification_questions", "warnings", "checks"],
}



def _clarification_records(state: DeliveryState) -> list[dict]:
    """Return all customer clarification facts available to this run."""
    records: list[dict] = []

    for item in state.get("clarification_history", []) or []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if answer:
            records.append({"question": question, "answer": answer})

    for item in state.get("clarification_answers", []) or []:
        text = str(item).strip()
        if text:
            records.append({"question": "", "answer": text})

    return records


def _clarification_context(state: DeliveryState) -> str:
    """Format cumulative customer answers for every agent re-entry."""
    records = _clarification_records(state)
    if not records:
        return ""

    lines = []
    for record in records:
        if record["question"]:
            lines.append(
                f"Question: {record['question']}\nAnswer: {record['answer']}"
            )
        else:
            lines.append(f"Customer answer: {record['answer']}")

    return """
CUMULATIVE CUSTOMER CLARIFICATION FACTS:

%s

These are authoritative customer-provided facts from previous
clarification iterations. They remain valid unless a later customer
answer explicitly contradicts them.

Do not ask the customer again for information already answered here.
Do not convert an answered question back into an unknown or blocker.
""" % "\n\n".join(lines)


def _answered_clarification_topics(state: DeliveryState) -> set[str]:
    """Classify topics that the customer has already answered."""
    text = " ".join(
        f"{record['question']} {record['answer']}"
        for record in _clarification_records(state)
    ).lower()

    topics: set[str] = set()

    if any(marker in text for marker in (
        "gdpr",
        "data privacy",
        "privacy regulation",
        "compliance",
        "security requirements",
        "security and compliance",
        "encryption in transit",
        "encryption at rest",
        "audit logging",
    )):
        topics.add("security_compliance")

    if any(marker in text for marker in (
        "user volume",
        "registered users",
        "concurrent users",
        "expected volume",
        "expected user volume",
        "users will",
    )):
        topics.add("user_volume")

    if any(marker in text for marker in (
        "enterprise customer user",
        "enterprise customer admin",
        "customer support agent",
        "internal admin",
        "user roles",
        "roles/permissions",
        "roles and permissions",
        "role-based access",
        "rbac",
    )):
        topics.add("roles_permissions")

    if "salesforce" in text and any(marker in text for marker in (
        "integration", "api", "system of record", "existing", "current state"
    )):
        topics.add("salesforce_integration")

    if "entra" in text and any(marker in text for marker in (
        "integration", "api", "authentication", "identity provider", "existing", "current state"
    )):
        topics.add("entra_integration")

    return topics


def _question_topic(question: str) -> str | None:
    """Map a clarification question to the canonical topic it resolves."""
    text = str(question or "").lower()

    if any(marker in text for marker in (
        "security", "compliance", "data privacy", "privacy requirements", "regulatory"
    )):
        return "security_compliance"
    if any(marker in text for marker in (
        "user volume", "expected user volume", "traffic", "concurrent users"
    )):
        return "user_volume"
    if any(marker in text for marker in (
        "user roles", "roles/permissions", "roles and permissions", "permissions"
    )):
        return "roles_permissions"
    if "salesforce" in text and "integration" in text:
        return "salesforce_integration"
    if "entra" in text and "integration" in text:
        return "entra_integration"
    return None


def _filter_answered_questions(questions: list, state: DeliveryState) -> list:
    """Remove questions whose canonical topic was already answered."""
    answered = _answered_clarification_topics(state)
    if not answered:
        return questions

    filtered = []
    for item in questions or []:
        text = item.get("question") if isinstance(item, dict) else str(item)
        topic = _question_topic(text)
        if topic and topic in answered:
            continue
        filtered.append(item)
    return filtered

def _filter_answered_discovery(discovery: dict, state: DeliveryState) -> dict:
    """Remove stale discovery unknowns/questions after customer answers."""
    answered = _answered_clarification_topics(state)
    if not answered:
        return discovery

    cleaned = dict(discovery)
    cleaned["unknowns"] = [
        item for item in discovery.get("unknowns", []) or []
        if not (_question_topic(str(item)) in answered)
    ]
    cleaned["clarification_questions"] = _filter_answered_questions(
        discovery.get("clarification_questions", []) or [], state
    )
    return cleaned


def _filter_answered_requirement_questions(requirements: dict, state: DeliveryState) -> dict:
    """Remove answered topics from the requirements open-question list."""
    answered = _answered_clarification_topics(state)
    if not answered:
        return requirements

    cleaned = dict(requirements)
    cleaned["open_questions"] = [
        item for item in requirements.get("open_questions", []) or []
        if not (_question_topic(str(item)) in answered)
    ]
    return cleaned


def _clean_downstream_items(items: list, state: DeliveryState) -> list:
    """Drop stale clarification/confirmation items from downstream artifacts."""
    answered = _answered_clarification_topics(state)
    if not answered:
        return list(items or [])

    cleaned = []
    stale_markers = (
        "clarify", "clarification", "confirm", "confirmation",
        "determine", "unknown", "uncertainty", "must be confirmed",
        "needs to be confirmed", "needs confirmation",
    )
    for item in items or []:
        text = str(item)
        lower = text.lower()
        topic = _question_topic(lower)
        if topic in answered and any(marker in lower for marker in stale_markers):
            continue
        cleaned.append(item)
    return cleaned


def _ground_downstream_artifact(artifact: dict, state: DeliveryState) -> dict:
    """Prevent downstream agents from carrying answered blockers forward."""
    if not isinstance(artifact, dict):
        return artifact

    cleaned = dict(artifact)
    for key in (
        "delivery_risks", "dependencies", "next_steps",
        "risks_affecting_estimate",
    ):
        if isinstance(cleaned.get(key), list):
            cleaned[key] = _clean_downstream_items(cleaned[key], state)

    # Do not carry model-invented documentation claims as customer facts.
    if isinstance(cleaned.get("assumptions"), list):
        cleaned["assumptions"] = [
            item for item in cleaned["assumptions"]
            if "well-documented" not in str(item).lower()
            and "well documented" not in str(item).lower()
        ]
    return cleaned

def discovery_agent(
    state: DeliveryState,
    provider: AIProvider,
) -> dict:

    request = state["user_request"]
    clarification_context = _clarification_context(state)

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
    discovery = _filter_answered_discovery(discovery, state)

    # The original request defines enterprise customers as the portal audience.
    # Clarification about internal roles must not replace that customer audience.
    source_text = " ".join([
        str(discovery.get("problem") or ""),
        str(discovery.get("business_goal") or ""),
    ]).lower()
    if "enterprise customers" in source_text:
        users = list(discovery.get("users", []) or [])
        if not any("enterprise customer" in str(item).lower() for item in users):
            users.insert(0, "Enterprise customers")
        discovery["users"] = users

    result = {
        "discovery": discovery,
    }

    if "iteration" in state:
        result["iteration"] = state["iteration"]

    return result


def _requirements_need_grounding_retry(discovery: dict, requirements: dict) -> bool:
    """Detect common cases where the model promoted unknowns into requirements."""
    unknown_text = " ".join(str(item) for item in discovery.get("unknowns", [])).lower()
    all_requirements = [
        *requirements.get("functional_requirements", []),
        *requirements.get("non_functional_requirements", []),
        *requirements.get("acceptance_criteria", []),
    ]
    requirement_text = " ".join(str(item) for item in all_requirements).lower()

    unknown_markers = (
        "user volume",
        "data privacy regulations",
        "security and compliance requirements",
        "current state of salesforce integration",
        "current state of entra id integration",
        "desired user interface",
    )
    if any(marker in unknown_text and marker in requirement_text for marker in unknown_markers):
        return True

    confirmed_text = _flatten_confirmed_discovery(discovery)
    for requirement in all_requirements:
        numbers = re.findall(
            r"(?:\b\d+(?:\.\d+)?\s*%|\b\d+(?:\.\d+)?\s*(?:users?|customers?|seconds?|ms|minutes?|hours?|days?|weeks?|months?))",
            str(requirement).lower(),
        )
        if numbers and not all(token in confirmed_text for token in numbers):
            return True
    return False


def _ground_requirements_to_discovery(discovery: dict, requirements: dict) -> dict:
    """Remove unsupported commitments after the model pass."""
    confirmed_text = _flatten_confirmed_discovery(discovery)
    unknown_text = " ".join(str(item) for item in discovery.get("unknowns", [])).lower()

    grounded = {
        "functional_requirements": [],
        "non_functional_requirements": [],
        "acceptance_criteria": [],
        "open_questions": list(requirements.get("open_questions", [])),
        "contradictions": list(requirements.get("contradictions", [])),
    }

    unsupported_markers = (
        "user volume",
        "data privacy regulations",
        "security and compliance requirements",
        "current state of salesforce integration",
        "current state of entra id integration",
        "desired user interface",
        "branding",
    )

    def is_grounded(text: str) -> bool:
        lower = text.lower()
        if any(marker in lower and marker in unknown_text for marker in unsupported_markers):
            return False
        numbers = re.findall(
            r"(?:\b\d+(?:\.\d+)?\s*%|\b\d+(?:\.\d+)?\s*(?:users?|customers?|seconds?|ms|minutes?|hours?|days?|weeks?|months?))",
            lower,
        )
        return not numbers or all(token in confirmed_text for token in numbers)

    for key in ("functional_requirements", "non_functional_requirements", "acceptance_criteria"):
        for item in requirements.get(key, []) or []:
            text = str(item)
            if is_grounded(text):
                grounded[key].append(text)
            else:
                question = text
                if "must" in question.lower():
                    question = re.sub(
                        r"^The portal must ",
                        "What should the portal ",
                        question,
                        flags=re.I,
                    )
                    question = question.rstrip(".") + "?"
                if question not in grounded["open_questions"]:
                    grounded["open_questions"].append(question)

    return grounded


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

    if _requirements_need_grounding_retry(discovery, requirements):
        retry_prompt = f"""
Rebuild the requirements artifact using a strict provenance rule.

DISCOVERY (customer-confirmed facts only):
{discovery}

PREVIOUS REQUIREMENTS:
{requirements}

Rules:
1. A confirmed requirement MUST be directly supported by customer-confirmed discovery facts or explicit customer constraints.
2. NEVER convert discovery.unknowns into requirements.
3. NEVER invent numeric commitments such as uptime, response time, user volume, performance targets, or compliance standards.
4. If a detail is unknown, put the question in open_questions.
5. Do not turn assumptions into confirmed requirements.
6. Acceptance criteria may only test grounded requirements.
7. Keep the customer's explicit launch deadline as a requirement/constraint.

Return the complete requirements schema.
"""
        requirements = provider.generate_json(
            prompt=retry_prompt,
            schema=REQUIREMENTS_SCHEMA,
        )

    requirements = _ground_requirements_to_discovery(discovery, requirements)
    requirements = _filter_answered_requirement_questions(requirements, state)

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
        requirements = _ground_requirements_to_discovery(discovery, requirements)
        requirements = _filter_answered_requirement_questions(requirements, state)

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

Your job is to determine whether the project definition is ready
for the next delivery stage.

Do NOT decide whether every question has been answered. Instead,
decide whether there is enough information to perform the NEXT stage:
solution shaping and preliminary delivery planning.

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
- A deadline combined with an unresolved implementation option is NOT
  a contradiction unless the available evidence demonstrates that the
  deadline cannot be met under at least one viable implementation option.
- An unresolved technical dependency is NOT automatically
  customer-blocking. It becomes blocking only when a customer decision
  is required before the next stage can produce useful work.
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

    # Never allow a validation model response to reopen a topic that the
    # customer has already answered in a previous clarification iteration.
    validation["questions"] = _filter_answered_questions(
        validation.get("questions", []) or [],
        state,
    )
    validation["non_blocking_questions"] = _filter_answered_questions(
        validation.get("non_blocking_questions", []) or [],
        state,
    )

    # Deterministic gate: some customer unknowns are sufficiently material
    # that we must stop before solution/plan/estimate. This is deliberately
    # a small, explicit set — we do not turn every open question into a blocker.
    unknowns = [str(item).strip() for item in (discovery.get("unknowns", []) or []) if str(item).strip()]
    open_questions = [str(item).strip() for item in (requirements.get("open_questions", []) or []) if str(item).strip()]
    candidate_text = unknowns + open_questions

    blocker_rules = [
        (
            ("compliance", "data privacy", "regulatory", "security and compliance"),
            "What are the applicable security, compliance, and data privacy requirements?",
            "Required to avoid choosing a solution that cannot satisfy mandatory legal, regulatory, or security constraints.",
        ),
        (
            ("current level of integration with salesforce", "current state of salesforce integration", "salesforce integration"),
            "What is the current level of integration with Salesforce?",
            "Required to determine the integration approach and delivery effort rather than assuming the current integration state.",
        ),
        (
            ("current level of integration with microsoft entra", "current state of entra id integration", "entra id integration"),
            "What is the current level of integration with Microsoft Entra ID?",
            "Required to determine the authentication/integration approach and delivery effort rather than assuming the current integration state.",
        ),
        (
            ("user roles and permissions", "specific user roles", "user volume", "expected user volume"),
            "What are the expected user roles/permissions and expected user volume?",
            "Required to validate the access-control model and make a credible preliminary scalability and delivery assessment.",
        ),
    ]

    existing_questions = {
        str(item).strip().lower()
        for item in (validation.get("questions", []) or [])
        if str(item).strip()
    }
    blocking_questions = []
    non_blocking_questions = [
        str(item).strip()
        for item in (validation.get("non_blocking_questions", []) or [])
        if str(item).strip()
    ]

    # Minimum-scope gate: only stop for a genuinely vague request.
    # Do not treat every discovery unknown as blocking. A concrete product
    # capability plus at least one meaningful piece of delivery context is
    # enough to continue; the remaining details can stay non-blocking.
    functional_requirements = [
        str(item).strip()
        for item in (requirements.get("functional_requirements", []) or [])
        if str(item).strip()
    ]
    capability_text = " ".join(functional_requirements).lower()
    generic_capability_markers = (
        "self-service interface",
        "self service interface",
        "provide a self-service interface",
        "provide a self service interface",
    )
    has_concrete_capability = bool(functional_requirements) and not all(
        any(marker in item.lower() for marker in generic_capability_markers)
        for item in functional_requirements
    )

    meaningful_context_values = (
        discovery.get("users", []),
        discovery.get("stakeholders", []),
        discovery.get("existing_systems", []),
        discovery.get("constraints", []),
    )
    has_meaningful_context = any(
        bool(value) for value in meaningful_context_values
    )

    if (
        validation.get("status") == "READY"
        and (not has_concrete_capability or not has_meaningful_context)
    ):
        minimum_scope_question = (
            "What are the main capabilities the portal should provide, "
            "and who will use it?"
        )
        if minimum_scope_question.lower() not in existing_questions:
            blocking_questions.append(minimum_scope_question)
            existing_questions.add(minimum_scope_question.lower())

    # Contradictions are always blocking.
    contradictions = [
        str(item).strip()
        for item in (requirements.get("contradictions", []) or [])
        if str(item).strip()
    ]
    for contradiction in contradictions:
        if contradiction.lower() not in existing_questions:
            blocking_questions.append(contradiction)
            existing_questions.add(contradiction.lower())

    # Promote only explicit, material customer unknowns. Do not infer a
    # blocker merely because the model mentioned a generic open question.
    # Critically, an answered topic can never become a blocker again.
    answered_topics = _answered_clarification_topics(state)
    for unknown in candidate_text:
        lowered = unknown.lower()
        for markers, question, reason in blocker_rules:
            if any(marker in lowered for marker in markers):
                topic = _question_topic(question)
                if topic and topic in answered_topics:
                    break
                if question.lower() not in existing_questions:
                    blocking_questions.append(question)
                    existing_questions.add(question.lower())
                if question in non_blocking_questions:
                    non_blocking_questions.remove(question)
                break

    # Preserve model-selected blockers, but normalize them as strings.
    for question in (validation.get("questions", []) or []):
        text = str(question).strip()
        topic = _question_topic(text)
        if topic and topic in answered_topics:
            continue
        if text and text.lower() not in {q.lower() for q in blocking_questions}:
            blocking_questions.append(text)

    status = "NEEDS_INFO" if blocking_questions else "READY"
    reasons = [str(item).strip() for item in (validation.get("reasons", []) or []) if str(item).strip()]
    if contradictions and not any("contradiction" in r.lower() for r in reasons):
        reasons.append("Unresolved contradiction(s) must be clarified before the workflow can continue.")
    if blocking_questions and status == "NEEDS_INFO" and not any("blocking" in r.lower() for r in reasons):
        reasons.append("Material customer decisions remain unresolved and block the next delivery stage.")

    validation = {
        "status": status,
        "reasons": reasons,
        "questions": blocking_questions,
        "blocking_questions": blocking_questions,
        "non_blocking_questions": [
            q for q in non_blocking_questions
            if q.lower() not in {b.lower() for b in blocking_questions}
        ],
    }

    return {
        "validation": validation,
    }


def clarification_agent(state: DeliveryState) -> dict:
    """Build the human-in-the-loop clarification payload.

    Validation questions remain useful non-blocking questions. Delivery
    Review questions can be promoted to REQUIRED when a review blocker is
    explicitly customer-answerable. Purely internal blockers never become
    customer questions.
    """
    validation = state.get("validation", {}) or {}
    review = state.get("delivery_review", {}) or {}
    question_map = {}

    def add_question(item, default_priority="RECOMMENDED"):
        if isinstance(item, str):
            question = item.strip()
            if not question:
                return
            normalized = {
                "question": question,
                "priority": default_priority,
                "reason": "",
                "blocks_workflow": default_priority == "REQUIRED",
            }
        elif isinstance(item, dict):
            question = str(item.get("question") or item.get("text") or "").strip()
            if not question:
                return
            blocks = bool(item.get("blocks_workflow", default_priority == "REQUIRED"))
            normalized = {
                "question": question,
                "priority": "REQUIRED" if blocks else str(item.get("priority") or default_priority).upper(),
                "reason": str(item.get("reason") or ""),
                "blocks_workflow": blocks,
            }
        else:
            return

        existing = question_map.get(question)
        if existing is None:
            question_map[question] = normalized
        elif normalized["blocks_workflow"]:
            existing.update({"priority": "REQUIRED", "blocks_workflow": True})
            if not existing["reason"]:
                existing["reason"] = normalized["reason"]

    # Clarification is a human-in-the-loop stop. Show the customer only
    # questions that actually block continuation. Non-blocking questions
    # remain in validation and are carried forward, not dumped into the UI.
    for item in validation.get("blocking_questions", []) or validation.get("questions", []) or []:
        add_question(item, "REQUIRED")
    for item in review.get("clarification_questions", []) or []:
        add_question(item, "REQUIRED")

    questions = _filter_answered_questions(list(question_map.values()), state)
    blocking = [q for q in questions if q["blocks_workflow"]]
    non_blocking = [q for q in questions if not q["blocks_workflow"]]

    return {
        "clarification_questions": questions,
        "blocking_questions": blocking,
        "non_blocking_questions": non_blocking,
        "clarification_history": list(state.get("clarification_history", []) or []),
        "awaiting_customer": bool(blocking),
        "workflow_status": "NEEDS_INFO" if blocking else "READY",
        "current_stage": "clarification" if blocking else "validation",
    }


def solution_shaping_agent(
    state: DeliveryState,
    provider: AIProvider,
) -> dict:

    discovery = state["discovery"]
    requirements = state["requirements"]
    clarification_context = _clarification_context(state)

    prompt = f"""
You are a senior Solution Architect and Delivery Lead.

Create an initial solution shaping assessment from the
confirmed Discovery and Requirements.

DISCOVERY:

{discovery}

REQUIREMENTS:

{requirements}

{clarification_context}

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
    solution = _ground_downstream_artifact(solution, state)

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
    clarification_context = _clarification_context(state)

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

{clarification_context}

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
    plan = _ground_downstream_artifact(plan, state)

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
    clarification_context = _clarification_context(state)

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

{clarification_context}

Produce a preliminary estimate.

IMPORTANT:

1. This is an indicative estimate, not a contractual commitment.
2. Do not present false precision.
3. Provide a range rather than an exact number.
4. State assumptions.
5. State confidence.
6. Identify risks that could materially change the estimate.
7. Confidence must reflect the amount of unresolved delivery-critical information.
   Use LOW confidence when material scope, UX, data, integration, budget,
   migration, performance, or operational details remain open.
8. Never describe an unresolved area as "well understood" or "fully defined".
9. Explicitly distinguish customer-confirmed facts from planning assumptions.
10. The estimate should be a preliminary planning range, not a commitment.
"""

    estimate = provider.generate_json(
        prompt=prompt,
        schema=ESTIMATE_SCHEMA,
    )

    deadline_months = _parse_max_months(discovery.get("constraints", []))
    estimate_max_weeks = _parse_max_weeks(estimate.get("duration_range", ""))
    if (
        deadline_months is not None
        and estimate_max_weeks is not None
        and estimate_max_weeks > deadline_months * 4.345
    ):
        retry_prompt = f"""
Recalculate the preliminary estimate using the explicit customer deadline as a hard delivery constraint.

CUSTOMER DISCOVERY:
{discovery}

REQUIREMENTS:
{requirements}

SOLUTION:
{solution}

DELIVERY PLAN:
{delivery_plan}

PREVIOUS ESTIMATE:
{estimate}

The customer explicitly requires launch within {deadline_months:g} month(s).
Produce a realistic range compatible with that target where the confirmed
scope permits it. The estimate remains indicative, not contractual.
Do not invent scope or false precision. If the scope genuinely cannot fit,
state that clearly in risks, but do not inflate the estimate merely because
more work could be imagined.
"""
        estimate = provider.generate_json(
            prompt=retry_prompt,
            schema=ESTIMATE_SCHEMA,
        )

    estimate = _ground_downstream_artifact(estimate, state)

    # Keep the estimate honest when material discovery questions remain open.
    # A preliminary estimate can still be produced, but its confidence must
    # not imply that unresolved scope is already fully understood.
    open_questions = (
        state.get("requirements", {}) or {}
    ).get("open_questions", []) or []
    material_open_markers = (
        "ui", "user interface", "data storage", "database", "performance",
        "scalability", "third-party", "integration", "budget", "resource",
        "migration", "training", "onboarding", "support", "maintenance",
    )
    material_open_count = sum(
        1
        for question in open_questions
        if any(marker in str(question).lower() for marker in material_open_markers)
    )
    if material_open_count >= 2:
        estimate["confidence"] = "LOW"

    if isinstance(estimate.get("assumptions"), list):
        normalized_assumptions = []
        for item in estimate["assumptions"]:
            text = str(item)
            lower = text.lower()
            if "security and compliance requirements are well understood" in lower:
                text = (
                    "The security and compliance baseline is based on current customer input; "
                    "detailed technical controls may require refinement during solution design."
                )
            elif "security and compliance requirements are fully understood" in lower:
                text = (
                    "The security and compliance baseline is based on current customer input; "
                    "detailed technical controls may require refinement during solution design."
                )
            normalized_assumptions.append(text)
        estimate["assumptions"] = normalized_assumptions

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
    clarification_context = _clarification_context(state)

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

{clarification_context}

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
    proposal = _ground_downstream_artifact(proposal, state)

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
    clarification_context = _clarification_context(state)

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

{clarification_context}

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
    sow = _ground_downstream_artifact(sow, state)

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
9. If a blocking issue can be resolved by a concrete customer answer, add
   an exact clarification question with priority REQUIRED and
   blocks_workflow=true.
10. If a blocker is purely internal and does not require a customer decision,
    leave clarification_questions empty.
11. Never classify a customer-answerable blocker as RECOMMENDED or OPTIONAL.
12. Remaining non-blocking open questions may be carried forward as warnings,
    but they must not be described as unresolved blockers.
13. If there are no material blockers, return READY.
14. READY does not mean every project detail is finalized; it means the
    available information is sufficient to produce a preliminary delivery package.
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
    clarification_questions = list(review.get("clarification_questions", []))
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

    # Deterministic provenance blockers that are answerable by the customer
    # get an explicit REQUIRED question. This prevents a valid review blocker
    # from being exposed to the UI as merely a recommended question.
    issue_question_map = {
        "user volume": "What is the expected user volume?",
        "security and compliance requirements": "What are the security and compliance requirements for the portal?",
        "data privacy regulations": "What are the applicable data privacy and compliance requirements?",
    }

    existing_question_text = {
        str(q.get("question", "")).strip().lower()
        for q in clarification_questions
        if isinstance(q, dict)
    }

    for issue in blocking_issues:
        lowered = str(issue).lower()
        for marker, question_text in issue_question_map.items():
            if marker in lowered and question_text.lower() not in existing_question_text:
                clarification_questions.append({
                    "question": question_text,
                    "priority": "REQUIRED",
                    "reason": "The delivery review identified this customer decision as necessary to resolve the blocking issue.",
                    "blocks_workflow": True,
                })
                existing_question_text.add(question_text.lower())
                break

    normalized_questions = []
    # A READY review is not a hidden second clarification gate. Only review
    # questions attached to actual blocking issues may reach the customer.
    if blocking_issues:
        for question in clarification_questions:
            if not isinstance(question, dict):
                continue
            text = str(question.get("question") or question.get("text") or "").strip()
            if not text:
                continue
            blocks = bool(question.get("blocks_workflow", False))
            normalized_questions.append({
                "question": text,
                "priority": "REQUIRED" if blocks else "RECOMMENDED",
                "reason": str(question.get("reason") or ""),
                "blocks_workflow": blocks,
            })

    # Review must not claim that every detail is resolved when requirements
    # intentionally carry non-blocking open questions forward.
    open_questions = (requirements or {}).get("open_questions", []) or []
    if open_questions and not blocking_issues:
        checks = [
            check
            for check in checks
            if "no unresolved details" not in str(check).lower()
            and "all are flagged as required clarifications" not in str(check).lower()
        ]
        checks.append(
            f"{len(open_questions)} non-blocking requirement question(s) remain explicitly carried forward as planning assumptions or follow-up items."
        )

    status = "BLOCKED" if blocking_issues else "READY"

    return {
        "delivery_review": {
            "status": status,
            "blocking_issues": blocking_issues,
            "clarification_questions": normalized_questions,
            "warnings": warnings,
            "checks": checks,
        },
    }
