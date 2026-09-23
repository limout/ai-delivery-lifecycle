import logging
import re
from app.providers import AIProvider
from app.state import DeliveryState
from app.evidence import (
    clarification_answer_body,
    customer_authored_text,
    has_substantive_first_release_scope_answer,
    is_estimable,
    is_non_substantive_clarification_answer,
    material_evidence_gaps,
)
from app.timeline import (
    WEEKS_PER_MONTH,
    deadline_source_texts,
    parse_customer_estimate,
    parse_requested_deadline,
)

_log = logging.getLogger("app.agents")


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

    for item in state.get("new_clarification_records", []) or []:
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

    if has_substantive_first_release_scope_answer(state):
        topics.add("first_release_scope")

    for record in _clarification_records(state):
        question, body = _record_question_and_answer(record)
        if is_non_substantive_clarification_answer(body):
            continue
        if _question_topic(question) == "deadline_type":
            topics.add("deadline_type")
            break

    return topics


def _is_penalty_only_question(text: str) -> bool:
    """True for penalty/LD follow-ups, not target-vs-contractual combo questions."""
    t = str(text or "").lower()
    if "penalt" not in t and "liquidated" not in t:
        return False
    if any(marker in t for marker in (
        "flexible",
        "internal target",
        "planning date",
        "planning target",
    )):
        return False
    if "target" in t and "contractual" in t:
        return False
    return True


def _is_deadline_type_question(text: str) -> bool:
    """True when the question asks whether a known date is binding vs a target."""
    t = str(text or "").lower()
    if _is_penalty_only_question(t):
        return False
    has_date = bool(re.search(
        r"\b(deadline|date|2-month|two-month|2 month|two month)\b",
        t,
    ))
    has_nature = any(marker in t for marker in (
        "contractual",
        "binding",
        "flexible",
        "internal target",
        "planning date",
        "planning target",
    ))
    return has_date and has_nature


def _question_topic(question: str) -> str | None:
    """Map a clarification question to the canonical topic it resolves."""
    text = str(question or "").lower()

    if any(marker in text for marker in (
        "first release", "first-release", "in scope", "out of scope",
        "main capabilities", "core function",
    )):
        return "first_release_scope"
    if _is_deadline_type_question(text):
        return "deadline_type"
    if any(marker in text for marker in (
        "security", "compliance", "data privacy", "privacy requirements", "regulatory"
    )):
        return "security_compliance"
    if any(marker in text for marker in (
        "user volume", "expected user volume", "traffic", "concurrent users",
        "concurrent load",
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


def _normalize_question_text(text: str) -> str:
    """Normalize question text for exact answered-question matching."""
    return re.sub(r"\s+", " ", str(text or "").strip()).casefold()


_INTERROGATIVE_PREFIXES = (
    "what is the ",
    "what are the ",
    "whether ",
    "is the ",
)
_SINGLETON_OPTIONAL_TOPICS = frozenset({"deadline_type"})
VOLUME_FOLLOW_UP_QUESTION = (
    "What is the expected user volume and concurrent load for the web application?"
)
ROLES_FOLLOW_UP_QUESTION = "What are the expected user roles and permissions?"


def _question_dedup_key(text: str) -> str:
    """Deterministic stem key: normalized text without a safe interrogative wrapper."""
    key = _normalize_question_text(text)
    if key.endswith("?"):
        key = key[:-1].rstrip()
    for prefix in _INTERROGATIVE_PREFIXES:
        if key.startswith(prefix):
            key = key[len(prefix):].rstrip()
            break
    return key


def _coalesce_optional_questions(questions: list, state: DeliveryState) -> list:
    """Exact, stem, and singleton-topic dedup for optional questions. Keep first."""
    answered_topics = _answered_clarification_topics(state)
    result = []
    seen_lower = set()
    seen_stems = set()
    seen_singleton = set()
    for item in questions or []:
        question = str(item or "").strip()
        if not question:
            continue
        lower = question.lower()
        if lower in seen_lower:
            continue
        stem = _question_dedup_key(question)
        if stem and stem in seen_stems:
            continue
        topic = _question_topic(question)
        if topic in _SINGLETON_OPTIONAL_TOPICS:
            if topic in answered_topics or topic in seen_singleton:
                continue
        result.append(question)
        seen_lower.add(lower)
        if stem:
            seen_stems.add(stem)
        if topic in _SINGLETON_OPTIONAL_TOPICS:
            seen_singleton.add(topic)
    return result


def _split_legacy_clarification_blob(blob: str) -> tuple[str, str]:
    """Recover question/answer from the UI string `${questionText}: ${answer}`."""
    text = str(blob or "").strip()
    if not text:
        return "", ""
    # Prefer "?: " so colons inside the question (for example S/4HANA notes)
    # are not treated as the answer separator. Questions from the UI end with ?.
    marker = "?: "
    index = text.rfind(marker)
    if index != -1:
        return text[: index + 1].strip(), text[index + len(marker) :].strip()
    marker = ": "
    index = text.rfind(marker)
    if index != -1:
        question = text[:index].strip()
        answer = text[index + len(marker) :].strip()
        if question and answer:
            return question, answer
    return "", text


def _record_question_and_answer(record: dict) -> tuple[str, str]:
    """Return the real question/answer, unpacking legacy UI history rows."""
    question = str(record.get("question") or "").strip()
    answer = str(record.get("answer") or "").strip()
    placeholder = _normalize_question_text(question) in {"", "customer clarification"}
    if placeholder:
        inner_question, inner_answer = _split_legacy_clarification_blob(answer)
        if inner_question:
            return inner_question, inner_answer
        return question, answer
    return question, clarification_answer_body(question, answer)


def _answered_question_texts(state: DeliveryState) -> set[str]:
    """Questions that already have a substantive customer answer."""
    answered: set[str] = set()
    for record in _clarification_records(state):
        question, body = _record_question_and_answer(record)
        normalized = _normalize_question_text(question)
        if not normalized:
            continue
        if is_non_substantive_clarification_answer(body):
            continue
        answered.add(normalized)
    return answered


def _filter_answered_questions(questions: list, state: DeliveryState) -> list:
    """Remove questions already answered by topic or exact question text."""
    answered_topics = _answered_clarification_topics(state)
    answered_texts = _answered_question_texts(state)
    if not answered_topics and not answered_texts:
        return list(questions or [])

    filtered = []
    for item in questions or []:
        text = item.get("question") if isinstance(item, dict) else str(item)
        if _normalize_question_text(text) in answered_texts:
            continue
        topic = _question_topic(text)
        if topic and topic in answered_topics:
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


def _discovery_reference_section(query: str) -> str:
    """Append knowledge-base excerpts only when RAG is enabled and results exist.

    Retrieval failures are logged and ignored so /analyze still returns JSON.
    Retrieved text is never written into discovery structured fields here.
    """
    try:
        from app.rag.config import rag_enabled

        enabled = rag_enabled()
        print(f"[RAG] discovery enabled={enabled}")
        if not enabled:
            return ""
        from app.rag.retrieve import format_reference_section, retrieve_relevant_context

        chunks = retrieve_relevant_context(query)
        refs = [
            f"{item.title or item.document_id}:{item.chunk_index}"
            for item in chunks
        ]
        print(f"[RAG] discovery chunks={len(chunks)} refs={refs}")
        section = format_reference_section(chunks)
        print(
            f"[RAG] discovery excerpts_appended={bool(section)} "
            f"prompt_extra_chars={len(section)}"
        )
        return section
    except Exception:
        _log.exception("RAG retrieval failed; discovery continues without reference excerpts")
        return ""


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
9. Never state or imply that the current infrastructure is inadequate,
   not scalable, or otherwise deficient unless the customer explicitly
   confirmed that fact. If scalability for Black Friday traffic is unknown,
   record it as unconfirmed/unknown rather than as an assumption presented
   as fact.

Original customer request:

{request}

{clarification_context}
"""

    rag_section = _discovery_reference_section(request)
    if rag_section:
        prompt = f"{prompt.rstrip()}\n\n{rag_section}\n"

    discovery = provider.generate_json(
        prompt=prompt,
        schema=DISCOVERY_SCHEMA,
    )
    # Preserve explicit customer timeline facts even if the discovery model omits
    # them from structured constraints. These facts are authoritative provenance
    # for the estimation stage.
    explicit_timeline_facts = _extract_explicit_timeline_facts(
        customer_authored_text(state) or request
    )
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

    # Some model-generated "contradictions" are actually non-blocking
    # refinement questions. In particular, a customer statement such as
    # "simple and easy to use" is a valid high-level UX goal; the absence of
    # a detailed design system or measurable UX criteria does not prevent
    # preliminary solution shaping or delivery planning.
    normalized_contradictions = []
    normalized_open_questions = list(grounded["open_questions"])
    for item in grounded["contradictions"]:
        text = str(item).strip()
        lower = text.lower()
        is_non_blocking_ux_gap = (
            ("simple and easy to use" in lower or "easy to use" in lower)
            and any(
                marker in lower
                for marker in (
                    "ux/ui", "ui/ux", "ux", "ui", "design system",
                    "guidelines", "specific", "test", "criteria",
                )
            )
            and any(
                marker in lower
                for marker in (
                    "no specific", "not provided", "not specified",
                    "no ", "lack", "without", "there are no",
                )
            )
        )
        # A high-level feature scope and an unresolved sub-scope are not a
        # contradiction. For example, knowing that the portal can submit
        # service requests while the exact request types are still TBD is
        # sufficient for preliminary solution shaping.
        is_non_blocking_scope_gap = (
            any(marker in lower for marker in (
                "service requests", "service request", "initial mvp", "mvp scope"
            ))
            and any(marker in lower for marker in (
                "unknown", "undetermined", "undetermined", "not determined",
                "specific types", "specific type", "which types", "types"
            ))
            and any(marker in lower for marker in (
                "assumes", "assumption", "features", "includes", "scope"
            ))
        )
        # An architectural assumption such as "Salesforce can be integrated using
        # standard APIs" is not contradicted by not yet knowing the exact API
        # endpoint/data-model choice or peak traffic. Those are solution-shaping
        # investigation items. The assumption is explicitly provisional, so it
        # must not become a customer blocker merely because the model wants more
        # technical certainty for the estimate.
        is_non_blocking_technical_gap = (
            any(marker in lower for marker in (
                "salesforce", "entra id", "microsoft entra",
                "standard api", "standard apis", "api integration",
                "integration method", "integration approach",
            ))
            and any(marker in lower for marker in (
                "assumption", "assumes", "unknown", "unknowns",
                "exact api", "exact integration", "integration method",
                "technical certainty", "peak traffic", "concurrency",
            ))
            and any(marker in lower for marker in (
                "not known", "unknown", "undetermined", "uncertain",
                "creates a contradiction", "contradiction",
            ))
        )
        is_non_blocking_contradiction = (
            is_non_blocking_ux_gap
            or is_non_blocking_scope_gap
            or is_non_blocking_technical_gap
        )
        if is_non_blocking_contradiction:
            # Keep the underlying refinement question as non-blocking when it
            # already exists; do not turn a scope clarification into a UX
            # question.
            if is_non_blocking_ux_gap:
                follow_up = (
                    "Are there existing UI/UX design systems or brand guidelines "
                    "the portal should follow, and how should simplicity be evaluated?"
                )
                if follow_up not in normalized_open_questions:
                    normalized_open_questions.append(follow_up)
            continue
        if text and text not in normalized_contradictions:
            normalized_contradictions.append(text)

    grounded["open_questions"] = normalized_open_questions
    grounded["contradictions"] = normalized_contradictions

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

    # Deterministic lifecycle gate.
    #
    # IMPORTANT: LLM-generated questions and contradictions are signals, not
    # routing decisions. A model can reasonably ask for more detail forever.
    # The gate therefore blocks only on objective lifecycle prerequisites that
    # are required before preliminary solution shaping can produce a useful
    # result. Everything else is carried forward as a non-blocking question,
    # assumption, risk, dependency, or investigation item.
    model_questions = [
        str(item).strip()
        for item in (validation.get("questions", []) or [])
        if str(item).strip()
    ]
    model_non_blocking = [
        str(item).strip()
        for item in (validation.get("non_blocking_questions", []) or [])
        if str(item).strip()
    ]

    non_blocking_questions = list(dict.fromkeys(model_non_blocking))
    blocking_questions = []
    existing_questions = {q.lower() for q in non_blocking_questions}

    # Evidence gate: block only on material gaps required for a responsible
    # estimate or deadline assessment. A missing deadline is not by itself a
    # blocker; a known deadline does not make an undefined product estimable.
    evidence_gaps = material_evidence_gaps(state)
    for gap in evidence_gaps:
        if gap.question.lower() not in {q.lower() for q in blocking_questions}:
            blocking_questions.append(gap.question)

    timeline_question = "What is the target delivery timeline?"
    customer_text = " ".join(
        [
            str(state.get("user_request") or ""),
            *[
                str(item.get("answer") or "")
                for item in (state.get("clarification_history", []) or [])
                if isinstance(item, dict)
            ],
            *[str(item) for item in (state.get("clarification_answers", []) or [])],
        ]
    ).lower()
    has_customer_timeline = bool(parse_requested_deadline([customer_text]))
    if not has_customer_timeline and timeline_question.lower() not in existing_questions:
        non_blocking_questions.append(timeline_question)
        existing_questions.add(timeline_question.lower())

    # The validation model may report contradictions, security/compliance
    # questions, technical unknowns, performance questions, or other concerns.
    # None of these is automatically a customer blocker. In particular:
    #   * a high-level scalability goal can be planned with scenarios/ranges;
    #   * missing performance SLAs can be investigated during solution shaping;
    #   * baseline security can be treated as a solution constraint while
    #     specific compliance obligations are investigated;
    #   * integration details are solution-shaping work;
    #   * scope sub-types, UX, RBAC and volume are refinement inputs.
    #
    # Most importantly, an LLM-generated "contradiction" is not evidence of a
    # customer-confirmed conflict. Requirements were already grounded against
    # discovery, so the contradiction field is retained as a diagnostic but
    # does not route the workflow into clarification. This prevents an
    # unbounded loop of one-off phrase exceptions.
    diagnostic_questions = model_questions + [
        str(item).strip()
        for item in (requirements.get("open_questions", []) or [])
        if str(item).strip()
    ] + [
        str(item).strip()
        for item in (discovery.get("unknowns", []) or [])
        if str(item).strip()
    ]

    for question in diagnostic_questions:
        if not question:
            continue
        lower = question.lower()
        if lower not in {q.lower() for q in blocking_questions} and lower not in existing_questions:
            non_blocking_questions.append(question)
            existing_questions.add(lower)

    answered_topics = _answered_clarification_topics(state)
    present_topics = {
        topic
        for topic in (_question_topic(q) for q in non_blocking_questions)
        if topic
    }
    if "user_volume" not in answered_topics and "user_volume" not in present_topics:
        if _filter_answered_questions([VOLUME_FOLLOW_UP_QUESTION], state):
            non_blocking_questions.append(VOLUME_FOLLOW_UP_QUESTION)
    if (
        "roles_permissions" not in answered_topics
        and "roles_permissions" not in present_topics
    ):
        if _filter_answered_questions([ROLES_FOLLOW_UP_QUESTION], state):
            non_blocking_questions.append(ROLES_FOLLOW_UP_QUESTION)

    # A customer-confirmed answer must never be reopened as a blocker.
    answered_topics = _answered_clarification_topics(state)
    gap_questions = {gap.question.lower() for gap in evidence_gaps}
    blocking_questions = [
        q for q in blocking_questions
        if q.lower() in gap_questions
        or not (_question_topic(q) and _question_topic(q) in answered_topics)
    ]

    status = "NEEDS_INFO" if blocking_questions else "READY"
    reasons = [str(item).strip() for item in (validation.get("reasons", []) or []) if str(item).strip()]
    contradictory_ready_markers = (
        "not ready", "not yet ready", "blocking uncertainties",
        "critical missing details", "prevent the next stage",
        "cannot proceed", "must be clarified before",
        "unresolved contradiction", "material customer decisions remain unresolved",
    )
    reasons = [
        r for r in reasons
        if not any(marker in r.lower() for marker in contradictory_ready_markers)
    ]
    if status == "READY":
        if not reasons or not any(
            marker in " ".join(reasons).lower()
            for marker in ("preliminary", "proceed", "ready", "sufficient")
        ):
            reasons.append(
                "The project has enough grounded information for preliminary solution shaping and delivery planning; remaining unknowns are carried forward as non-blocking questions."
            )
    else:
        for gap in evidence_gaps:
            if gap.reason not in reasons:
                reasons.append(gap.reason)
        if not any("not yet" in r.lower() or "missing" in r.lower() for r in reasons):
            reasons.append(
                "Material scope or integration evidence is missing, so a numeric estimate is not yet responsible."
            )

    validation = {
        "status": status,
        "reasons": reasons,
        "questions": blocking_questions,
        "blocking_questions": blocking_questions,
        "non_blocking_questions": _filter_answered_questions(
            _coalesce_optional_questions(
                [
                    q for q in non_blocking_questions
                    if q.lower() not in {b.lower() for b in blocking_questions}
                ],
                state,
            ),
            state,
        ),
        "estimable": not blocking_questions,
        "missing_evidence": [gap.reason for gap in evidence_gaps],
    }

    return {
        "validation": validation,
    }


def clarification_agent(state: DeliveryState) -> dict:
    """Build the human-in-the-loop clarification payload.

    Validation is the only stage that can create customer clarification.
    Delivery Review blockers are deterministic delivery-gate failures and
    must not reopen customer clarification. Review diagnostics remain in
    the review payload instead of becoming new customer questions.
    """
    validation = state.get("validation", {}) or {}
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
    for item in validation.get("blocking_questions", []) or []:
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


STANDARD_SCOPE_ASSUMPTION = (
    "The estimate assumes the requested functionality remains within the assessed scope; "
    "any scope reduction or deferral is treated as a separate delivery decision."
)


def sanitize_standard_estimate_assumptions(assumptions: list) -> list:
    """Keep the independent baseline from assuming deadline-driven scope cuts."""
    normalized = []
    for item in assumptions or []:
        text = str(item).strip()
        lower = text.lower()
        if "security and compliance requirements are well understood" in lower or "security and compliance requirements are fully understood" in lower:
            text = (
                "The security and compliance baseline is based on current customer input; "
                "detailed technical controls may require refinement during solution design."
            )
        elif "black friday is a specific date" in lower:
            continue
        if "3-month estimate is accurate" in lower or "3 months estimate is accurate" in lower:
            continue
        if (
            ("additional resources" in lower or "increase resources" in lower or "more resources" in lower)
            and ("within one month" in lower or "within 1 month" in lower or "deadline" in lower)
        ):
            continue
        if "phased approach" in lower and ("deadline" in lower or "within one month" in lower or "within 1 month" in lower):
            continue
        if (
            "scope can be successfully managed" in lower
            or ("deferred" in lower and "meet" in lower and "scope" in lower)
            or ("deferral" in lower and ("deadline" in lower or "release" in lower) and "scope" in lower)
            or ("scope reduction" in lower and ("meet" in lower or "deadline" in lower))
        ):
            text = STANDARD_SCOPE_ASSUMPTION
        if text and text not in normalized:
            normalized.append(text)
    return normalized


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

    timeline_sources = deadline_source_texts(
        user_request=str(state.get("user_request") or ""),
        discovery=discovery,
        clarification_history=state.get("clarification_history"),
        clarification_answers=state.get("clarification_answers"),
    )
    requested_deadline = parse_requested_deadline(timeline_sources)
    customer_estimate = parse_customer_estimate(timeline_sources)
    customer_deadline_text = requested_deadline.display if requested_deadline is not None else ""
    customer_baseline_text = customer_estimate.display if customer_estimate is not None else ""

    if not is_estimable(state):
        gaps = material_evidence_gaps(state)
        return {
            "estimate": {
                "effort_range": "",
                "duration_range": "Not yet estimable",
                "baseline_duration_range": "Not yet estimable",
                "baseline_effort_range": "",
                "confidence": "LOW",
                "assumptions": [gap.reason for gap in gaps],
                "risks_affecting_estimate": [],
                "customer_deadline": customer_deadline_text,
                "customer_baseline_duration": customer_baseline_text,
                "customer_deadline_weeks": (
                    requested_deadline.weeks if requested_deadline is not None else None
                ),
                "standard_deadline_fit": "NOT_DEMONSTRATED",
                "not_yet_estimable": True,
                "missing_evidence": [gap.reason for gap in gaps],
                "baseline_variance_explanation": (
                    "No independent numeric estimate is produced until the missing "
                    "material evidence is provided."
                ),
            }
        }

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
11. Do not assume scope can be reduced, managed, or deferred to meet the deadline.
    The estimate assumes the requested functionality remains within the assessed
    scope; any scope reduction or deferral is a separate delivery decision.
"""

    estimate = provider.generate_json(prompt=prompt, schema=ESTIMATE_SCHEMA)
    if not isinstance(estimate, dict):
        estimate = {}

    customer_estimated_months = _parse_customer_estimated_months(
        discovery.get("constraints", [])
    )
    deadline_months = _parse_deadline_months(discovery.get("constraints", []))
    timeline_sources = deadline_source_texts(
        user_request=str(state.get("user_request") or ""),
        discovery=discovery,
        clarification_history=state.get("clarification_history"),
        clarification_answers=state.get("clarification_answers"),
    )
    requested_deadline = parse_requested_deadline(timeline_sources)
    customer_estimate = parse_customer_estimate(timeline_sources)

    customer_baseline_text = (
        customer_estimate.display
        if customer_estimate is not None
        else (
            f"{customer_estimated_months:g} months"
            if customer_estimated_months is not None else ""
        )
    )
    customer_deadline_text = (
        requested_deadline.display
        if requested_deadline is not None
        else (
            f"{deadline_months:g} month" + ("" if deadline_months == 1 else "s")
            if deadline_months is not None else ""
        )
    )
    deadline_weeks = (
        requested_deadline.weeks
        if requested_deadline is not None
        else (deadline_months * WEEKS_PER_MONTH if deadline_months is not None else None)
    )

    # Customer-provided baseline and deadline are metadata, not part of our
    # independent estimate. They remain visible for comparison.
    estimate["customer_baseline_duration"] = customer_baseline_text
    estimate["customer_deadline"] = customer_deadline_text
    estimate["baseline_duration_range"] = str(estimate.get("duration_range") or "").strip()
    estimate["baseline_effort_range"] = str(estimate.get("effort_range") or "").strip()

    # This field belongs to the standard estimate only. Do not allow the model
    # to turn the customer's deadline into an optimization rationale here.
    if customer_estimate is not None or customer_estimated_months is not None:
        shown = customer_baseline_text or f"{customer_estimated_months:g} months"
        estimate["baseline_variance_explanation"] = (
            f"The customer-provided estimate is {shown} and is kept "
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
    if deadline_weeks is None or standard_max_weeks is None:
        estimate["standard_deadline_fit"] = "NOT_DEMONSTRATED"
    elif standard_max_weeks <= deadline_weeks + 1e-6:
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
        estimate["assumptions"] = sanitize_standard_estimate_assumptions(estimate["assumptions"])

    # Effort must remain an effort unit; duration must not leak into effort.
    estimate["effort_range"] = _normalize_effort_range(estimate.get("effort_range"))

    # Reassert immutable comparison fields after grounding/normalization.
    estimate["customer_baseline_duration"] = customer_baseline_text
    estimate["customer_deadline"] = customer_deadline_text
    estimate["baseline_duration_range"] = str(estimate.get("duration_range") or "").strip()
    estimate["baseline_effort_range"] = str(estimate.get("effort_range") or "").strip()
    standard_max_weeks = _parse_max_weeks(estimate.get("duration_range", ""))
    if deadline_weeks is None or standard_max_weeks is None:
        estimate["standard_deadline_fit"] = "NOT_DEMONSTRATED"
    elif standard_max_weeks <= deadline_weeks + 1e-6:
        estimate["standard_deadline_fit"] = "FITS"
    else:
        estimate["standard_deadline_fit"] = "EXCEEDS"
    if deadline_weeks is not None:
        estimate["customer_deadline_weeks"] = deadline_weeks

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
    customer_deadline = str(estimate.get("customer_deadline") or "").strip()
    timeline_sources = deadline_source_texts(
        user_request=str(state.get("user_request") or ""),
        discovery=discovery,
        clarification_history=state.get("clarification_history"),
        clarification_answers=state.get("clarification_answers"),
    )
    if not customer_baseline:
        customer_estimate = parse_customer_estimate(timeline_sources)
        if customer_estimate is not None:
            customer_baseline = customer_estimate.display
    if not customer_deadline:
        requested_deadline = parse_requested_deadline(timeline_sources)
        if requested_deadline is not None:
            customer_deadline = requested_deadline.display
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
    requested_deadline = parse_requested_deadline(timeline_sources)
    deadline_weeks = (
        requested_deadline.weeks
        if requested_deadline is not None
        else estimate.get("customer_deadline_weeks")
    )
    if deadline_weeks is None:
        result["deadline_feasibility"] = "NOT_APPLICABLE"
        result["deadline_gap"] = ""
    elif optimized_max_weeks is None:
        result["deadline_feasibility"] = "NOT_DEMONSTRATED"
    else:
        if optimized_max_weeks <= deadline_weeks + 1e-6:
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
            "NOT_APPLICABLE" if deadline_weeks is None else "NOT_DEMONSTRATED"
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
            "decisions supported by project evidence. This is optional scenario analysis, "
            "not a guaranteed acceleration."
        )
    elif result["deadline_feasibility"] in {"FEASIBLE", "FEASIBLE_WITH_CONDITIONS"}:
        prefix = (
            "Under the assumptions below, an AI-assisted approach could reduce the "
            "estimated duration. This is scenario analysis, not a commitment. "
        )
        summary = result["optimization_summary"]
        if "not a commitment" not in summary.lower() and "scenario analysis" not in summary.lower():
            result["optimization_summary"] = prefix + summary
        result["optimization_summary"] = re.sub(
            r"\bguarantees?\b",
            "does not guarantee",
            result["optimization_summary"],
            flags=re.I,
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
6. Use estimate.standard_deadline_fit as the only deadline verdict for the
   independent estimate. Values are FITS, EXCEEDS, or NOT_DEMONSTRATED.
   If the fit is EXCEEDS or NOT_DEMONSTRATED, do NOT describe the customer
   deadline as an achieved delivery commitment. Present it as the customer's
   target and clearly distinguish it from the independent indicative estimate.
7. If an AI-optimized scenario is explicitly provided and marked
   FEASIBLE_WITH_CONDITIONS, describe it as a conditional accelerated option,
   not a guaranteed commitment. Never treat AI optimization as a substitute
   for the independent estimate.
"""

    proposal = provider.generate_json(
        prompt=prompt,
        schema=PROPOSAL_SCHEMA,
    )
    proposal = _ground_downstream_artifact(proposal, state)
    if isinstance(proposal, dict):
        proposal = _apply_deadline_honesty(proposal, estimate)

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
    if isinstance(sow, dict):
        sow = _apply_deadline_honesty(sow, estimate)

    return {
        "sow": sow,
    }

def _apply_deadline_honesty(document: dict, estimate: dict) -> dict:
    """Force proposal/SOW timeline text to match standard_deadline_fit."""
    from app.assessment import deadline_honesty_timeline, standard_deadline_fit

    fit = standard_deadline_fit(estimate)
    document["timeline"] = deadline_honesty_timeline(estimate)
    summary = document.get("executive_summary")
    if isinstance(summary, str) and fit in {"EXCEEDS", "NOT_DEMONSTRATED"}:
        commitment_markers = (
            "complete within",
            "completed within",
            "delivered within",
            "will be done by",
            "guaranteed",
            "commit to deliver by",
        )
        if any(marker in summary.lower() for marker in commitment_markers):
            document["executive_summary"] = (
                summary.rstrip()
                + " The requested deadline is not a demonstrated delivery commitment; "
                f"the independent estimate assessment is {fit.replace('_', ' ')}."
            )
    return document


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


def _extract_explicit_timeline_facts(request: str) -> list[str]:
    """Extract explicit customer deadline and estimate statements for provenance."""
    facts: list[str] = []
    deadline = parse_requested_deadline([request])
    estimate = parse_customer_estimate([request])
    if deadline:
        facts.append(f"Target delivery timeline: {deadline.display}")
    if estimate:
        facts.append(f"Customer-provided estimate: {estimate.display}")
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
    span = parse_customer_estimate(list(constraints or []))
    if span is None:
        return None
    return span.weeks / WEEKS_PER_MONTH


def _parse_deadline_months(constraints: list[str]) -> float | None:
    """Extract an explicit customer delivery deadline from constraints.

    Supports days, weeks, and months. Bare duration estimates are ignored.
    """
    span = parse_requested_deadline(list(constraints or []))
    if span is None:
        return None
    return span.weeks / WEEKS_PER_MONTH

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
    requested = parse_requested_deadline(discovery.get("constraints", []))
    deadline_weeks = requested.weeks if requested is not None else None
    estimate_max_weeks = _parse_max_weeks(estimate.get("duration_range", ""))
    customer_estimate = parse_customer_estimate(discovery.get("constraints", []))

    if deadline_weeks is not None and estimate_max_weeks is not None:
        if customer_estimate is not None and customer_estimate.weeks > deadline_weeks:
            fit = str(estimate.get("standard_deadline_fit") or "").upper()
            if fit == "FITS":
                warnings.append(
                    "The customer-provided baseline exceeds the deadline, but the independent "
                    "estimate does not. Keep the customer baseline as reference only; do not "
                    "treat the date as proven by the customer's own estimate."
                )
            else:
                warnings.append(
                    "Customer baseline exceeds the deadline. Deadline feasibility is not demonstrated "
                    "by the current independent estimate; an explicit AI-optimized scenario is required "
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

    # The LLM review is advisory. It can identify risks, inconsistencies and
    # questions, but it must not create a customer blocker by itself. Otherwise
    # every newly-worded uncertainty (scope detail, traffic, integration
    # maturity, compliance detail, etc.) can reopen clarification indefinitely.
    # Only deterministic invariants below are allowed to populate
    # blocking_issues.
    blocking_issues = []
    warnings = list(review.get("warnings", []))
    checks = list(review.get("checks", []))
    deadline_review_removed = False

    for issue in (review.get("blocking_issues", []) or []):
        text = str(issue).strip()
        if not text:
            continue
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

        # A model-reported deadline gap is advisory in the standard Analyze
        # flow. AI optimization is optional and is assessed separately.
        if not ai_optimization and deadline_related:
            deadline_review_removed = True
            continue

        advisory = f"Delivery review advisory: {text}"
        if advisory.lower() not in {str(w).lower() for w in warnings}:
            warnings.append(advisory)

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
