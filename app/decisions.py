"""Reconcile customer clarification answers with the structured run output.

A clarification answer is authoritative over older, unresolved wording in the
original request. This module turns accumulated clarification records into
sentence-level statements, classifies each as RESOLVED or PENDING, and exposes
deterministic helpers that:

* decide whether an unknown/open question is already answered (content overlap,
  not a fixed topic list), while keeping genuinely pending items open;
* collapse equivalent open questions into one;
* write one canonical remaining-question list into discovery, requirements,
  and validation so Assessment cannot re-read a stale pre-reconciliation copy;
* write resolved product decisions into the structured requirement lists, with
  provenance, so downstream consumers do not depend on clarification prose.

Planning facts, existing-state evidence, and unanswered request-flagged items
are classified explicitly. System-inferred assumptions are never labelled as
customer-confirmed decisions. Nothing here knows about a domain, a platform
or a specific question text. The original ``user_request`` and every original
``clarification_history`` entry are never modified.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.evidence import (
    is_non_substantive_clarification_answer,
    normalize_question_text,
    unpack_clarification_record,
    _clarification_pairs,
)

SOURCE_LABEL = "customer clarification"

_STOPWORDS = frozenset(
    """
    a an the and or nor but if then than that this these those there their they them
    he she it its we our us you your i me my is are was were be been being am do does did
    have has had having will would shall should can could may might must to of in on at by
    for with from into onto over under about as per via not no yes yet still also both
    either each any all some such other more most same what which who whom whose when where
    why how whether please confirm specify provide define describe decide decided clarify
    expected required requirement requirements need needs needed want wants like use used
    using support supported supports customer customers project system solution application
    app software product first release initial phase scope detail details information
    preference preferred option options approach there here one two get gets got make makes
    undecided unknown unknowns unclear open remain remains remaining outstanding original
    request requests stated states leave leaves contradict contradicts contradiction
    later earlier answer answers answered clarification clarifications
    """.split()
)

# Wording that leaves a statement open: deferral, proposal awaiting approval, etc.
_PENDING_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bnot\s+(?:yet\s+)?(?:been\s+)?(?:approved|confirmed|decided|agreed|signed|"
        r"finali[sz]ed|determined|chosen|selected|settled|known|sure|certain|"
        r"defined|specified|established|obtained|collected)\b",
        r"\b(?:has|have|had|is|are|was|were)(?:\s+not|n['’]t)\s+(?:yet\s+)?(?:been\s+)?"
        r"(?:approved|confirmed|decided|agreed|signed|finali[sz]ed|determined|chosen|"
        r"selected|settled|established|obtained|collected)\b",
        r"\bdo not assume\b",
        r"\bmust (?:still )?be (?:obtained|collected|gathered|provided)\b",
        r"\bpending\b(?![- ]sync)",
        r"\b(?:awaiting|undecided|unconfirmed|unapproved|undetermined|tbd|tbc)\b",
        r"\bto\s+be\s+(?:confirmed|decided|approved|determined|agreed|defined|finali[sz]ed)\b",
        r"\b(?:subject\s+to|needs?|requires?|awaits?|waiting\s+for)\s+(?:\w+\s+){0,3}?"
        r"(?:approval|sign-?off|confirmation)\b",
        r"\bstill\s+(?:open|undecided|to\s+be\s+(?:decided|confirmed|agreed))\b",
        # A proposal is not a decision until it is approved.
        r"\b(?:propos(?:e|ed|es|al|als)|suggest(?:s|ed)?|tentative(?:ly)?|"
        r"provisional(?:ly)?|draft)\b",
    )
)

_QUALITY_ATTRIBUTE = re.compile(
    r"\b(security|privacy|encrypt\w*|performance|latency|throughput|availability|"
    r"uptime|accessib\w*|complian\w*|audit\w*|scalab\w*|reliab\w*|backup\w*|"
    r"retention|retain\w*)\b",
    re.I,
)

# Commercial and scheduling answers are recorded as decisions but are not
# product requirements.
_DELIVERY_ADMIN = re.compile(
    r"\b(deadline|timeline|due\s+date|go-?live|launch\s+date|budget|cost|costs|"
    r"pricing|price|invoice|payment|contract|staffing|team\s+size)\b",
    re.I,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_PROPOSAL = re.compile(
    r"\b(?:propos(?:e|ed|es|al|als)|suggest(?:s|ed)?|tentative(?:ly)?|"
    r"provisional(?:ly)?|draft)\b",
    re.I,
)
_APPROVAL_ASK = re.compile(
    r"\b(approv|sign-?off|signed off|confirm|confirmed|confirmation)\b",
    re.I,
)
_PENDING_REMAINDER = re.compile(
    r"(.+?)\s+(?:"
    r"(?:has|have|is|are)\s+"
    r"(?:not(?:\s+yet)?\s+(?:been\s+)?(approved|confirmed|decided|agreed|"
    r"signed off|finali[sz]ed|defined|specified|established)|pending\s+(?:approval|"
    r"sign-?off|confirmation|decision))"
    r"|"
    r"(?:still\s+)?needs?\s+to\s+be\s+(approved|confirmed|decided|agreed|"
    r"defined|specified|established)"
    r")",
    re.I,
)
_CAPACITY = re.compile(
    r"\b(volume|capacity|concurrent|concurrency|user counts?|peak load|"
    r"peak concurrency|usage volume)\b",
    re.I,
)
# Usage/load estimates for sizing, not disk/DR/staffing "capacity" in general.
_USAGE_ESTIMATE = re.compile(
    r"\b(?:user volumes?|usage volume|concurrent(?: load| users?|cy)?|"
    r"user counts?|number of users|peak (?:load|concurrency|concurrent)|"
    r"active installations?|inspection volumes?|photo uploads?)\b",
    re.I,
)
_ESTABLISHED_ASK = re.compile(
    r"\b(?:have|has)\b.+\bbeen\s+(?:established|defined|specified)\b",
    re.I,
)
_DIRECT_REQUEST = re.compile(
    r"^(?:what|which|how many|how much)\b",
    re.I,
)
_PLANNING_FACT = re.compile(
    r"\b(?:obtain|collect|gather)\b.+\b(?:estimates?|volume|counts?|capacity)\b|"
    r"\b(?:estimates?|volume|counts?)\s+(?:must|should|need to)\s+be\s+"
    r"(?:obtained|collected|gathered|provided)\b|"
    r"\bhas not yet been established\b|"
    r"\bnot yet been established\b|"
    r"\bdo not assume\b|"
    r"\bno (?:numerical|numeric) (?:capacity|volume|target)\b",
    re.I,
)
_EXISTING_EVIDENCE = re.compile(
    r"\b(?:api access|technical documentation)\b.+\b(?:verified|available)\b|"
    r"\b(?:have|has) (?:already\s+)?been verified\b|"
    r"\balready been verified\b",
    re.I,
)
_RESOLUTION_POLICY = re.compile(
    r"\b(?:last[- ]write[- ]wins|most recent \w+ wins|silently overwrit)\b",
    re.I,
)
_REQUEST_OPEN = re.compile(
    r"\b(?:need(?:s)?\s+clarification|still\s+need(?:s)?\s+confirmation|"
    r"have not yet decided|has not yet been decided|"
    r"has not yet been defined|have not yet been defined|"
    r"are undecided|is undecided)\b",
    re.I,
)
_INTERFACE_SCOPE = re.compile(
    r"\b(?:interface|dashboard|in[- ]scope|first[- ]release scope)\b",
    re.I,
)
_USES_PRODUCT = re.compile(
    r"\b(?:will (?:view|complete|perform|use|log)|primary users?|"
    r"use the (?:app|application|product)|mobile app)\b",
    re.I,
)
CAPACITY_COLLECTION_QUESTION = (
    "What are the expected user counts, active installations, inspection "
    "volume, photo uploads, and peak concurrency?"
)


def _stem(word: str) -> str:
    for suffix in ("ations", "ation", "ings", "ing", "ies", "ied", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            stem = word[: -len(suffix)]
            if suffix in ("ies", "ied"):
                stem += "y"
            return stem[:6]
    return word[:6]


_STOP_STEMS = frozenset(_stem(word) for word in _STOPWORDS)
_REFINEMENT_STEMS = frozenset(
    _stem(word)
    for word in (
        "detailed",
        "category",
        "categories",
        "definition",
        "matrix",
        "workflow",
        "policy",
        "policies",
        "exact",
        "resolution",
    )
)
_FRAME_STEMS = frozenset(
    _stem(word)
    for word in (
        "defined",
        "specified",
        "established",
        "exact",
        "been",
    )
)


def content_tokens(text: str) -> frozenset[str]:
    """Stemmed content words of a text, without question frames or filler."""
    tokens = set()
    for word in re.findall(r"[a-z0-9]+", str(text or "").lower()):
        if len(word) < 3 or word in _STOPWORDS:
            continue
        stem = _stem(word)
        if stem in _STOP_STEMS:
            continue
        tokens.add(stem)
    return frozenset(tokens)


def _ordered_content_stems(text: str) -> list[str]:
    stems = []
    for word in re.findall(r"[a-z0-9]+", str(text or "").lower()):
        if len(word) < 3 or word in _STOPWORDS:
            continue
        stem = _stem(word)
        if stem in _STOP_STEMS:
            continue
        stems.append(stem)
    return stems


def _stems_match(left: str, right: str) -> bool:
    if left == right:
        return True
    return (
        len(left) >= 5
        and len(right) >= 5
        and (left.startswith(right[:5]) or right.startswith(left[:5]))
    )


def _shared_stem_count(left: frozenset[str], right: frozenset[str]) -> int:
    used = set()
    shared = 0
    for item in left:
        for other in right:
            if other in used:
                continue
            if _stems_match(item, other):
                used.add(other)
                shared += 1
                break
    return shared


def content_bigrams(text: str) -> frozenset[tuple[str, str]]:
    stems = [stem for stem in _ordered_content_stems(text) if stem not in _FRAME_STEMS]
    return frozenset(zip(stems, stems[1:]))


def _matching_bigrams(first: str, second: str) -> bool:
    left, right = content_bigrams(first), content_bigrams(second)
    for a1, a2 in left:
        for b1, b2 in right:
            if _stems_match(a1, b1) and _stems_match(a2, b2):
                return True
    return False


def is_pending_text(text: str) -> bool:
    """True when the wording leaves a decision open (deferral or pending approval)."""
    value = str(text or "")
    return any(pattern.search(value) for pattern in _PENDING_PATTERNS) or bool(
        _PLANNING_FACT.search(value)
    )


@dataclass(frozen=True)
class ClarifiedStatement:
    question: str
    text: str
    resolved: bool
    tokens: frozenset[str]
    own_tokens: frozenset[str]


def _sentences(answer: str) -> list[str]:
    units = []
    for raw in _SENTENCE_SPLIT.split(str(answer or "")):
        unit = _BULLET.sub("", raw).strip()
        if unit:
            units.append(unit)
    return units


def clarified_statements(state: dict | None) -> list[ClarifiedStatement]:
    """Sentence-level statements from every substantive clarification record."""
    statements: list[ClarifiedStatement] = []
    seen_records: set[tuple[str, str]] = set()
    for question, answer in _clarification_pairs(state):
        real_question, body = unpack_clarification_record(question, answer)
        if is_non_substantive_clarification_answer(body):
            continue
        key = (normalize_question_text(real_question), normalize_question_text(body))
        if key in seen_records:
            continue
        seen_records.add(key)

        question_tokens = content_tokens(real_question)
        units = _sentences(body)
        pending = [is_pending_text(unit) for unit in units]
        # A short follow-up such as "That is not yet approved." qualifies the
        # sentence before it.
        for index, unit in enumerate(units):
            if pending[index] and index > 0 and len(content_tokens(unit)) < 3:
                pending[index - 1] = True
        for unit, is_pending in zip(units, pending):
            own = content_tokens(unit)
            if is_non_substantive_clarification_answer(unit) and not is_pending:
                continue
            statements.append(
                ClarifiedStatement(
                    question=real_question,
                    text=unit,
                    resolved=not is_pending,
                    tokens=own | question_tokens,
                    own_tokens=own,
                )
            )
    return statements


def _overlaps(item_tokens: frozenset[str], other_tokens: frozenset[str]) -> bool:
    if not item_tokens:
        return False
    shared = len(item_tokens & other_tokens)
    if shared < min(2, len(item_tokens)):
        return False
    coverage = shared / len(item_tokens)
    # A long unknown can restate a decision in many words; three shared
    # content words still identify the subject.
    return coverage >= 0.5 or (shared >= 3 and coverage >= 0.3)


class ClarificationDecisions:
    """Resolved and pending customer statements for one run."""

    def __init__(self, state: dict | None):
        self.statements = clarified_statements(state)
        self.resolved = [s for s in self.statements if s.resolved]
        self.pending = [s for s in self.statements if not s.resolved]

    def is_pending(self, text: str) -> bool:
        return any(_pending_matches_question(statement, text) for statement in self.pending)

    def resolves(self, text: str) -> bool:
        """True when a resolved answer covers ``text`` and no pending remainder does.

        Coverage uses the answer body (``own_tokens``), not the original
        question mixed into the statement. A pending remainder on the same
        original question therefore cannot keep a broader, already-answered
        question open, and mentioning an activity does not close a still
        unanswered detailed-requirements question.
        """
        tokens = content_tokens(text)
        covered = any(_statement_covers(statement, text) for statement in self.resolved)
        if not covered:
            related = set()
            for statement in self.resolved:
                if (
                    (statement.question.strip() and questions_equivalent(text, statement.question))
                    or (tokens & statement.own_tokens)
                ):
                    related |= statement.own_tokens
            subject = tokens - _FRAME_STEMS
            if subject and _overlaps(subject, related):
                refinement = _refinement_tokens(text) - _FRAME_STEMS
                if not refinement or (refinement & related):
                    covered = True
        if not covered:
            return False
        if any(
            statement.question.strip()
            and normalize_question_text(text)
            == normalize_question_text(statement.question)
            for statement in self.pending
        ):
            return False
        return not any(_overlaps(tokens, statement.own_tokens) for statement in self.pending)

    def pending_questions(self) -> list[str]:
        """Original clarification questions that still have a pending remainder."""
        questions: list[str] = []
        for statement in self.pending:
            question = statement.question.strip()
            if question and question not in questions:
                questions.append(question)
        return questions

    def remainder_questions(self) -> list[str]:
        """Narrow remaining questions for pending statements, not the original broads."""
        grouped: dict[str, list[ClarifiedStatement]] = {}
        for statement in self.pending:
            key = normalize_question_text(statement.question) or normalize_question_text(
                statement.text
            )
            grouped.setdefault(key, []).append(statement)
        remainders: list[str] = []
        for statements in grouped.values():
            original = statements[0].question.strip()
            remainders.append(_narrowed_from_pending(original, statements))
        return remainders


def question_text(item) -> str:
    """Question string from a free-text or structured question item."""
    if isinstance(item, dict):
        return str(item.get("question") or item.get("text") or "").strip()
    return str(item or "").strip()


def _same_question_text(first: str, second: str) -> bool:
    """True when two questions are the same string after trivial formatting.

    Collapses leading/trailing whitespace and internal run-on spaces. Does not
    treat differently worded questions as the same.
    """
    left = normalize_question_text(first)
    return bool(left) and left == normalize_question_text(second)


def _with_question_text(item, text: str):
    if isinstance(item, dict):
        updated = dict(item)
        updated["question"] = text
        return updated
    return text


def questions_equivalent(first: str, second: str) -> bool:
    """True when two questions ask about the same remaining decision."""
    a = content_tokens(first) - _FRAME_STEMS
    b = content_tokens(second) - _FRAME_STEMS
    if not a or not b:
        return False
    shared = _shared_stem_count(a, b)
    if shared < min(2, len(a), len(b)):
        # A two-word label such as "Hosting arrangements" still matches its
        # long form when every content word is covered.
        if shared >= 1 and (shared / min(len(a), len(b)) >= 1.0 and min(len(a), len(b)) <= 2):
            return True
        return _matching_bigrams(first, second)
    smaller = min(len(a), len(b))
    larger = max(len(a), len(b))
    if shared / smaller >= 0.8 and (shared / larger >= 0.5 or smaller <= 3):
        return True
    if shared >= 3 and shared / smaller >= 0.5:
        return True
    if _matching_bigrams(first, second) and shared >= 2:
        return True
    # "Have these usage figures been established?" asks for the same
    # capacity inputs as "What is the expected user volume and load?"
    if _is_usage_estimate_question(first) and _is_usage_estimate_question(second):
        return True
    return False


def _is_approval_question(text: str) -> bool:
    return bool(_APPROVAL_ASK.search(str(text or "")))


def _has_proposal(text: str) -> bool:
    return bool(_PROPOSAL.search(str(text or "")))


def _is_capacity_text(text: str) -> bool:
    return bool(_CAPACITY.search(str(text or "")))


def _is_usage_estimate_question(text: str) -> bool:
    """True for questions that collect the same usage/load sizing inputs."""
    return bool(_USAGE_ESTIMATE.search(str(text or "")))


def _is_established_question(text: str) -> bool:
    """True for 'Has/Have … been established/defined?' information checks."""
    return bool(_ESTABLISHED_ASK.search(str(text or "")))


def _is_direct_request_question(text: str) -> bool:
    """True for a direct request for the missing information."""
    return bool(_DIRECT_REQUEST.match(str(text or "").strip()))


def _statement_covers(statement: ClarifiedStatement, text: str) -> bool:
    """True when this resolved statement actually answers ``text``.

    Distinct remaining decisions (detailed requirements, exact workflow,
    permission matrix) stay open unless the answer body itself carries those
    refinement tokens. Generated requirements and stale payload text are not
    consulted.
    """
    tokens = content_tokens(text)
    if not tokens:
        return False
    if statement.question.strip() and questions_equivalent(text, statement.question):
        return True
    if not _overlaps(tokens, statement.own_tokens):
        return False
    refinement = _refinement_tokens(text)
    if refinement and not (refinement & statement.own_tokens):
        return False
    return True


def _refinement_tokens(text: str) -> frozenset[str]:
    """Refinement stems taken from raw wording, including stopworded 'detail'."""
    stems = set()
    for word in re.findall(r"[a-z0-9]+", str(text or "").lower()):
        stem = _stem(word)
        if stem in _REFINEMENT_STEMS:
            stems.add(stem)
    return frozenset(stems)


def _pending_matches_question(statement: ClarifiedStatement, text: str) -> bool:
    """True when a pending remainder belongs to this question.

    Remainder-frame words (exact/defined/workflow templates) are not enough
    to attach one pending decision to a different remaining question.
    Equivalence to the original broad question is not used here: that would
    keep already-answered broad wording open whenever a narrower remainder
    still exists.
    """
    if statement.question.strip() and normalize_question_text(text) == normalize_question_text(
        statement.question
    ):
        return True
    return _overlaps(
        content_tokens(text) - _FRAME_STEMS,
        statement.own_tokens - _FRAME_STEMS,
    )


def _pending_has_proposal(text: str, decisions: ClarificationDecisions) -> bool:
    tokens = content_tokens(text)
    return any(
        _has_proposal(statement.text) and _overlaps(tokens, statement.own_tokens)
        for statement in decisions.pending
    )


def _question_from_pending_text(text: str) -> str:
    blob = str(text or "").strip()
    if blob.endswith("?"):
        return blob
    remainder = blob
    for separator in (r"\bbut\b", r";"):
        match = re.search(separator, remainder)
        if match:
            remainder = remainder[match.end():].strip()
            break
    remainder = remainder.strip(" ;.")
    parsed = _PENDING_REMAINDER.search(remainder)
    if not parsed:
        parsed = _PENDING_REMAINDER.search(blob)
    if not parsed:
        return ""
    subject = re.sub(r"^(that|the|whether)\s+", "", parsed.group(1).strip(), flags=re.I)
    subject = subject.rstrip(" ,")
    verb = next((group for group in parsed.groups()[1:] if group), "approved")
    verb = verb.lower().replace("signed off", "signed off")
    if not subject:
        return ""
    aux = "Have" if (" and " in subject.lower() or subject.lower().endswith("s")) else "Has"
    if "sign" in verb:
        return f"{aux} {subject} been signed off?"
    if verb in {"decided", "agreed"}:
        return f"Has {subject} been {verb}?"
    return f"{aux} {subject} been {verb}?"


def _narrowed_from_pending(original: str, pending: list[ClarifiedStatement]) -> str:
    original = str(original or "").strip()
    blob = " ".join(statement.text for statement in pending)
    if _is_capacity_text(blob) and not _has_proposal(blob):
        if original.endswith("?") and not _is_approval_question(original):
            return original
        return CAPACITY_COLLECTION_QUESTION
    if original.endswith("?") and not _has_proposal(blob) and not re.search(
        r"signed off|sign-off|"
        r"not(?:\s+yet)?(?:\s+been)?\s+(?:defined|specified|established|decided)|"
        r"not(?:\s+yet)?\s+been\s+approved|"
        r"has not been (?:decided|approved)|"
        r"(?:still\s+)?needs?\s+to\s+be\s+(?:defined|specified|established|decided|approved|confirmed)",
        blob,
        re.I,
    ):
        return original
    candidate = _question_from_pending_text(blob)
    if candidate:
        if _is_capacity_text(candidate) and not _has_proposal(blob):
            return original if original.endswith("?") and not _is_approval_question(original) else CAPACITY_COLLECTION_QUESTION
        return candidate
    if _has_proposal(blob) and original.endswith("?"):
        stem = re.sub(
            r"^(what are the|what is the|what are|what is|which|who|how|when|where)\s+",
            "",
            original.rstrip("?").strip(),
            flags=re.I,
        )
        if stem:
            return f"Has the proposed {stem} been approved?"
    return original or next((s.text for s in pending if s.text), "")


def dedupe_equivalent_questions(items: list) -> list:
    """Drop later questions equivalent to an earlier one. Keeps first occurrence."""
    kept: list = []
    kept_text: list[str] = []
    for item in items or []:
        text = str(item.get("question") if isinstance(item, dict) else item or "")
        if not text.strip():
            continue
        if any(
            _same_question_text(text, existing) or questions_equivalent(text, existing)
            for existing in kept_text
        ):
            continue
        kept.append(item)
        kept_text.append(text)
    return kept


def drop_resolved(items: list, decisions: ClarificationDecisions) -> list:
    """Remove unresolved items that a resolved clarification already answers."""
    if not decisions.resolved:
        return list(items or [])
    kept = []
    for item in items or []:
        text = question_text(item)
        if decisions.resolves(text):
            continue
        kept.append(item)
    return kept


def _prefer_remaining(current: str, candidate: str, decisions: ClarificationDecisions) -> str:
    """Pick the remaining-decision wording when two questions are equivalent.

    Approval phrasing is used only when the customer actually proposed
    something. Capacity follow-ups without a numerical proposal stay as
    estimate-collection questions, not approval of an unspecified volume.
    """
    if current.endswith("?") and not str(candidate).endswith("?"):
        return current
    if str(candidate).endswith("?") and not current.endswith("?"):
        return candidate
    pending_context = decisions.is_pending(current) or decisions.is_pending(candidate)
    has_proposal = (
        _pending_has_proposal(current, decisions)
        or _pending_has_proposal(candidate, decisions)
        or _has_proposal(current)
        or _has_proposal(candidate)
    )
    if pending_context and has_proposal:
        if _is_approval_question(candidate) and not _is_approval_question(current):
            return candidate
        if _is_approval_question(current) and not _is_approval_question(candidate):
            return current
    elif pending_context or _is_capacity_text(current) or _is_capacity_text(candidate):
        if _is_approval_question(candidate) and not _is_approval_question(current):
            return current
        if _is_approval_question(current) and not _is_approval_question(candidate):
            return candidate
    if _is_usage_estimate_question(current) and _is_usage_estimate_question(candidate):
        current_direct = _is_direct_request_question(current) and not _is_established_question(
            current
        )
        candidate_direct = _is_direct_request_question(candidate) and not _is_established_question(
            candidate
        )
        if current_direct and not candidate_direct:
            return current
        if candidate_direct and not current_direct:
            return candidate
        if not current_direct and not candidate_direct:
            return CAPACITY_COLLECTION_QUESTION
    if len(content_tokens(candidate)) > len(content_tokens(current)):
        return candidate
    return current


def _is_generalization_of(general: str, specific: str) -> bool:
    """True when ``general`` is a shorter restatement of ``specific``."""
    if normalize_question_text(general) == normalize_question_text(specific):
        return False
    g, s = content_tokens(general), content_tokens(specific)
    if not g or not s or len(g) >= len(s):
        return False
    shared = _shared_stem_count(g, s)
    return shared >= min(2, len(g)) and shared / len(g) >= 0.8


def _is_broader_question(broad: str, specific: str) -> bool:
    """True when ``broad`` restates a topic already narrowed in ``specific``.

    The specific question must add a remaining-decision refinement (workflow,
    resolution, policy, matrix) that the broad question does not ask. Shared
    topic words alone, such as hosting or photo, do not collapse distinct
    decisions.
    """
    if _same_question_text(broad, specific):
        return False
    b = content_tokens(broad) - _FRAME_STEMS
    s = content_tokens(specific) - _FRAME_STEMS
    if not b or not s or b == s:
        return False
    extra = s - b
    if not (extra & _REFINEMENT_STEMS):
        return False
    shared = _shared_stem_count(b, s)
    return shared >= min(2, len(b)) and shared / len(b) >= 0.5


def reconcile_open_questions(questions: list, state: dict | None) -> list:
    """Close, replace, or keep questions against all clarification answers.

    Resolved questions are dropped. A pending remainder replaces the original
    broad question. Equivalent paraphrases collapse to one canonical item.
    Distinct remaining decisions on the same topic stay separate.
    """
    decisions = ClarificationDecisions(state)
    rewritten = []
    for item in questions or []:
        text = question_text(item)
        if not text:
            continue
        pending_hits = [
            statement
            for statement in decisions.pending
            if _pending_matches_question(statement, text)
        ]
        if decisions.resolves(text) and not pending_hits:
            continue
        if pending_hits:
            source = pending_hits[0].question.strip() or text
            text = _narrowed_from_pending(source, pending_hits)
            item = _with_question_text(item, text)
        rewritten.append(item)

    kept: list = []
    kept_text: list[str] = []
    for item in rewritten:
        text = question_text(item)
        match = next(
            (
                index
                for index, existing in enumerate(kept_text)
                if _same_question_text(text, existing)
                or questions_equivalent(text, existing)
            ),
            None,
        )
        if match is None:
            kept.append(item)
            kept_text.append(text)
            continue
        if _same_question_text(text, kept_text[match]):
            continue
        if _prefer_remaining(kept_text[match], text, decisions) == text:
            kept[match] = item
            kept_text[match] = text

    for index, text in enumerate(kept_text):
        if (
            _is_usage_estimate_question(text)
            and _is_established_question(text)
            and not _is_direct_request_question(text)
        ):
            kept_text[index] = CAPACITY_COLLECTION_QUESTION
            kept[index] = _with_question_text(kept[index], CAPACITY_COLLECTION_QUESTION)

    final = []
    for item, text in zip(kept, kept_text):
        if any(_is_generalization_of(text, other) for other in kept_text):
            continue
        if any(
            _is_broader_question(text, other)
            for other in kept_text
            if not _same_question_text(text, other)
        ):
            continue
        final.append(item)
    return final


def _covered(statement_tokens: frozenset[str], texts: list[str]) -> bool:
    if not statement_tokens:
        return True
    # Strict on purpose: a decision that only partly overlaps an existing
    # requirement (for example, missing its qualifying condition) is new.
    allowed_missing = len(statement_tokens) // 8
    return any(
        len(statement_tokens - content_tokens(text)) <= allowed_missing
        for text in texts
    )


def _sentence_case(text: str) -> str:
    text = text.strip().rstrip(".;")
    return text[:1].upper() + text[1:] if text else text


def _requirement_text(statement: ClarifiedStatement) -> str:
    if len(statement.own_tokens) >= 3 or not statement.question.strip():
        body = _sentence_case(statement.text)
    else:
        body = f"{statement.question.strip().rstrip('?')}: {_sentence_case(statement.text)}"
    return f"{body} (Source: {SOURCE_LABEL})"


def _requirement_body(text: str) -> str:
    body = str(text or "")
    body = re.sub(r"^Verified by demonstration or test that:\s*", "", body, flags=re.I)
    body = re.sub(r"\s*\(Source:.*\)$", "", body)
    return body.strip()


def _is_non_product_requirement(text: str) -> bool:
    """True for planning actions and existing-state evidence, not product behavior."""
    body = _requirement_body(text)
    return bool(_PLANNING_FACT.search(body) or _EXISTING_EVIDENCE.search(body))


def _unsupported_resolution_policy(text: str, decisions: ClarificationDecisions) -> bool:
    """True when a generated last-write/overwrite policy was not customer-confirmed."""
    if not _RESOLUTION_POLICY.search(str(text or "")):
        return False
    return not any(_RESOLUTION_POLICY.search(statement.text) for statement in decisions.resolved)


def _is_product_statement(statement: ClarifiedStatement) -> bool:
    blob = f"{statement.question} {statement.text}"
    if _DELIVERY_ADMIN.search(blob):
        return False
    if _is_non_product_requirement(statement.text):
        return False
    return True


def _filter_requirement_list(items: list[str], decisions: ClarificationDecisions) -> list[str]:
    return [
        item
        for item in items
        if not _is_non_product_requirement(item)
        and not _unsupported_resolution_policy(item, decisions)
    ]


def apply_decisions_to_requirements(requirements: dict | None, state: dict | None) -> dict:
    """Write resolved product decisions into requirements and keep pending ones open.

    Resolved product-behavior statements become sourced requirements (and
    acceptance criteria) unless an equivalent entry already exists. Planning
    facts, capacity unknowns, and existing-state evidence stay in
    ``clarified_decisions`` with provenance but are not turned into product
    requirements or "Verified by demonstration..." criteria. Pending
    statements keep their question open.
    """
    requirements = dict(requirements or {})
    decisions = ClarificationDecisions(state)
    if not decisions.statements:
        return requirements

    functional = _filter_requirement_list(
        [str(i) for i in requirements.get("functional_requirements") or []],
        decisions,
    )
    non_functional = _filter_requirement_list(
        [str(i) for i in requirements.get("non_functional_requirements") or []],
        decisions,
    )
    acceptance = _filter_requirement_list(
        [str(i) for i in requirements.get("acceptance_criteria") or []],
        decisions,
    )

    for statement in decisions.resolved:
        if not _is_product_statement(statement):
            continue
        tokens = statement.own_tokens if len(statement.own_tokens) >= 2 else statement.tokens
        if not _covered(tokens, functional + non_functional):
            text = _requirement_text(statement)
            if _QUALITY_ATTRIBUTE.search(statement.text):
                non_functional.append(text)
            else:
                functional.append(text)
        if not _covered(tokens, acceptance):
            acceptance.append(
                "Verified by demonstration or test that: "
                f"{_sentence_case(statement.text)} (Source: {SOURCE_LABEL})"
            )

    open_questions = reconcile_open_questions(
        [str(i) for i in requirements.get("open_questions") or []]
        + decisions.remainder_questions()
        + unanswered_request_items(state),
        state,
    )

    requirements["functional_requirements"] = functional
    requirements["non_functional_requirements"] = non_functional
    requirements["acceptance_criteria"] = acceptance
    requirements["open_questions"] = [question_text(item) for item in open_questions]
    requirements["clarified_decisions"] = [
        {
            "question": statement.question,
            "decision": statement.text,
            "status": "RESOLVED" if statement.resolved else "PENDING",
            "source": SOURCE_LABEL,
        }
        for statement in decisions.statements
    ]
    return requirements


def _as_open_question(subject: str) -> str:
    text = re.sub(r"\b(?:also|still)\s*$", "", str(subject or "").strip().rstrip(". "), flags=re.I).strip()
    if not text:
        return ""
    if text.endswith("?"):
        return text
    if re.match(r"^(which|what|who|how|when|where|whether)\b", text, re.I):
        return text + "?"
    text = re.sub(r"^(?:the|a|an)\s+", "", text, flags=re.I)
    return f"What are the {text}?"


def _subject_already_in_dialogue(subject: str, decisions: ClarificationDecisions) -> bool:
    tokens = content_tokens(subject)
    if not tokens:
        return False
    if decisions.resolves(subject) or decisions.is_pending(subject):
        return True
    refinement = _refinement_tokens(subject)
    for statement in decisions.statements:
        question_tokens = content_tokens(statement.question)
        related = question_tokens | statement.own_tokens
        shared = tokens & related
        if statement.question.strip() and (
            questions_equivalent(subject, statement.question)
            or _overlaps(question_tokens, tokens)
        ):
            if refinement and not (refinement & related):
                continue
            return True
        if shared and (len(shared) >= min(2, len(tokens)) or len(tokens) <= 3):
            if refinement and not (refinement & related):
                continue
            return True
    return False


def unanswered_request_items(state: dict | None) -> list[str]:
    """Restore request-flagged decisions that later answers never addressed.

    Uses the original request's "needs clarification" / "undecided" clauses,
    not a domain-specific checklist. Coordinated subjects are split so that
    answering hosting does not drop an unanswered checklist item.
    """
    request = str((state or {}).get("user_request") or "")
    if not request:
        return []
    decisions = ClarificationDecisions(state)
    found: list[str] = []
    for sentence in _sentences(request):
        match = _REQUEST_OPEN.search(sentence)
        if not match:
            continue
        head = sentence[: match.start()].strip()
        tail = sentence[match.end():].strip()
        subjects = [part.strip() for part in re.split(r",|\band\b", head) if part.strip()]
        whether = re.match(r"whether\s+(.+)", tail, re.I)
        if whether:
            subjects.append(whether.group(1).strip(" ."))
        if not subjects:
            subjects = [sentence]
        for subject in subjects:
            if len(content_tokens(subject)) < 2:
                continue
            if _subject_already_in_dialogue(subject, decisions):
                continue
            question = _as_open_question(subject)
            if question and question not in found:
                found.append(question)
    return found


def active_open_questions(state: dict | None, extras: list | None = None) -> list[str]:
    """Canonical remaining questions after later clarification answers.

    Combines current artifact lists, pending remainders, and unanswered
    request-flagged items, then closes, narrows, and deduplicates them.
    """
    decisions = ClarificationDecisions(state)
    combined = [
        question_text(item)
        for item in (extras or [])
        if question_text(item)
    ]
    combined.extend(decisions.remainder_questions())
    combined.extend(unanswered_request_items(state))
    return [question_text(item) for item in reconcile_open_questions(combined, state)]


def reconcile_discovery_actors(discovery: dict | None, state: dict | None) -> dict:
    """Keep confirmed product users; move unresolved-interface roles to stakeholders.

    Review participation does not, by itself, prove that a named role uses a
    dedicated first-release interface.
    """
    discovery = dict(discovery or {})
    decisions = ClarificationDecisions(state)
    users: list[str] = []
    stakeholders = [str(item) for item in discovery.get("stakeholders") or [] if str(item).strip()]
    for user in discovery.get("users") or []:
        label = str(user).strip()
        if not label:
            continue
        mentions = [
            statement
            for statement in decisions.statements
            if _overlaps(content_tokens(label), statement.own_tokens)
            or label.lower() in f"{statement.text} {statement.question}".lower()
        ]
        if not mentions:
            users.append(label)
            continue
        uses_product = any(
            statement.resolved and _USES_PRODUCT.search(statement.text)
            for statement in mentions
        )
        pending_interface = any(
            (not statement.resolved) and _INTERFACE_SCOPE.search(f"{statement.text} {statement.question}")
            for statement in decisions.pending
            if any(
                statement.question == mention.question
                or _overlaps(content_tokens(label), statement.own_tokens)
                for mention in mentions
            )
        )
        if pending_interface and not uses_product:
            if label not in stakeholders:
                stakeholders.append(label)
            continue
        users.append(label)
    discovery["users"] = users
    discovery["stakeholders"] = stakeholders
    return discovery


def apply_reconciled_project_state(state: dict | None) -> dict:
    """Persist one reconciled project state into discovery, requirements, and validation.

    Call this after later clarification answers and before Assessment, print,
    export, or downstream serialization. ``user_request`` and
    ``clarification_history`` are not returned and must not be rewritten by
    callers.
    """
    state = dict(state or {})
    discovery = dict(state.get("discovery") or {})
    requirements = apply_decisions_to_requirements(state.get("requirements"), state)
    validation = dict(state.get("validation") or {})
    extras = []
    for collection in (
        discovery.get("unknowns"),
        discovery.get("clarification_questions"),
        requirements.get("open_questions"),
        validation.get("non_blocking_questions"),
        state.get("non_blocking_questions"),
    ):
        extras.extend(collection or [])
    questions = active_open_questions(state, extras)
    if state.get("discovery") is not None:
        discovery = reconcile_discovery_actors(discovery, state)
        discovery["unknowns"] = list(questions)
    requirements["open_questions"] = list(questions)
    validation["non_blocking_questions"] = list(questions)
    updates = {"requirements": requirements, "validation": validation}
    if state.get("discovery") is not None:
        updates["discovery"] = discovery
    return updates
