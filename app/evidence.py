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

_STATED_ACTION_VERBS = (
    "log in",
    "sign in",
    "authenticate",
    "login",
    "view",
    "submit",
    "track",
    "manage",
    "create",
    "search",
    "export",
    "import",
    "display",
    "approve",
    "onboard",
    "update",
    "edit",
    "place",
    "browse",
    "upload",
    "download",
    "cancel",
    "assign",
    "notify",
)
_STATED_VERB_ALT = "|".join(
    sorted((re.escape(verb) for verb in _STATED_ACTION_VERBS), key=len, reverse=True)
)
_NOUN = rf"(?!{_STATED_VERB_ALT}\b)[a-z][\w'-]*"
_COORDINATED_ACTIONS = re.compile(
    rf"\b((?:{_STATED_VERB_ALT})(?:\s*(?:,|/|\band\b)\s*(?:{_STATED_VERB_ALT}))+)\s+"
    rf"(?:the\s+|a\s+|an\s+)?({_NOUN}(?:\s+{_NOUN}){{0,3}})",
    re.I,
)
_SIMPLE_ACTION_OBJECT = re.compile(
    rf"\b({_STATED_VERB_ALT})\s+(?:the\s+|a\s+|an\s+)?({_NOUN}(?:\s+{_NOUN}){{0,3}})",
    re.I,
)
_STANDALONE_AUTH = re.compile(r"\b(log\s*in|sign\s*in|authenticate|login)\b", re.I)
_SOURCE_OF_TRUTH = re.compile(r"\b(source of truth|system of record)\b", re.I)
_OBJECT_TRIM = re.compile(
    r"\s+(?:and|or|with|using|via|so|that|who|which|where|when|,|;|:|\.)\b",
    re.I,
)
_AUTH_VERBS = frozenset({"log in", "login", "sign in", "signin", "authenticate", "authentication"})
_VERB_FAMILIES = (
    _AUTH_VERBS,
    frozenset({"view", "display", "see", "read", "browse"}),
    frozenset({"create", "submit", "file", "raise", "open", "place"}),
    frozenset({"track", "tracking", "follow"}),
    frozenset({"update", "edit"}),
    frozenset({"manage", "maintain"}),
    frozenset({"search", "find"}),
    frozenset({"export"}),
    frozenset({"import"}),
    frozenset({"approve", "approval"}),
    frozenset({"upload"}),
    frozenset({"download"}),
    frozenset({"cancel"}),
    frozenset({"assign"}),
    frozenset({"notify", "notification"}),
    frozenset({"onboard", "onboarding"}),
)

_NAMED_SYSTEM = re.compile(
    r"\b(salesforce|sap|jira|servicenow|workday|dynamics|sharepoint|"
    r"entra|okta|auth0|aws|azure|gcp|snowflake|postgres|mysql|"
    r"stripe|adyen|braintree|paypal|worldpay|"
    r"identity\s+provider|idp\b|active\s+directory|ldap\b|"
    r"[\w-]+\s+api|api\s+called|existing\s+[\w-]+\s+api)\b",
    re.I,
)

_NAMED_EXISTING_SYSTEM = re.compile(
    r"\bexisting\s+(?!systems?\b)(?:[\w'-]+\s+){0,5}"
    r"(?:provider|platform|service|directory|idp)\b",
    re.I,
)

_GENERIC_SYSTEM_TOKENS = {
    "existing", "and", "or", "the", "an", "a", "our", "their", "its",
    "erp", "crm", "cms", "hrms", "hrm",
    "payment", "payments", "provider", "providers",
    "platform", "platforms", "service", "services",
    "system", "systems", "gateway", "gateways",
    "legacy", "third", "party", "external", "internal",
}

_INTEGRATION_MENTION = re.compile(
    r"\b(integrat(?:e|ed|ion)|existing\s+systems?|source\s+of\s+truth|"
    r"legacy|crm|erp|third[- ]party|"
    r"payment\s+providers?|payment\s+gateways?)\b",
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

_UNDEFINED_SCOPE = re.compile(
    r"\b("
    r"not provided detailed requirements|"
    r"detailed requirements.{0,60}not (?:yet )?provided|"
    r"has not provided.{0,40}requirements|"
    r"exact scope is still|"
    r"scope is still being discussed|"
    r"scope (?:is|remains) (?:undefined|unclear|tbd|not defined)|"
    r"requirements (?:are|remain) (?:undefined|unclear|not (?:yet )?provided)"
    r")\b",
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

_NON_SUBSTANTIVE_ANSWER_WORDS = {
    "i", "do", "dont", "don't", "not", "know", "tbd", "n", "a", "na",
    "idk", "unknown", "none", "yet", "decided", "sure", "defined",
    "no", "idea", "undecided", "applicable", "to", "be", "determined",
    "still", "being", "discussed", "sorry", "unsure",
}

FIRST_RELEASE_SCOPE_QUESTION = (
    "What is in scope for the first production release, including "
    "the main capabilities and what is explicitly out of scope?"
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
    seen_answers: set[str] = set()
    for item in state.get("clarification_history") or []:
        if isinstance(item, dict):
            answer = str(item.get("answer") or "")
        else:
            answer = str(item)
        if answer.strip():
            parts.append(answer)
            seen_answers.add(answer.strip())
    for item in state.get("clarification_answers") or []:
        answer = str(item)
        if answer.strip() and answer.strip() not in seen_answers:
            parts.append(answer)
            seen_answers.add(answer.strip())
    for item in state.get("new_clarification_records") or []:
        if isinstance(item, dict):
            answer = str(item.get("answer") or "")
            if answer.strip() and answer.strip() not in seen_answers:
                parts.append(answer)
                seen_answers.add(answer.strip())
    canonical = state.get("clarification_state") if isinstance(state, dict) else {}
    if isinstance(canonical, dict):
        for item in canonical.get("answers") or []:
            if not isinstance(item, dict):
                continue
            answer = str(item.get("answer") or "")
            if answer.strip() and answer.strip() not in seen_answers:
                parts.append(answer)
                seen_answers.add(answer.strip())
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
    has_action = bool(_ACTION_OBJECT.search(source))
    if has_action:
        return True
    for match in _CAPABILITY_CLAUSE.finditer(source):
        snippet = match.group(0)
        if _CAPABILITY_NOT_SCOPE.search(snippet):
            continue
        if _VAGUE_AUTOMATION.search(snippet):
            continue
        if _GENERIC_PRODUCT.search(snippet) and not _ACTION_OBJECT.search(snippet):
            remainder = _GENERIC_PRODUCT.sub(" ", snippet)
            if not re.search(r"[a-z]{4,}", remainder, re.I):
                continue
        if _UNDEFINED_SCOPE.search(source):
            return False
        return True
    return False


def has_named_users(text: str) -> bool:
    return bool(_USER_HINT.search(text or ""))


def _is_generic_system_snippet(snippet: str) -> bool:
    tokens = re.findall(r"[a-z0-9]+", str(snippet or "").lower())
    if not tokens:
        return True
    return all(token in _GENERIC_SYSTEM_TOKENS for token in tokens)


def has_named_integration(text: str) -> bool:
    source = text or ""
    for pattern in (_NAMED_SYSTEM, _NAMED_EXISTING_SYSTEM):
        for match in pattern.finditer(source):
            if not _is_generic_system_snippet(match.group(0)):
                return True
    return False


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


def is_first_release_scope_question(text: str) -> bool:
    """True for the first-release *scope* question, not other first-release topics."""
    lower = str(text or "").lower()
    if FIRST_RELEASE_SCOPE_QUESTION.lower() in lower:
        return True
    if "main capabilities" in lower or "core function" in lower:
        return True
    if "in scope" in lower and "out of scope" in lower:
        return True
    return False


def is_non_substantive_clarification_answer(text: str) -> bool:
    """True for empty/TBD/unknown replies that do not provide scope evidence."""
    raw = str(text or "").strip()
    if len(raw) < 8:
        return True
    words = re.findall(r"[a-z0-9']+", raw.lower())
    if not words:
        return True
    content = [word for word in words if word not in _NON_SUBSTANTIVE_ANSWER_WORDS]
    return not content


def normalize_question_text(text: str) -> str:
    """Normalize question text for exact answered-question matching."""
    return re.sub(r"\s+", " ", str(text or "").strip()).casefold()


def split_legacy_clarification_blob(blob: str) -> tuple[str, str]:
    """Recover question/answer from the UI string `${questionText}: ${answer}`."""
    text = str(blob or "").strip()
    if not text:
        return "", ""
    marker = "?: "
    index = text.rfind(marker)
    if index != -1:
        return text[: index + 1].strip(), text[index + len(marker):].strip()
    marker = ": "
    index = text.rfind(marker)
    if index != -1:
        question = text[:index].strip()
        answer = text[index + len(marker):].strip()
        if question and answer:
            return question, answer
    return "", text


def unpack_clarification_record(question: str, answer: str) -> tuple[str, str]:
    """Return the real question/answer, unpacking legacy UI history rows."""
    question_text = str(question or "").strip()
    answer_text = str(answer or "").strip()
    placeholder = normalize_question_text(question_text) in {"", "customer clarification"}
    if placeholder:
        inner_question, inner_answer = split_legacy_clarification_blob(answer_text)
        if inner_question:
            return inner_question, inner_answer
        return question_text, answer_text
    return question_text, clarification_answer_body(question_text, answer_text)


def clarification_answer_body(question: str, answer: str) -> str:
    """Strip a duplicated question prefix from legacy 'question: answer' strings."""
    answer_text = str(answer or "").strip()
    question_text = str(question or "").strip()
    if question_text and answer_text.lower().startswith(question_text.lower()):
        return answer_text[len(question_text):].lstrip(" :")
    prefix = FIRST_RELEASE_SCOPE_QUESTION
    if answer_text.lower().startswith(prefix.lower()):
        return answer_text[len(prefix):].lstrip(" :")
    return answer_text


def _clarification_pairs(state: dict | None) -> list[tuple[str, str]]:
    state = state or {}
    pairs: list[tuple[str, str]] = []
    for item in state.get("clarification_history") or []:
        if isinstance(item, dict):
            pairs.append(
                (str(item.get("question") or ""), str(item.get("answer") or ""))
            )
        else:
            pairs.append(("", str(item)))
    for item in state.get("new_clarification_records") or []:
        if isinstance(item, dict):
            pairs.append(
                (str(item.get("question") or ""), str(item.get("answer") or ""))
            )
    for item in state.get("clarification_answers") or []:
        pairs.append(("", str(item)))
    canonical = state.get("clarification_state")
    if isinstance(canonical, dict):
        for item in canonical.get("answers") or []:
            if not isinstance(item, dict):
                continue
            pairs.append(
                (str(item.get("question") or ""), str(item.get("answer") or ""))
            )

    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for question, answer in pairs:
        question = question.strip()
        answer = answer.strip()
        if not answer:
            continue
        key = (normalize_question_text(question), normalize_question_text(answer))
        if key in seen:
            continue
        seen.add(key)
        deduped.append((question, answer))
    return deduped


def substantive_answered_questions(state: dict | None) -> set[str]:
    """Normalized question texts that already have a substantive customer answer."""
    answered: set[str] = set()
    for question, answer in _clarification_pairs(state):
        real_question, body = unpack_clarification_record(question, answer)
        normalized = normalize_question_text(real_question)
        if not normalized:
            continue
        if is_non_substantive_clarification_answer(body):
            continue
        answered.add(normalized)
    return answered


def has_substantive_answer_for_question(state: dict | None, question: str) -> bool:
    """True when this exact required question already has a usable customer answer."""
    normalized = normalize_question_text(question)
    if not normalized:
        return False
    return normalized in substantive_answered_questions(state)


def has_substantive_first_release_scope_answer(state: dict | None) -> bool:
    """True when the customer substantively answered the first-release scope question."""
    for question, answer in _clarification_pairs(state):
        blob = f"{question} {answer}"
        if not (
            is_first_release_scope_question(question)
            or is_first_release_scope_question(blob)
        ):
            continue
        body = clarification_answer_body(question, answer)
        if not is_non_substantive_clarification_answer(body):
            return True
    return False


def is_non_blocking_topic(text: str) -> bool:
    lower = str(text or "").lower()
    return any(marker in lower for marker in _NON_BLOCKING_MARKERS)


def is_material_question(text: str) -> bool:
    lower = str(text or "").lower()
    if is_non_blocking_topic(lower):
        return False
    return any(marker in lower for marker in _MATERIAL_QUESTION_MARKERS)


def _normalize_action_verb(verb: str) -> str:
    return re.sub(r"\s+", " ", str(verb or "").strip().lower())


def _trim_action_object(raw: str) -> str:
    text = str(raw or "").strip().lower()
    cut = _OBJECT_TRIM.search(text)
    if cut:
        text = text[: cut.start()].strip()
    tokens = [token for token in re.findall(r"[a-z0-9']+", text) if token not in _STOPWORDS]
    return " ".join(tokens[:4]).strip()


def _verb_family(verb: str) -> frozenset[str]:
    normalized = _normalize_action_verb(verb)
    for family in _VERB_FAMILIES:
        if normalized in family:
            return family
    return frozenset({normalized})


_PREFERRED_FAMILY_IDS = (
    "authenticate",
    "view",
    "create",
    "track",
    "update",
    "manage",
    "search",
    "export",
    "import",
    "approve",
    "upload",
    "download",
    "cancel",
    "assign",
    "notify",
    "onboard",
)
_FAMILY_ID_BY_TOKEN: dict[str, str] = {}
for _family in _VERB_FAMILIES:
    _family_id = next(
        (name for name in _PREFERRED_FAMILY_IDS if name in _family),
        min(_family),
    )
    for _token in _family:
        _FAMILY_ID_BY_TOKEN[_token] = _family_id

# Nominal and gerund forms of the same generic verb families. Not product nouns.
_NOMINAL_VERBS = {
    "creation": "create",
    "creating": "create",
    "tracking": "track",
    "submission": "submit",
    "submitting": "submit",
    "management": "manage",
    "managing": "manage",
    "searching": "search",
    "viewing": "view",
    "updating": "update",
    "editing": "edit",
    "placing": "place",
    "browsing": "browse",
    "uploading": "upload",
    "downloading": "download",
    "cancelling": "cancel",
    "canceling": "cancel",
    "cancellation": "cancel",
    "assigning": "assign",
    "notifying": "notify",
}
for _nominal, _verb in _NOMINAL_VERBS.items():
    _FAMILY_ID_BY_TOKEN.setdefault(_nominal, _FAMILY_ID_BY_TOKEN.get(_verb, _verb))

_SIGNATURE_SKIP = _STOPWORDS | {
    "a", "an", "of", "to", "for", "from", "into", "onto", "with", "via", "by", "on", "in",
    "is", "are", "be", "been", "being", "was", "were", "can", "may", "shall",
    "must", "should", "able", "allow", "allows", "allowed", "their", "its",
    "available", "possible", "supported", "support", "works", "work",
    "succeeds", "successful", "successfully", "provided", "including",
}
_SIGNATURE_FILLERS = frozenset({
    "workflow", "workflows", "capability", "capabilities", "process", "processes",
    "functionality", "feature", "features", "handling", "ability", "function",
    "functions",
})
_SIGNATURE_QUALIFIERS = frozenset({"status", "state", "progress", "detail", "details"})
_SIGNATURE_ACTORS = frozenset({
    "customer", "customers", "user", "users", "member", "members", "staff",
    "operator", "operators", "patient", "patients", "student", "students",
    "visitor", "visitors", "employee", "employees", "guest", "guests",
    "client", "clients",
})


def _family_id(token: str) -> str | None:
    return _FAMILY_ID_BY_TOKEN.get(str(token or "").lower())


def _signature_object(words: list[str]) -> str:
    stems: list[str] = []
    for word in words:
        if word in _SIGNATURE_SKIP or word in _SIGNATURE_FILLERS or word in _SIGNATURE_QUALIFIERS:
            continue
        if _family_id(word):
            break
        stem = word[:-1] if word.endswith("s") and not word.endswith("ss") and len(word) > 4 else word
        if stem in _SIGNATURE_QUALIFIERS:
            continue
        stems.append(stem)
        if len(stems) >= 4:
            break
    return " ".join(stems)


def behavior_signatures(text: str) -> frozenset[tuple[str, str]]:
    """Generic behavior identity for one statement.

    Each signature is a verb family plus the object it applies to. Login and
    authentication share the authenticate family. Create and track stay
    distinct. Words outside the generic verb families produce no signature.
    """
    raw = str(text or "").lower()
    raw = re.sub(r"\blog\s+in\b", "login", raw)
    raw = re.sub(r"\bsign\s+in\b", "signin", raw)
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    words = [word for word in raw.split() if word]
    found: list[tuple[str, str]] = []
    index = 0
    while index < len(words):
        family = _family_id(words[index])
        if not family:
            index += 1
            continue
        families = [family]
        cursor = index + 1
        while cursor + 1 < len(words) and words[cursor] == "and":
            nxt = _family_id(words[cursor + 1])
            if not nxt:
                break
            if nxt not in families:
                families.append(nxt)
            cursor += 2
        if cursor < len(words) and words[cursor] == "of":
            cursor += 1
        forward: list[str] = []
        while cursor < len(words) and words[cursor] != "and" and not _family_id(words[cursor]):
            forward.append(words[cursor])
            cursor += 1
            if len(forward) >= 6:
                break
        forward_obj = _signature_object(forward)
        forward_parts = [part for part in forward_obj.split() if part not in _SIGNATURE_ACTORS]
        obj = " ".join(forward_parts)
        if not obj:
            before: list[str] = []
            back = index - 1
            while back >= 0 and len(before) < 3 and not _family_id(words[back]):
                before.append(words[back])
                back -= 1
            before.reverse()
            parts = _signature_object(before).split()
            while parts and parts[0] in _SIGNATURE_ACTORS:
                parts = parts[1:]
            obj = " ".join(parts) or forward_obj
        for item in families:
            found.append((item, "" if item == "authenticate" else obj))
        index = max(cursor, index + 1)
    return frozenset(found)


def _split_coordinated_verbs(blob: str) -> list[str]:
    parts = re.split(r"\s*(?:,|/|\band\b)\s*", str(blob or ""), flags=re.I)
    return [_normalize_action_verb(part) for part in parts if _normalize_action_verb(part)]


def stated_request_outcomes(text: str) -> tuple[str, ...]:
    """Independently testable action/outcome phrases stated by the customer."""
    source = str(text or "")
    found: list[tuple[str, str]] = []
    used_spans: list[tuple[int, int]] = []

    def already_used(start: int, end: int) -> bool:
        return any(start < stop and end > begin for begin, stop in used_spans)

    for match in _COORDINATED_ACTIONS.finditer(source):
        verbs = _split_coordinated_verbs(match.group(1))
        obj = _trim_action_object(match.group(2))
        used_spans.append(match.span())
        for verb in verbs:
            if verb in _AUTH_VERBS:
                found.append((verb, ""))
            elif obj:
                found.append((verb, obj))

    for match in _SIMPLE_ACTION_OBJECT.finditer(source):
        if already_used(*match.span()):
            continue
        verb = _normalize_action_verb(match.group(1))
        obj = _trim_action_object(match.group(2))
        if verb in _AUTH_VERBS:
            found.append((verb, ""))
            continue
        if obj:
            found.append((verb, obj))

    if _STANDALONE_AUTH.search(source) and not any(verb in _AUTH_VERBS for verb, _obj in found):
        found.append(("log in", ""))

    phrases: list[str] = []
    seen: set[str] = set()
    for verb, obj in found:
        phrase = f"{verb} {obj}".strip()
        key = phrase
        if verb in _AUTH_VERBS:
            key = "authenticate"
            phrase = "authenticate"
        if key in seen:
            continue
        seen.add(key)
        phrases.append(phrase)
    if _SOURCE_OF_TRUTH.search(source):
        phrases.append("source of truth")
    return tuple(phrases)


def outcome_is_covered(outcome: str, requirements_text: str) -> bool:
    """True when requirements preserve the stated action, not only a shared object."""
    blob = str(requirements_text or "").lower()
    phrase = str(outcome or "").strip().lower()
    if not phrase or not blob:
        return False
    if phrase == "source of truth":
        return bool(_SOURCE_OF_TRUTH.search(blob))
    if phrase in blob:
        return True
    parts = phrase.split(None, 1)
    verb = parts[0] if parts else ""
    obj = parts[1] if len(parts) > 1 else ""
    if phrase in _AUTH_VERBS or verb in _AUTH_VERBS:
        return any(token in blob for token in _AUTH_VERBS)
    family = _verb_family(verb)
    if not any(re.search(rf"\b{re.escape(token)}\b", blob) for token in family if token):
        return False
    if not obj:
        return True
    tokens = [token for token in re.findall(r"[a-z0-9]{3,}", obj) if token not in _STOPWORDS]
    if not tokens:
        return True
    return all(token in blob for token in tokens)


def uncovered_request_outcomes(source: str, requirements: dict | None) -> tuple[str, ...]:
    """Request-stated outcomes missing from functional requirements and acceptance criteria."""
    requirements = requirements or {}
    blob = " ".join(
        [
            " ".join(str(item) for item in requirements.get("functional_requirements") or []),
            " ".join(str(item) for item in requirements.get("acceptance_criteria") or []),
            " ".join(str(item) for item in requirements.get("non_functional_requirements") or []),
        ]
    )
    return tuple(
        outcome
        for outcome in stated_request_outcomes(source)
        if not outcome_is_covered(outcome, blob)
    )


_SCOPE_RETRACTION = re.compile(
    r"\b(?:instead(?:\s+of)?|no longer|not (?:in|part of)(?:\s+the)?\s+scope|"
    r"out of scope|replace(?:s|d)?|do not include|removed? from scope|"
    r"exclude(?:d)?|drop(?:ped)?(?:\s+from)?|cancel(?:led)?|"
    r"different product)\b",
    re.I,
)
_ADDITIVE_SCOPE = re.compile(
    r"\b(?:in addition|also|as well|additionally)\b",
    re.I,
)
_PROHIBITION_MARKERS = (
    "must not",
    "shall not",
    "do not ",
    "don't ",
    "do not include",
    "must never",
)
_REPLACE_WITH = re.compile(
    r"\breplace(?:s|d)?\s+(?:the\s+|an?\s+)?(.+?)\s+with\b",
    re.I,
)
_NO_LONGER_ITEM = re.compile(
    r"\b(?:the\s+|an?\s+)?(.+?)\s+(?:is|are)\s+no longer(?:\s+in scope)?\b",
    re.I,
)


def _normalize_scope_phrase(text: str) -> str:
    value = re.sub(r"\bapplications?\b", "app", str(text or "").lower())
    return re.sub(r"\s+", " ", value).strip(" .;:,")


def withdrawn_scope_phrases(state: dict | None) -> tuple[str, ...]:
    """Product phrases a later answer explicitly replaces or marks out of scope."""
    found: list[str] = []
    seen: set[str] = set()
    for _question, answer in _clarification_pairs(state):
        body = str(answer or "").strip()
        if not body or not _SCOPE_RETRACTION.search(body):
            continue
        if _ADDITIVE_SCOPE.search(body) and not re.search(r"\binstead\b", body, re.I):
            continue
        for clause in re.split(r"[.;]\s*", body):
            clause = clause.strip()
            if not clause:
                continue
            for match in (_REPLACE_WITH.search(clause), _NO_LONGER_ITEM.search(clause)):
                if not match:
                    continue
                phrase = _normalize_scope_phrase(match.group(1))
                if len(phrase) < 4 or phrase in seen:
                    continue
                seen.add(phrase)
                found.append(phrase)
    return tuple(found)


def _item_matches_withdrawn_phrase(item: str, phrase: str) -> bool:
    item_n = _normalize_scope_phrase(item)
    phrase_n = _normalize_scope_phrase(phrase)
    if not item_n or not phrase_n:
        return False
    if phrase_n in item_n:
        return True
    return statement_is_explicit(phrase, item)


def answer_retracts_scope(item: str, state: dict | None) -> bool:
    """True when a clarification answer explicitly removes ``item`` from scope."""
    item = str(item or "").strip()
    if not item:
        return False
    for phrase in withdrawn_scope_phrases(state):
        if _item_matches_withdrawn_phrase(item, phrase):
            return True
    for _question, answer in _clarification_pairs(state):
        body = str(answer or "").strip()
        if not body or not _SCOPE_RETRACTION.search(body):
            continue
        if _ADDITIVE_SCOPE.search(body) and not re.search(r"\binstead\b", body, re.I):
            continue
        if statement_is_explicit(item, body):
            return True
        tokens = [
            token for token in re.findall(r"[a-z0-9]{4,}", item.lower())
            if token not in _STOPWORDS and not _GENERIC_PRODUCT.fullmatch(token)
        ]
        if tokens and all(token in body.lower() for token in tokens[:3]):
            return True
    return False


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


def _iter_text_items(value):
    if value is None:
        return
    if isinstance(value, str):
        text = value.strip()
        if text:
            yield text
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_text_items(item)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_text_items(item)


def original_scope_item_still_in_force(item: str, state: dict | None) -> bool:
    """True when ``item`` restates original-request scope that was not withdrawn."""
    text = str(item or "").strip()
    request = str((state or {}).get("user_request") or "").strip()
    if not text or not request:
        return False
    if not statement_is_explicit(text, request):
        return False
    return not answer_retracts_scope(text, state)


def original_prohibition_statements(text: str) -> tuple[str, ...]:
    """Customer sentences that forbid a behavior, kept as original wording."""
    found: list[str] = []
    for raw in re.split(r"(?<=[.!?])\s+|\n+", str(text or "")):
        sentence = raw.strip()
        if not sentence:
            continue
        lower = f" {sentence.lower()} "
        if any(marker in lower for marker in _PROHIBITION_MARKERS):
            found.append(sentence)
    return tuple(found)


def in_force_scope_blob(state: dict | None) -> str:
    """Artifact text that claims current in-scope work. Excludes out-of-scope."""
    state = state or {}
    parts: list[str] = []
    discovery = state.get("discovery") or {}
    for key in ("problem", "business_goal", "users", "existing_systems", "constraints"):
        parts.extend(_iter_text_items(discovery.get(key)))
    requirements = state.get("requirements") or {}
    for key in (
        "functional_requirements",
        "non_functional_requirements",
        "acceptance_criteria",
    ):
        parts.extend(_iter_text_items(requirements.get(key)))
    solution = state.get("solution") or {}
    for key in ("solution_summary", "key_capabilities", "integration_approach"):
        parts.extend(_iter_text_items(solution.get(key)))
    parts.extend(_iter_text_items(state.get("delivery_plan")))
    parts.extend(_iter_text_items(state.get("estimate")))
    proposal = state.get("proposal") or {}
    for key in ("executive_summary", "scope"):
        parts.extend(_iter_text_items(proposal.get(key)))
    sow = state.get("sow") or {}
    for key in ("objectives", "deliverables", "in_scope", "acceptance"):
        parts.extend(_iter_text_items(sow.get(key)))
    return " ".join(parts)


def _prohibition_restated_as_capability(prohibition: str, blob: str) -> bool:
    lower = str(prohibition or "").lower()
    remainder = lower
    for marker in _PROHIBITION_MARKERS:
        remainder = remainder.replace(marker, " ")
    remainder = re.sub(r"\s+", " ", remainder).strip(" .")
    tokens = [
        token for token in re.findall(r"[a-z0-9]{4,}", remainder)
        if token not in _STOPWORDS and not _GENERIC_PRODUCT.fullmatch(token)
    ]
    if len(tokens) < 2:
        return False
    for item in re.split(r"[.\n]", str(blob or "")):
        item_lower = item.lower()
        if not item_lower.strip():
            continue
        if any(marker in f" {item_lower} " for marker in _PROHIBITION_MARKERS):
            continue
        hits = sum(1 for token in tokens if token in item_lower)
        if hits >= min(2, len(tokens)) and hits / len(tokens) >= 0.5:
            return True
    return False


def original_scope_contradictions(state: dict | None) -> list[str]:
    """Detect original requirements that artifacts dropped or inverted.

    Records contradictions. Does not reconstruct or append original sentences.
    """
    state = state or {}
    request = str(state.get("user_request") or "").strip()
    if not request:
        return []
    blob = in_force_scope_blob(state)
    findings: list[str] = []
    for outcome in stated_request_outcomes(request):
        if answer_retracts_scope(outcome, state):
            continue
        if outcome_is_covered(outcome, blob):
            continue
        findings.append(
            "Original request still in force but not reflected in delivery "
            f"artifacts: {outcome}."
        )
    for prohibition in original_prohibition_statements(request):
        if answer_retracts_scope(prohibition, state):
            continue
        if _prohibition_restated_as_capability(prohibition, blob):
            findings.append(
                "Original prohibition was restated as a positive capability: "
                f"{prohibition}"
            )
    return findings


def _item_is_forbidden_capability(item: str, request: str) -> bool:
    text = str(item or "").strip()
    if not text:
        return False
    return any(
        _prohibition_restated_as_capability(prohibition, text)
        for prohibition in original_prohibition_statements(request)
    )


def _keep_active_scope_item(item: str, state: dict | None, request: str) -> bool:
    text = str(item or "").strip()
    if not text:
        return False
    if answer_retracts_scope(text, state):
        return False
    if _item_is_forbidden_capability(text, request):
        return False
    return True


def _filter_active_scope_items(items, state: dict | None, request: str) -> list[str]:
    return [
        str(item).strip()
        for item in items or []
        if _keep_active_scope_item(item, state, request)
    ]


def apply_original_scope_consistency(state: dict | None) -> dict:
    """Keep original work out of out-of-scope and surface silent loss.

    Drops withdrawn or forbidden in-scope bullets. Does not rewrite estimates
    or inject reconstructed capabilities.
    """
    state = dict(state or {})
    request = str(state.get("user_request") or "").strip()
    if not request:
        return {}
    updates: dict = {}

    if state.get("requirements") is not None:
        requirements = dict(state.get("requirements") or {})
        for key in ("functional_requirements", "acceptance_criteria"):
            requirements[key] = _filter_active_scope_items(
                requirements.get(key), state, request
            )
        updates["requirements"] = requirements
        state["requirements"] = requirements

    if state.get("solution") is not None:
        solution = dict(state.get("solution") or {})
        for key in ("key_capabilities", "integration_approach"):
            solution[key] = _filter_active_scope_items(
                solution.get(key), state, request
            )
        updates["solution"] = solution
        state["solution"] = solution

    if state.get("proposal") is not None:
        proposal = dict(state.get("proposal") or {})
        proposal["scope"] = _filter_active_scope_items(
            proposal.get("scope"), state, request
        )
        updates["proposal"] = proposal
        state["proposal"] = proposal

    if state.get("sow") is not None:
        sow = dict(state.get("sow") or {})
        for key in ("objectives", "in_scope", "acceptance"):
            sow[key] = _filter_active_scope_items(sow.get(key), state, request)
        sow["out_of_scope"] = [
            str(item).strip()
            for item in sow.get("out_of_scope") or []
            if str(item).strip() and not original_scope_item_still_in_force(item, state)
        ]
        from app.decisions import drop_unresolved_out_of_scope_items

        sow["out_of_scope"] = drop_unresolved_out_of_scope_items(
            sow["out_of_scope"], state
        )
        updates["sow"] = sow
        state["sow"] = sow

    findings = original_scope_contradictions(state)
    if findings:
        requirements = dict(state.get("requirements") or updates.get("requirements") or {})
        existing = [str(item) for item in requirements.get("contradictions") or []]
        for item in findings:
            if item not in existing:
                existing.append(item)
        requirements["contradictions"] = existing
        updates["requirements"] = requirements
    return updates


def grounded_customer_evidence_text(state: dict | None) -> str:
    """Customer-authored text plus structured fields copied from that text.

    Discovery/requirements cannot clear a gap unless the same wording already
    appears in the customer request or clarification answers.
    """
    state = state or {}
    source = customer_authored_text(state)
    origin = source.lower()
    chunks = [source]
    discovery = state.get("discovery") or {}
    requirements = state.get("requirements") or {}

    def _add_if_customer_stated(item: str) -> None:
        text = str(item or "").strip()
        if text and text.lower() in origin:
            chunks.append(text)

    for item in _iter_text_items(requirements.get("functional_requirements")):
        _add_if_customer_stated(item)
    for item in _iter_text_items(discovery.get("users")):
        _add_if_customer_stated(item)
    for item in _iter_text_items(discovery.get("existing_systems")):
        _add_if_customer_stated(item)
    return "\n".join(chunk for chunk in chunks if str(chunk).strip())


def material_evidence_gaps(state: dict | None) -> list[EvidenceGap]:
    """Minimum missing evidence required for a responsible estimate."""
    state = state or {}
    source = customer_authored_text(state)
    grounded = grounded_customer_evidence_text(state)
    gaps: list[EvidenceGap] = []

    request_text = str(state.get("user_request") or "")
    scoped = has_first_release_scope(grounded)
    if has_substantive_first_release_scope_answer(state):
        scoped = True
    elif not scoped:
        # Evaluate clarification text without the original request so
        # "_UNDEFINED_SCOPE" on the request cannot void a later answer.
        answer_text = "\n".join(
            clarification_answer_body(question, answer)
            for question, answer in _clarification_pairs(state)
        )
        if answer_text and has_first_release_scope(answer_text):
            scoped = True
        elif has_first_release_scope(request_text):
            scoped = True

    if not scoped:
        gaps.append(EvidenceGap(
            code="first_release_scope",
            question=FIRST_RELEASE_SCOPE_QUESTION,
            reason="First-release scope is not defined well enough for a responsible estimate.",
        ))

    if not has_named_users(grounded):
        gaps.append(EvidenceGap(
            code="users",
            question="Who will use the first release, and what will they do in it?",
            reason="The primary users of the first release are not identified.",
        ))

    if needs_integration_clarity(grounded):
        gaps.append(EvidenceGap(
            code="integrations",
            question=(
                "Which systems must the first release integrate with, and what "
                "is the source of truth?"
            ),
            reason="Major integration work is implied but the systems are not named.",
        ))

    if needs_migration_clarity(grounded):
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

    answered = substantive_answered_questions(state)
    return [
        gap
        for gap in gaps
        if normalize_question_text(gap.question) not in answered
    ]


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
