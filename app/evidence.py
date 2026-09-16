"""Deterministic evidence/readiness gate for responsible estimation.

A missing deadline does not mean the work is not estimable.
A known deadline does not mean the work is sufficiently defined to estimate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.timeline import parse_requested_deadline


_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "has",
    "will", "are", "was", "were", "been", "being", "into", "about", "their",
    "them", "they", "should", "must", "need", "needs", "wanted", "want",
    "build", "built", "using", "used", "our", "its", "not", "but", "can",
}

_GENERIC_PRODUCT = re.compile(
    r"\b(portals?|websites?|apps?|applications?|systems?|platforms?|"
    r"dashboards?|tools?|solutions?|interfaces?|products?|sites?|"
    r"reporting|reports?|knowledge\s+bases?)\b",
    re.I,
)

_CAPABILITY_CLAUSE = re.compile(
    r"\b(?:can|must|should|needs?\s+to|able\s+to|allow(?:s|ing)?|"
    r"enable(?:s|ing)?|provide(?:s|ing)?|include(?:s|ing)?)\s+"
    r"(?:the\s+|a\s+|an\s+|to\s+)?(?!portal\b|website\b|app\b|system\b|platform\b)"
    r"[\w][\w\s-]{2,80}",
    re.I,
)

_CAPABILITY_NOT_SCOPE = re.compile(
    r"\b(?:integrat\w*|existing\s+systems?|source\s+of\s+truth|third[- ]party|"
    r"proposal|delivery estimate)\b",
    re.I,
)
_VAGUE_AUTOMATION = re.compile(
    r"\bautomate\b.{0,60}\b(process(?:es)?|manual|workflows?)\b",
    re.I,
)
_ACTION_OBJECT = re.compile(
    r"\b(?:view|submit|track|manage|create|search|export|import|display|"
    r"approve|onboard|authenticate|log\s*in|update|edit)\s+"
    r"(?:the\s+|a\s+|an\s+)?[\w][\w\s-]{2,40}",
    re.I,
)

_NAMED_SYSTEM = re.compile(
    r"\b(salesforce|sap|jira|servicenow|workday|dynamics|sharepoint|"
    r"entra|okta|auth0|aws|azure|gcp|snowflake|postgres|mysql|"
    r"identity\s+provider|idp\b|active\s+directory|ldap\b|"
    r"[\w-]+\s+api|api\s+called|existing\s+[\w-]+\s+api)\b",
    re.I,
)

_NAMED_EXISTING_SYSTEM = re.compile(
    r"\bexisting\s+(?!systems?\b)(?:[\w'-]+\s+){0,5}"
    r"(?:provider|platform|service|directory|idp)\b",
    re.I,
)

_INTEGRATION_MENTION = re.compile(
    r"\b(integrat(?:e|ed|ion)|existing\s+systems?|source\s+of\s+truth|"
    r"legacy|crm|erp|third[- ]party)\b",
    re.I,
)

_MIGRATION_MENTION = re.compile(
    r"\b(migrat(?:e|ed|ion)|cutover|data\s+import|legacy\s+data|"
    r"all\s+(?:accounts?|records?|users?|customers?))\b",
    re.I,
)

_VOLUME_HINT = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:accounts?|records?|users?|customers?|"
    r"employees?|rows?|gb|tb)\b",
    re.I,
)

_PHASE_HINT = re.compile(
    r"\b(first\s+release|mvp|phase\s*1|critical\s+subset|pilot|"
    r"subset|phased)\b",
    re.I,
)

_COMPLIANCE_MANDATE = re.compile(
    r"\b(must\s+comply|mandatory\s+(?:security|compliance|regulatory)|"
    r"hipaa|pci[- ]dss|soc\s*2|gdpr\s+required|regulated\s+industry)\b",
    re.I,
)

_USER_HINT = re.compile(
    r"\b(users?|customers?|employees?|agents?|admins?|operators?|"
    r"staff|audience|who will use)\b",
    re.I,
)

_NON_BLOCKING_MARKERS = (
    "brand", "logo", "color", "font", "css", "theme",
    "technology preference", "tech stack", "framework",
    "react", "angular", "vue", "language preference",
    "minor ui", "button placement", "formatting",
    "exact field", "pixel",
)

_MATERIAL_QUESTION_MARKERS = (
    "first release", "first-release", "in scope", "out of scope",
    "core function", "main capabilities", "who will use",
    "integrat", "source of truth", "migrat", "data volume",
    "acceptance criteria", "mandatory", "regulat", "compliance",
)


@dataclass(frozen=True)
class EvidenceGap:
    code: str
    question: str
    reason: str


def customer_authored_text(state: dict | None) -> str:
    """Only customer-authored sources: request plus clarification answers."""
    state = state or {}
    parts = [str(state.get("user_request") or "")]
    for item in state.get("clarification_history") or []:
        if isinstance(item, dict):
            parts.append(str(item.get("answer") or ""))
        else:
            parts.append(str(item))
    for item in state.get("clarification_answers") or []:
        parts.append(str(item))
    for item in state.get("new_clarification_records") or []:
        if isinstance(item, dict):
            parts.append(str(item.get("answer") or ""))
    return "\n".join(part for part in parts if str(part).strip())


def is_numeric_duration(text: str) -> bool:
    raw = str(text or "").strip().lower()
    if not raw or "not yet estimable" in raw or "not estimable" in raw:
        return False
    return bool(re.search(
        r"\d+(?:[.,]\d+)?\s*(?:-|–|—|to)?\s*\d*(?:[.,]\d+)?\s*"
        r"(?:day|days|week|weeks|month|months)\b",
        raw,
    ))


def has_first_release_scope(text: str) -> bool:
    """True only for named first-release capabilities, not integration or vague automation."""
    source = str(text or "")
    if _ACTION_OBJECT.search(source):
        return True
    for match in _CAPABILITY_CLAUSE.finditer(source):
        snippet = match.group(0)
        if _CAPABILITY_NOT_SCOPE.search(snippet):
            continue
        if _VAGUE_AUTOMATION.search(snippet):
            continue
        return True
    return False


def has_named_users(text: str) -> bool:
    return bool(_USER_HINT.search(text or ""))


def has_named_integration(text: str) -> bool:
    source = text or ""
    return bool(_NAMED_SYSTEM.search(source) or _NAMED_EXISTING_SYSTEM.search(source))


def needs_integration_clarity(text: str) -> bool:
    source = text or ""
    if not _INTEGRATION_MENTION.search(source):
        return False
    return not has_named_integration(source)


def needs_migration_clarity(text: str) -> bool:
    source = text or ""
    if not _MIGRATION_MENTION.search(source):
        return False
    return not (_VOLUME_HINT.search(source) or _PHASE_HINT.search(source))


def needs_compliance_clarity(text: str) -> bool:
    return bool(_COMPLIANCE_MANDATE.search(text or ""))


def is_non_blocking_topic(text: str) -> bool:
    lower = str(text or "").lower()
    return any(marker in lower for marker in _NON_BLOCKING_MARKERS)


def is_material_question(text: str) -> bool:
    lower = str(text or "").lower()
    if is_non_blocking_topic(lower):
        return False
    return any(marker in lower for marker in _MATERIAL_QUESTION_MARKERS)


def statement_is_explicit(statement: str, source: str) -> bool:
    """True when a statement is a substring or shares enough customer tokens."""
    text = str(statement or "").strip()
    origin = str(source or "").lower()
    if not text or not origin:
        return False
    lower = text.lower()
    if lower in origin:
        return True
    tokens = [
        token for token in re.findall(r"[a-z0-9]{4,}", lower)
        if token not in _STOPWORDS and not _GENERIC_PRODUCT.fullmatch(token)
    ]
    if len(tokens) < 2:
        return False
    hits = sum(1 for token in tokens if token in origin)
    return hits >= min(2, len(tokens)) and hits / len(tokens) >= 0.5


def material_evidence_gaps(state: dict | None) -> list[EvidenceGap]:
    """Minimum missing evidence required for a responsible estimate."""
    source = customer_authored_text(state)
    gaps: list[EvidenceGap] = []

    if not has_first_release_scope(source):
        gaps.append(EvidenceGap(
            code="first_release_scope",
            question=(
                "What is in scope for the first production release, including "
                "the main capabilities and what is explicitly out of scope?"
            ),
            reason="First-release scope is not defined well enough for a responsible estimate.",
        ))

    if not has_named_users(source):
        gaps.append(EvidenceGap(
            code="users",
            question="Who will use the first release, and what will they do in it?",
            reason="The primary users of the first release are not identified.",
        ))

    if needs_integration_clarity(source):
        gaps.append(EvidenceGap(
            code="integrations",
            question=(
                "Which systems must the first release integrate with, and what "
                "is the source of truth?"
            ),
            reason="Major integration work is implied but the systems are not named.",
        ))

    if needs_migration_clarity(source):
        gaps.append(EvidenceGap(
            code="migration",
            question=(
                "What data or accounts must be migrated in the first release, "
                "and at what volume or phasing?"
            ),
            reason="Migration is in play but volume/phasing is not specified.",
        ))

    if needs_compliance_clarity(source):
        gaps.append(EvidenceGap(
            code="compliance",
            question=(
                "Which mandatory security or regulatory constraints apply to "
                "the first release?"
            ),
            reason="Mandatory compliance constraints are claimed but not specified.",
        ))

    return gaps


def is_estimable(state: dict | None) -> bool:
    return not material_evidence_gaps(state)


def requested_deadline_display(state: dict | None) -> str:
    state = state or {}
    discovery = state.get("discovery") or {}
    from app.timeline import deadline_source_texts

    hit = parse_requested_deadline(
        deadline_source_texts(
            user_request=str(state.get("user_request") or ""),
            discovery=discovery,
            clarification_history=state.get("clarification_history"),
            clarification_answers=state.get("clarification_answers"),
        )
    )
    return hit.display if hit is not None else ""
