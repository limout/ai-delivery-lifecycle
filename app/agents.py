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
        "scope": {"type": "array", "items": {"type": "string"}},
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
        "scope",
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
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "risks_affecting_estimate": {"type": "array", "items": {"type": "string"}},
        "baseline_variance_explanation": {"type": "string"},
    },
    "required": [
        "effort_range",
        "duration_range",
        "confidence",
        "assumptions",
        "risks_affecting_estimate",
    ],
}

AI_OPTIMIZATION_SCHEMA = {
    "type": "object",
    "properties": {
        "duration_range": {"type": "string"},
        "effort_range": {"type": "string"},
        "confidence": {
            "type": "string",
            "enum": ["LOW", "MEDIUM", "HIGH"],
        },
        "optimization_summary": {"type": "string"},
        "optimization_levers": {"type": "array", "items": {"type": "string"}},
        "feasibility_conditions": {"type": "array", "items": {"type": "string"}},
        "optimization_team_model": {"type": "string"},
        "deadline_feasibility": {
            "type": "string",
            "enum": ["FEASIBLE", "FEASIBLE_WITH_CONDITIONS", "NOT_DEMONSTRATED", "NOT_APPLICABLE"],
        },
        "deadline_gap": {"type": "string"},
        "scope_tradeoffs": {"type": "array", "items": {"type": "string"}},
        "recommendations": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "duration_range",
        "effort_range",
        "confidence",
        "optimization_summary",
        "optimization_levers",
        "feasibility_conditions",
        "optimization_team_model",
        "deadline_feasibility",
        "deadline_gap",
        "scope_tradeoffs",
        "recommendations",
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
            and "black friday is a specific date" not in str(item).lower()
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
7. Preserve every concrete customer-stated capability in the explicit
   scope field. Scope must describe confirmed system capabilities, not
   inferred implementation details.
8. Think like a Delivery Lead preparing the project for requirements
   and later estimation.
9. The input may be vague, incomplete, or informal.
10. Never state or imply that the current infrastructure is inadequate,
   not scalable, or otherwise deficient unless the customer explicitly
   confirmed that fact. If scalability for Black Friday traffic is unknown,
   record it as unconfirmed/unknown rather than as an assumption presented
   as fact.

Original customer request:

{request}

{clarification_context}
"""

    discovery = provider.generate_json(
        prompt=prompt,
        schema=DISCOVERY_SCHEMA,
    )

    # Preserve an explicitly labelled customer scope even if the discovery model
    # omits or weakens it. This is customer provenance, not model inference.
    explicit_scope_items = _extract_explicit_scope_items(request)
    if explicit_scope_items:
        # Explicit customer scope is authoritative. Do not merge model-generated
        # paraphrases into it, otherwise provenance and downstream grounding become noisy.
        discovery["scope"] = explicit_scope_items
    elif not isinstance(discovery.get("scope"), list):
        discovery["scope"] = []

    # Preserve explicit customer timeline facts even if the discovery model omits
    # them from structured constraints. These facts are authoritative provenance
    # for the estimation stage.
    explicit_timeline_facts = _extract_explicit_timeline_facts(request)
    if explicit_timeline_facts:
        constraints = list(discovery.get("constraints", []) or [])
        existing_constraint_text = " ".join(str(item).lower() for item in constraints)
        for fact in explicit_timeline_facts:
            if fact.lower() not in existing_constraint_text:
                constraints.append(fact)
        discovery["constraints"] = constraints

    normalized_assumptions = []
    for item in discovery.get("assumptions", []) or []:
        text = str(item).strip()
        lower = text.lower()
        if "current infrastructure is adequate" in lower:
            text = "Current infrastructure capability for Black Friday traffic is unconfirmed."
            lower = text.lower()
        if (
            "3-month estimate is accurate" in lower
            or "3 months estimate is accurate" in lower
            or "development team's 3-month estimate" in lower
            or "development team has estimated" in lower
        ):
            continue
        if text and text not in normalized_assumptions:
            normalized_assumptions.append(text)
    discovery["assumptions"] = normalized_assumptions
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

    # Do not leave acceptance criteria referring to thresholds that are still open.
    normalized_acceptance = []
    for item in grounded["acceptance_criteria"]:
        text = str(item)
        lower = text.lower()
        if "defined thresholds" in lower and any(
            marker in " ".join(str(q).lower() for q in grounded["open_questions"])
            for marker in ("performance", "uptime", "response time")
        ):
            text = (
                "Black Friday reliability and performance targets are validated against "
                "customer-confirmed thresholds before final acceptance."
            )
        normalized_acceptance.append(text)
    grounded["acceptance_criteria"] = normalized_acceptance

    # Never leave model-invented performance thresholds disguised as confirmed acceptance criteria.
    normalized_acceptance = []
    for item in grounded["acceptance_criteria"]:
        text = str(item)
        lower = text.lower()
        if "defined thresholds" in lower or "acceptable response time" in lower or "uptime sla" in lower:
            normalized_acceptance.append(
                "Performance and reliability targets must be validated against customer-confirmed "
                "Black Friday thresholds before final acceptance."
            )
        else:
            normalized_acceptance.append(text)
    grounded["acceptance_criteria"] = list(dict.fromkeys(normalized_acceptance))

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

The explicit customer scope in Discovery is authoritative customer input.
Preserve it when deriving functional requirements.

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

    # If the customer explicitly provided concrete scope, preserve that scope as
    # functional requirements even when the local model returns an empty artifact.
    # This is deterministic provenance preservation, not feature inference.
    explicit_scope_items = _extract_explicit_scope_items(state.get("user_request", ""))
    if explicit_scope_items and not requirements.get("functional_requirements"):
        functional_requirements = []
        for item in explicit_scope_items:
            functional_requirements.extend(_scope_item_to_requirements(item))
        requirements["functional_requirements"] = functional_requirements

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
- Do not classify every unknown as blocking. Missing information is
  blocking only when the customer must provide it before the next stage
  can produce a meaningful result. Otherwise classify it as non-blocking
  and proceed using an explicit assumption, risk, dependency,
  investigation item, or range.
- The next stage is preliminary solution shaping and delivery planning,
  NOT final implementation planning. Do not require complete technical
  discovery before proceeding.
- For each unknown, explicitly ask: "Can the next stage produce a useful
  preliminary result using an explicit assumption, range, scenario, risk,
  dependency, or investigation item?" If YES, classify it as NON-BLOCKING.
  If NO because a specific customer decision is required before meaningful
  work can proceed, classify it as BLOCKING.
- Do not mark an unknown as blocking merely because resolving it would
  improve estimate accuracy, solution precision, or implementation detail.
- Never convert a model-proposed metric, threshold, architecture,
  technology, implementation detail, or acceptance criterion into a
  customer-confirmed requirement unless the customer explicitly
  provided or confirmed it.
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
            ("target delivery timeline", "delivery timeline", "target timeline"),
            "What is the target delivery timeline?",
            "Required to determine whether the next delivery stage can be planned against a concrete customer constraint.",
        ),
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

    # Requirements can legitimately be empty after deterministic grounding,
    # even when Discovery already contains enough concrete scope to proceed.
    # Use Discovery as the fallback source of scope instead of treating an
    # empty LLM requirements artifact as proof that the request is vague.
    discovery_scope_text = " ".join(
        str(discovery.get(key, ""))
        for key in (
            "problem",
            "business_goal",
            "users",
            "scope",
            "existing_systems",
            "constraints",
        )
    ).lower()
    discovery_capability_markers = (
        "manage",
        "submit",
        "track",
        "view",
        "create",
        "update",
        "request",
        "portal",
        "self-service",
        "self service",
    )
    has_discovery_capability = any(
        marker in discovery_scope_text for marker in discovery_capability_markers
    )

    # Meaningful delivery context should be concrete rather than a generic
    # placeholder such as "No specific constraints mentioned". Existing
    # systems are especially strong evidence that the solution direction is
    # already grounded.
    meaningful_constraints = [
        str(item).strip()
        for item in (discovery.get("constraints", []) or [])
        if str(item).strip()
        and str(item).strip().lower() not in {
            "no specific constraints mentioned",
            "no constraints mentioned",
        }
    ]
    has_meaningful_context = bool(
        discovery.get("existing_systems")
        or meaningful_constraints
    )

    has_usable_scope = has_concrete_capability or (
        has_discovery_capability and has_meaningful_context
    )

    if (
        validation.get("status") == "READY"
        and not has_usable_scope
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

    # Do not blindly preserve model-selected blockers. The model can identify
    # uncertainty, but routing remains deterministic: only explicit contradictions,
    # the minimum-scope gate, and the material customer-decision rules above can block.
    for question in (validation.get("questions", []) or []):
        text = str(question).strip()
        if not text:
            continue
        topic = _question_topic(text)
        if topic and topic in answered_topics:
            continue
        lower_text = text.lower()
        if lower_text not in {q.lower() for q in blocking_questions} and lower_text not in {q.lower() for q in non_blocking_questions}:
            non_blocking_questions.append(text)

    status = "NEEDS_INFO" if blocking_questions else "READY"
    reasons = [str(item).strip() for item in (validation.get("reasons", []) or []) if str(item).strip()]
    if status == "READY":
        contradictory_ready_markers = (
            "not ready", "not yet ready", "blocking uncertainties",
            "critical missing details", "prevent the next stage",
            "cannot proceed", "must be clarified before",
        )
        reasons = [
            r for r in reasons
            if not any(marker in r.lower() for marker in contradictory_ready_markers)
        ]
        if not reasons:
            reasons.append(
                "The project has enough grounded information for preliminary solution shaping and delivery planning; remaining unknowns are carried forward as non-blocking questions."
            )
        elif not any(marker in " ".join(reasons).lower() for marker in ("preliminary", "proceed", "ready", "sufficient")):
            reasons.append(
                "The next delivery stage can proceed using explicit assumptions while remaining questions are carried forward as non-blocking follow-ups."
            )
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
2. Do not invent confirmed technologies, cloud providers, architecture components, deployment strategies, or implementation choices.
3. Clearly separate customer-confirmed facts from assumptions and possible options.
4. If you mention a technology or architecture pattern that the customer did not confirm, describe it explicitly as an OPTION or possible approach, never as the current system or selected architecture.
5. Do not infer that the current infrastructure is inadequate, scalable, compliant, or otherwise characterized unless the customer confirmed that fact.
6. Identify integration and technical considerations.
7. Identify delivery risks and dependencies.
8. Produce a practical solution direction suitable for preliminary planning.
"""

    solution = provider.generate_json(
        prompt=prompt,
        schema=SOLUTION_SCHEMA,
    )
    solution = _ground_downstream_artifact(solution, state)

    # Prevent unsupported current-state claims from leaking into downstream artifacts.
    if isinstance(solution.get("assumptions"), list):
        normalized = []
        for item in solution["assumptions"]:
            text = str(item)
            lower = text.lower()
            if "current infrastructure is not scalable enough" in lower:
                text = (
                    "Current infrastructure scalability for Black Friday traffic is unconfirmed "
                    "and must be assessed before the migration approach is finalized."
                )
            if "black friday is a specific date" in lower:
                continue
            normalized.append(text)
        solution["assumptions"] = normalized

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
    """Produce the independent standard/human-only delivery estimate.

    AI optimization is deliberately NOT part of this stage. It is an explicit
    user-triggered action so the standard estimate remains a clean reference.
    """
    discovery = state["discovery"]
    requirements = state["requirements"]
    solution = state["solution"]
    delivery_plan = state["delivery_plan"]
    clarification_context = _clarification_context(state)

    prompt = f"""
You are a senior Delivery Manager preparing a preliminary STANDARD delivery estimate.

This estimate is the independent expert baseline for a traditional human-led
 delivery approach. Do NOT optimize it with AI. Do NOT make it fit a customer
deadline. Do NOT use AI acceleration, automation, reduced handoffs, or special
parallelism as hidden assumptions.

CUSTOMER DISCOVERY:
{discovery}

REQUIREMENTS:
{requirements}

SOLUTION:
{solution}

DELIVERY PLAN:
{delivery_plan}

{clarification_context}

Produce only the standard estimate.

IMPORTANT:
1. This is an indicative planning range, not a contractual commitment.
2. Provide a range, not false precision.
3. State assumptions and material risks.
4. Confidence must reflect unresolved delivery-critical information.
5. Never describe unresolved areas as fully defined or well understood.
6. Preserve customer-provided estimates as customer facts; do not replace them
   with your own estimate and do not treat your estimate as a correction.
7. If the customer estimate materially differs from your independent estimate,
   explain the variance without silently reconciling the numbers.
8. The customer deadline is a constraint for later comparison, not a target that
   should distort this standard estimate.
9. Effort must be expressed as person-days/person-hours (or another explicit effort unit),
   never as months or weeks. Duration is expressed separately.
10. Do not produce an AI-optimized scenario in this response.
"""

    estimate = provider.generate_json(prompt=prompt, schema=ESTIMATE_SCHEMA)
    if not isinstance(estimate, dict):
        estimate = {}

    customer_estimated_months = _parse_customer_estimated_months(
        discovery.get("constraints", [])
    )
    deadline_months = _parse_deadline_months(discovery.get("constraints", []))

    customer_baseline_text = (
        f"{customer_estimated_months:g} months"
        if customer_estimated_months is not None else ""
    )
    customer_deadline_text = (
        f"{deadline_months:g} month" + ("" if deadline_months == 1 else "s")
        if deadline_months is not None else ""
    )

    # Customer-provided baseline and deadline are metadata, not part of our
    # independent estimate. They remain visible for comparison.
    estimate["customer_baseline_duration"] = customer_baseline_text
    estimate["customer_deadline"] = customer_deadline_text
    estimate["baseline_duration_range"] = str(estimate.get("duration_range") or "").strip()
    estimate["baseline_effort_range"] = str(estimate.get("effort_range") or "").strip()

    # This field belongs to the standard estimate only. Do not allow the model
    # to turn the customer's deadline into an optimization rationale here.
    if customer_estimated_months is not None:
        estimate["baseline_variance_explanation"] = (
            f"The customer-provided estimate is {customer_estimated_months:g} months and is kept "
            "as a separate reference point. The standard estimate is an independent "
            "traditional human-led delivery assessment and is not adjusted to fit the "
            "customer deadline."
        )
    else:
        estimate["baseline_variance_explanation"] = (
            "No customer-provided delivery estimate was identified. The standard estimate "
            "is an independent traditional human-led delivery assessment and is not adjusted "
            "to fit a customer deadline."
        )

    # Compare the standard estimate with the deadline only as a simple factual
    # indicator. This is NOT AI feasibility and does not imply an optimized plan.
    standard_max_weeks = _parse_max_weeks(estimate.get("duration_range", ""))
    if deadline_months is None or standard_max_weeks is None:
        estimate["standard_deadline_fit"] = "NOT_DEMONSTRATED"
    elif standard_max_weeks <= deadline_months * 4.345:
        estimate["standard_deadline_fit"] = "FITS"
    else:
        estimate["standard_deadline_fit"] = "EXCEEDS"

    estimate = _ground_downstream_artifact(estimate, state)

    open_questions = (state.get("requirements", {}) or {}).get("open_questions", []) or []
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
            text = str(item).strip()
            lower = text.lower()
            if "security and compliance requirements are well understood" in lower or "security and compliance requirements are fully understood" in lower:
                text = (
                    "The security and compliance baseline is based on current customer input; "
                    "detailed technical controls may require refinement during solution design."
                )
            elif "black friday is a specific date" in lower:
                continue
            # Customer estimates are facts, not assumptions in our model.
            if "3-month estimate is accurate" in lower or "3 months estimate is accurate" in lower:
                continue
            # Do not let deadline-fitting tactics leak into the standard estimate.
            # Capacity increases, phased delivery, and similar acceleration tactics
            # belong to the explicit AI optimization scenario or later trade-off analysis.
            if (
                ("additional resources" in lower or "increase resources" in lower or "more resources" in lower)
                and ("within one month" in lower or "within 1 month" in lower or "deadline" in lower)
            ):
                continue
            if "phased approach" in lower and ("deadline" in lower or "within one month" in lower or "within 1 month" in lower):
                continue
            if text and text not in normalized_assumptions:
                normalized_assumptions.append(text)
        estimate["assumptions"] = normalized_assumptions

    # Effort must remain an effort unit; duration must not leak into effort.
    estimate["effort_range"] = _normalize_effort_range(estimate.get("effort_range"))

    # Reassert immutable comparison fields after grounding/normalization.
    estimate["customer_baseline_duration"] = customer_baseline_text
    estimate["customer_deadline"] = customer_deadline_text
    estimate["baseline_duration_range"] = str(estimate.get("duration_range") or "").strip()
    estimate["baseline_effort_range"] = str(estimate.get("effort_range") or "").strip()

    return {"estimate": estimate}


def ai_optimization_agent(
    state: DeliveryState,
    provider: AIProvider,
) -> dict:
    """Create an explicit AI-native delivery optimization scenario."""
    discovery = state.get("discovery", {}) or {}
    requirements = state.get("requirements", {}) or {}
    solution = state.get("solution", {}) or {}
    delivery_plan = state.get("delivery_plan", {}) or {}
    estimate = state.get("estimate", {}) or {}
    clarification_context = _clarification_context(state)

    customer_baseline = str(estimate.get("customer_baseline_duration") or "").strip()
    if not customer_baseline:
        customer_months = _parse_customer_estimated_months(discovery.get("constraints", []))
        if customer_months is not None:
            customer_baseline = f"{customer_months:g} months"

    customer_deadline = str(estimate.get("customer_deadline") or "").strip()
    if not customer_deadline:
        deadline_months = _parse_deadline_months(discovery.get("constraints", []))
        if deadline_months is not None:
            customer_deadline = f"{deadline_months:g} month" + ("" if deadline_months == 1 else "s")
    standard_duration = str(
        estimate.get("baseline_duration_range") or estimate.get("duration_range") or ""
    ).strip()
    standard_effort = str(
        estimate.get("baseline_effort_range") or estimate.get("effort_range") or ""
    ).strip()

    prompt = f"""
You are a senior Delivery Manager and AI-native delivery strategist.

The user explicitly requested an AI DELIVERY OPTIMIZATION analysis.
Create a THIRD, SEPARATE delivery scenario. Do not rewrite or replace the
standard estimate.

THREE DISTINCT REFERENCE POINTS:
A) Customer estimate: {customer_baseline or "not provided"}
B) Our standard human-only estimate: {standard_duration or "not available"}
C) Your AI-optimized scenario: produce this now

CUSTOMER DEADLINE: {customer_deadline or "not provided"}

DISCOVERY:
{discovery}

REQUIREMENTS:
{requirements}

SOLUTION:
{solution}

DELIVERY PLAN:
{delivery_plan}

STANDARD ESTIMATE:
{estimate}

{clarification_context}

Rules:
1. The customer estimate is reference information only. Never treat it as our
   estimate or as an accepted target.
2. The standard estimate is immutable. Do not rewrite it.
3. The AI-optimized scenario must be independently reasoned from the actual
   workstreams, sequencing, automation opportunities and delivery constraints.
4. Do not use a magic percentage such as "AI makes it 50% faster".
5. AI leverage can be high for migration scripts, IaC, boilerplate, test
   generation, documentation, analysis, repetitive configuration and similar
   automatable work.
6. AI leverage is low for architecture decisions, security/compliance approval,
   stakeholder decisions, production cutover, final validation and operational readiness.
7. Use parallelism only where work can genuinely overlap.
8. Do not invent cloud providers, technologies, traffic volumes, SLA targets,
   team size, budget or dates that are not supported by the project.
9. The optimized duration does NOT have to meet the customer deadline.
10. If the optimized scenario is still longer than the customer deadline,
    explicitly calculate the delivery gap and identify realistic scope/capacity/
    sequencing trade-offs that could close it. Do not pretend the deadline is met.
11. Scope trade-offs must only propose removing/de-scoping capabilities that are
    actually present in the requirements or solution. Never invent functionality.
12. FEASIBLE means the optimized duration fits the customer deadline with credible
    evidence. FEASIBLE_WITH_CONDITIONS means it fits but depends materially on the
    listed conditions. NOT_DEMONSTRATED means the evidence is insufficient.
13. If no customer deadline is available, use NOT_APPLICABLE for deadline_feasibility
    and focus on acceleration potential.
14. Keep effort and duration as ranges and keep confidence honest.
15. Effort must be expressed as person-days/person-hours (or another explicit effort unit),
    never as months or weeks. Duration is expressed separately.
"""

    optimized = provider.generate_json(
        prompt=prompt,
        schema=AI_OPTIMIZATION_SCHEMA,
    )
    if not isinstance(optimized, dict):
        optimized = {}

    import re

    def clean_list(value):
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    optimization_levers = clean_list(optimized.get("optimization_levers"))
    feasibility_conditions = clean_list(optimized.get("feasibility_conditions"))
    scope_tradeoffs = clean_list(optimized.get("scope_tradeoffs"))
    recommendations = clean_list(optimized.get("recommendations"))

    # Do not let the optimizer turn an unresolved scope question into a confirmed
    # scenario. The model may use examples from the open questions as if they were
    # facts (for example, assuming the migration is specifically a cloud-provider
    # migration). Keep such proposals explicitly conditional.
    def normalize_unsupported_scope_statement(item: str) -> str:
        lower = item.lower()
        if (
            "cloud provider migration" in lower
            or "cloud-provider migration" in lower
            or "without codebase refactoring" in lower
            or "without refactoring" in lower
            or "remove code refactoring" in lower
            or "limit migration to cloud" in lower
            or "limit the migration to cloud" in lower
        ):
            return (
                "Evaluate whether migration scope can be reduced, phased, or parallelized "
                "to close the deadline gap, subject to explicit scope confirmation."
            )
        return item

    feasibility_conditions = [
        normalize_unsupported_scope_statement(item)
        for item in feasibility_conditions
    ]
    recommendations = [
        normalize_unsupported_scope_statement(item)
        for item in recommendations
    ]

    # Do not let the optimizer invent team size or an "AI orchestrator" role.
    # Team capacity is a planning input unless the customer supplied it.
    team_model = str(optimized.get("optimization_team_model") or "").strip()
    team_model_lower = team_model.lower()
    invented_team_markers = (
        "ai orchestrator", "ai specialist", "ai specialists",
        "2–3", "2-3", "3–4", "3-4", "4–5", "4-5",
        "additional engineers", "additional developers",
    )
    headcount_pattern = re.compile(
        r"\b\d+(?:\s*[–-]\s*\d+)?\s+(?:architects?|developers?|engineers?|qa|qa engineers?|devops|specialists?|people|fte)\b",
        re.I,
    )
    if any(marker in team_model_lower for marker in invented_team_markers) or headcount_pattern.search(team_model):
        team_model = (
            "AI-assisted delivery using the existing delivery team; exact team capacity "
            "and any additional staffing are not established."
        )

    # Scope trade-offs are optional. Do not recommend weakening safety/quality controls
    # or invent percentage reductions. Such changes require explicit scope evidence.
    unsafe_tradeoff_markers = (
        "manual testing", "reduce testing", "simplify rollback",
        "limit infrastructure assessment", "reduce rollback",
    )
    percentage_pattern = re.compile(r"\b\d+(?:\.\d+)?%\b")
    filtered_tradeoffs = []
    for item in scope_tradeoffs:
        lower = item.lower()
        if percentage_pattern.search(item) or any(marker in lower for marker in unsafe_tradeoff_markers):
            continue
        filtered_tradeoffs.append(item)
    scope_tradeoffs = filtered_tradeoffs

    result = {
        "duration_range": str(optimized.get("duration_range") or "").strip(),
        "effort_range": str(optimized.get("effort_range") or "").strip(),
        "confidence": str(optimized.get("confidence") or "LOW").strip().upper(),
        "optimization_summary": str(optimized.get("optimization_summary") or "").strip(),
        "optimization_levers": optimization_levers,
        "feasibility_conditions": feasibility_conditions,
        "optimization_team_model": team_model,
        "deadline_feasibility": str(optimized.get("deadline_feasibility") or "NOT_DEMONSTRATED").strip().upper(),
        "deadline_gap": str(optimized.get("deadline_gap") or "").strip(),
        "scope_tradeoffs": scope_tradeoffs,
        "recommendations": recommendations,
        "customer_baseline_duration": customer_baseline,
        "customer_deadline": customer_deadline,
        "standard_duration_range": standard_duration,
        "standard_effort_range": standard_effort,
    }

    result["effort_range"] = _normalize_effort_range(result["effort_range"])

    if result["confidence"] not in {"LOW", "MEDIUM", "HIGH"}:
        result["confidence"] = "LOW"
    if result["deadline_feasibility"] not in {
        "FEASIBLE", "FEASIBLE_WITH_CONDITIONS", "NOT_DEMONSTRATED", "NOT_APPLICABLE"
    }:
        result["deadline_feasibility"] = "NOT_DEMONSTRATED"

    optimized_max_weeks = _parse_max_weeks(result["duration_range"])
    deadline_months = _parse_deadline_months(
        discovery.get("constraints", [])
    )
    if deadline_months is None:
        result["deadline_feasibility"] = "NOT_APPLICABLE"
        result["deadline_gap"] = ""
    elif optimized_max_weeks is None:
        result["deadline_feasibility"] = "NOT_DEMONSTRATED"
    else:
        deadline_weeks = deadline_months * 4.345
        if optimized_max_weeks <= deadline_weeks:
            if result["feasibility_conditions"]:
                result["deadline_feasibility"] = "FEASIBLE_WITH_CONDITIONS"
            else:
                result["deadline_feasibility"] = "FEASIBLE"
            result["deadline_gap"] = "0"
        else:
            result["deadline_feasibility"] = "NOT_DEMONSTRATED"
            result["deadline_gap"] = (
                f"approximately {optimized_max_weeks - deadline_weeks:.1f} weeks"
            )

    if not result["optimization_levers"]:
        result["deadline_feasibility"] = (
            "NOT_APPLICABLE" if deadline_months is None else "NOT_DEMONSTRATED"
        )
        result["optimization_summary"] = (
            result["optimization_summary"]
            or "No credible AI acceleration scenario was demonstrated because no concrete optimization levers were identified."
        )

    # Keep the narrative consistent with the deterministic deadline result.
    # In particular, never let model text claim that the deadline is feasible when
    # the calculated worst-case optimized duration is still longer than the deadline.
    if result["deadline_feasibility"] == "NOT_DEMONSTRATED":
        result["optimization_summary"] = (
            "The AI-optimized scenario may materially reduce delivery duration through "
            "the identified automation and parallelization levers, but the current "
            "duration range does not demonstrate that the customer deadline can be met. "
            "Closing the remaining gap requires explicit scope, sequencing, or capacity "
            "decisions supported by project evidence."
        )

    # Never allow the optimizer to silently mutate the standard estimate.
    return {"ai_optimization": result}


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
6. If the customer deadline is shorter than the baseline estimate and
   deadline_feasibility is NOT_DEMONSTRATED, do NOT describe the deadline
   as an achieved delivery commitment. Present it as the customer's target
   and clearly distinguish it from the current indicative baseline.
7. If an AI-optimized scenario is explicitly provided and marked
   FEASIBLE_WITH_CONDITIONS, describe it as a conditional accelerated option,
   not a guaranteed commitment.
"""

    proposal = provider.generate_json(
        prompt=prompt,
        schema=PROPOSAL_SCHEMA,
    )
    proposal = _ground_downstream_artifact(proposal, state)

    # Do not let a preliminary proposal turn an unproven accelerated target
    # into a delivery commitment. Keep the customer target visible, but make
    # the current baseline and feasibility status explicit.
    if isinstance(proposal, dict) and estimate.get("deadline_feasibility") == "NOT_DEMONSTRATED":
        customer_deadline = str(estimate.get("customer_deadline") or "")
        baseline_duration = str(estimate.get("baseline_duration_range") or estimate.get("duration_range") or "")
        if customer_deadline and baseline_duration:
            proposal["timeline"] = (
                f"Customer target: {customer_deadline}; current indicative baseline: "
                f"{baseline_duration}. AI-optimized feasibility is not yet demonstrated."
            )
        if isinstance(proposal.get("executive_summary"), str):
            summary = proposal["executive_summary"]
            lowered = summary.lower()
            commitment_markers = (
                "complete within one month",
                "completed within one month",
                "migration within one month",
                "within 1 month",
            )
            if any(marker in lowered for marker in commitment_markers):
                proposal["executive_summary"] = (
                    summary + " The one-month customer target remains subject to an "
                    "AI-optimized delivery scenario and feasibility validation; it is not "
                    "yet demonstrated by the current baseline."
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

    if isinstance(sow, dict) and estimate.get("deadline_feasibility") == "NOT_DEMONSTRATED":
        customer_deadline = str(estimate.get("customer_deadline") or "")
        baseline_duration = str(estimate.get("baseline_duration_range") or estimate.get("duration_range") or "")
        if customer_deadline and baseline_duration:
            sow["timeline"] = (
                f"Customer target: {customer_deadline}; current indicative baseline: "
                f"{baseline_duration}. Accelerated feasibility is not yet demonstrated."
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
        "scope",
        "constraints",
    )
    values = [discovery.get(key, "") for key in confirmed_keys]
    return " ".join(str(value) for value in values).lower()


def _scope_item_to_requirements(scope_item: str) -> list[str]:
    """Convert explicit customer capabilities into minimal functional requirements."""
    text = str(scope_item or "").strip().rstrip(".")
    match = re.match(r"^customers?\s+can\s+(.+)$", text, re.I)
    if match:
        capabilities = match.group(1).strip()
        parts = re.split(r",\s*|\s+and\s+", capabilities, flags=re.I)
        parts = [part.strip() for part in parts if part.strip()]
        # Only split a compound list when all resulting parts are short capability
        # phrases; otherwise preserve the original customer statement verbatim.
        if len(parts) >= 2 and len(parts) <= 6:
            return [f"The portal shall allow customers to {part}." for part in parts]
        return [f"The portal shall allow customers to {capabilities}."]
    match = re.match(r"^users?\s+can\s+(.+)$", text, re.I)
    if match:
        return [f"The portal shall allow users to {match.group(1).strip()}."]
    return [f"The portal shall support {text[0].lower() + text[1:] if text else text}."]


def _extract_explicit_scope_items(request: str) -> list[str]:
    """Extract explicitly labelled customer scope without inventing capabilities."""
    text = str(request or "")
    match = re.search(
        r"(?:^|\n)\s*scope\s*:\s*(.*?)(?=\n\s*\n|\n\s*(?:business goal|users|stakeholders|existing systems|authentication|security|target delivery timeline|delivery timeline|target timeline|target)\s*:|\Z)",
        text,
        re.I | re.S,
    )
    if not match:
        return []

    block = match.group(1).strip()
    if not block:
        return []

    # Scope statements are sometimes wrapped across multiple lines. Join those
    # lines first so a single customer capability is not split accidentally.
    normalized = " ".join(
        re.sub(r"^\s*[-*]\s*", "", line).strip()
        for line in block.splitlines()
        if line.strip()
    )

    items: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+|\s*;\s*", normalized):
        item = part.strip().rstrip(".")
        if item and item.lower() not in {existing.lower() for existing in items}:
            items.append(item)
    return items


def _extract_explicit_timeline_facts(request: str) -> list[str]:
    """Extract explicit customer timeline statements for provenance preservation."""
    import re

    text = str(request or "")
    facts: list[str] = []

    estimate_match = re.search(
        r"([^.!?\n]{0,160}\b(?:estimated|estimate)\b[^.!?\n]{0,100}\b\d+(?:\.\d+)?\s*months?[^.!?\n]*)",
        text,
        re.I,
    )
    if estimate_match:
        sentence = re.sub(r"\s+", " ", estimate_match.group(1)).strip(" ,;:")
        if sentence:
            facts.append(sentence)

    deadline_match = re.search(
        r"\bwithin\s+(\d+(?:\.\d+)?)\s*months?\b",
        text,
        re.I,
    )
    if deadline_match:
        facts.append(f"Customer requires completion within {deadline_match.group(1)} month(s).")

    target_timeline_match = re.search(
        r"\b(?:target\s+delivery\s+timeline|delivery\s+timeline|target\s+timeline|target)\s*[:=-]?\s*"
        r"(\d+(?:\.\d+)?)\s*months?\b",
        text,
        re.I,
    )
    if target_timeline_match:
        facts.append(
            f"Customer target delivery timeline is {target_timeline_match.group(1)} month(s)."
        )

    explicit_completion_match = re.search(
        r"\b(?:launch|complete|completion|deliver|delivery)\s+(?:by|within)\s+"
        r"(\d+(?:\.\d+)?)\s*months?\b",
        text,
        re.I,
    )
    if explicit_completion_match and not deadline_match:
        facts.append(
            f"Customer requires completion within {explicit_completion_match.group(1)} month(s)."
        )

    return facts


def _parse_max_weeks(duration_text: str) -> float | None:
    """Extract the largest duration value and normalize it to weeks."""
    import re

    text = str(duration_text or "").lower().replace("–", "-").replace("—", "-")

    def to_weeks(value: float, unit: str) -> float:
        if unit.startswith("day"):
            return value / 7.0
        if unit.startswith("month"):
            return value * 4.345
        return value

    range_pattern = (
        r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*"
        r"(\d+(?:\.\d+)?)\s*(days?|weeks?|months?)"
    )
    matches = re.findall(range_pattern, text)
    if matches:
        return max(to_weeks(float(high), unit) for _, high, unit in matches)

    single = re.findall(r"(\d+(?:\.\d+)?)\s*(days?|weeks?|months?)", text)
    if single:
        return max(to_weeks(float(value), unit) for value, unit in single)

    return None


def _parse_customer_estimated_months(constraints: list[str]) -> float | None:
    """Extract the customer's stated baseline estimate separately from the deadline."""
    import re

    for item in constraints or []:
        text = str(item).lower()

        # Common form: "within 1 month instead of 3 months estimated by developers".
        match = re.search(
            r"instead of\s+(\d+(?:\.\d+)?)\s*months?\s+estimated",
            text,
        )
        if match:
            return float(match.group(1))

        # Common form: "developers estimated 3 months" / "estimated at 3 months".
        match = re.search(
            r"\bestimat(?:e|ed)\b[^0-9]{0,100}"
            r"(\d+(?:\.\d+)?)\s*months?",
            text,
        )
        if match:
            return float(match.group(1))

        # Also handle "3 months estimated by developers".
        match = re.search(
            r"(\d+(?:\.\d+)?)\s*months?\s+estimated(?:\s+by)?",
            text,
        )
        if match:
            return float(match.group(1))

    return None


def _parse_deadline_months(constraints: list[str]) -> float | None:
    """Extract the required deadline, excluding the customer's baseline estimate."""
    import re

    values: list[float] = []
    for item in constraints or []:
        text = str(item).lower()
        match = re.search(
            r"(?:within|by|deadline(?: is)?|complete(?:d)? by|"
            r"target\s+delivery\s+timeline(?:\s+is)?|"
            r"delivery\s+timeline(?:\s+is)?|"
            r"target\s+timeline(?:\s+is)?|"
            r"target(?:\s+delivery)?(?:\s+timeline)?(?:\s+is)?)[^0-9]{0,40}"
            r"(\d+(?:\.\d+)?)\s*months?",
            text,
        )
        if match:
            values.append(float(match.group(1)))
            continue
        if "estimated" in text:
            prefix = text.split("estimated", 1)[0]
            match = re.search(r"(\d+(?:\.\d+)?)\s*months?", prefix)
            if match:
                values.append(float(match.group(1)))
    return min(values) if values else None


def _normalize_effort_range(value: object) -> str:
    """Reject duration-like effort values that cannot be interpreted as effort."""
    import re

    text = str(value or "").strip()
    if not text:
        return ""
    lower = text.lower()
    has_effort_unit = bool(re.search(r"\b(person[- ]?days?|person[- ]?hours?|hours?|pd|days?)\b", lower))
    has_duration_unit = bool(re.search(r"\b(weeks?|months?|minutes?)\b", lower))
    if has_duration_unit and not has_effort_unit:
        return "Not reliably estimable from current information"
    return text


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

    # 1. Deadline feasibility is an assessment, not an automatic customer blocker.
    deadline_months = _parse_deadline_months(discovery.get("constraints", []))
    estimate_max_weeks = _parse_max_weeks(estimate.get("duration_range", ""))
    customer_baseline_months = _parse_customer_estimated_months(discovery.get("constraints", []))

    if deadline_months is not None and estimate_max_weeks is not None:
        deadline_weeks = deadline_months * 4.345
        if customer_baseline_months is not None and customer_baseline_months > deadline_months:
            if (estimate.get("deadline_constrained") and
                    estimate.get("deadline_feasibility") == "FEASIBLE_WITH_CONDITIONS"):
                checks.append(
                    "Customer baseline exceeds the deadline; an explicit AI-optimized scenario "
                    "has been evaluated separately."
                )
            else:
                warnings.append(
                    "Customer baseline exceeds the deadline. Deadline feasibility is not demonstrated "
                    "by the current delivery scenario; an explicit AI-optimized scenario is required "
                    "before claiming the target is achievable."
                )
        elif estimate_max_weeks > deadline_weeks:
            warnings.append(
                "The current AI delivery scenario exceeds the explicit customer deadline; "
                "this is a feasibility risk, not by itself a customer clarification blocker."
            )
        else:
            checks.append("The current delivery scenario does not exceed the explicit customer deadline.")
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
    ai_optimization = state.get("ai_optimization")

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
3. Flag as BLOCKING a demonstrated deadline infeasibility, not merely an
   unresolved implementation option. If the estimate was explicitly
   recalculated to fit a customer deadline, distinguish that deadline-
   constrained scenario from the original baseline estimate.
3a. When the customer supplied a baseline estimate that is longer than the
   required deadline, review must explicitly assess the gap between that
   baseline and the deadline. A shorter independent AI estimate does NOT by
   itself prove feasibility. Look for an explicit AI-optimized scenario and
   its assumptions, workstream-level AI leverage, parallelism, and human-gated
   activities. If feasibility cannot be demonstrated, record a WARNING.
   IMPORTANT: AI optimization is an optional user-triggered analysis. The
   absence of an AI-optimized scenario in the standard Analyze Request flow
   is NOT deadline infeasibility and MUST NOT create a customer clarification
   blocker. Standard review should report the deadline gap as a warning only.
4. Check that effort and duration are at least plausibly consistent
   with the delivery plan; flag a material mismatch as BLOCKING.
5. Estimates remain indicative, but must be internally coherent.
6. Unresolved detail that can safely remain an assumption is a warning,
   not a blocker.
7. Do not invent missing facts while reviewing.
8. Objective feasibility uncertainty alone does not block the workflow. BLOCKED is
   reserved for demonstrated infeasibility or a concrete customer decision that
   is required before meaningful next-stage work can proceed.
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

    blocking_issues = []
    warnings = list(review.get("warnings", []))
    checks = list(review.get("checks", []))
    deadline_review_removed = False
    for issue in (review.get("blocking_issues", []) or []):
        text = str(issue).strip()
        lower = text.lower()
        deadline_related = (
            "deadline" in lower
            and (
                "customer baseline" in lower
                or "customer requires" in lower
                or "estimate" in lower
                or "ai-optimized" in lower
                or "ai optimized" in lower
                or "feasibility" in lower
            )
        )

        # The standard Analyze Request flow does not run AI optimization.
        # Therefore a gap between the standard estimate and customer deadline
        # is an assessment/warning, not a customer blocker. Only the explicit
        # Optimize with AI action can produce a deadline-feasibility blocker.
        if not ai_optimization and deadline_related:
            deadline_review_removed = True
            continue

        blocking_issues.append(text)

    clarification_questions = list(review.get("clarification_questions", []))
    if not ai_optimization:
        filtered_questions = []
        for question in clarification_questions:
            if not isinstance(question, dict):
                filtered_questions.append(question)
                continue
            question_text = str(question.get("question") or question.get("text") or "").strip()
            reason_text = str(question.get("reason") or "").lower()
            combined = f"{question_text.lower()} {reason_text}"
            deadline_question = (
                "deadline" in combined
                or "timeline" in combined
            ) and (
                "3 months" in combined
                or "customer baseline" in combined
                or "estimate" in combined
                or "ai-optimized" in combined
                or "ai optimized" in combined
                or "one-month" in combined
                or "1-month" in combined
            )
            if deadline_question:
                deadline_review_removed = True
                continue
            filtered_questions.append(question)
        clarification_questions = filtered_questions

    if deadline_review_removed:
        warnings.append(
            "The standard delivery estimate does not demonstrate the customer's target deadline. "
            "AI optimization is optional and must be run separately before assessing whether AI-native "
            "delivery can close the remaining deadline gap."
        )
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
