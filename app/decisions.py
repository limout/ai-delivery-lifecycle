"""Reconcile customer clarification answers with the structured run output.

A clarification answer is authoritative over older, unresolved wording in the
original request. This module turns accumulated clarification records into
sentence-level statements, classifies each as RESOLVED or PENDING, and exposes
deterministic helpers that:

* decide whether an unknown/open question is already answered (content overlap,
  not a fixed topic list), while keeping genuinely pending items open;
* collapse equivalent open questions into one;
* write resolved decisions into the structured requirement lists, with
  provenance, so downstream consumers do not depend on clarification prose.

Nothing here knows about a domain, a platform or a specific question text.
The original ``user_request`` is never modified.
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
    conflict conflicts conflicting later earlier answer answers answered clarification
    clarifications
    """.split()
)

# Wording that leaves a statement open: deferral, proposal awaiting approval, etc.
_PENDING_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bnot\s+(?:yet\s+)?(?:been\s+)?(?:approved|confirmed|decided|agreed|signed|"
        r"finali[sz]ed|determined|chosen|selected|settled|known|sure|certain)\b",
        r"\b(?:has|have|had|is|are|was|were)(?:\s+not|n['’]t)\s+(?:yet\s+)?(?:been\s+)?"
        r"(?:approved|confirmed|decided|agreed|signed|finali[sz]ed|determined|chosen|"
        r"selected|settled)\b",
        r"\b(?:pending|awaiting|undecided|unconfirmed|unapproved|undetermined|tbd|tbc)\b",
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


def _stem(word: str) -> str:
    for suffix in ("ations", "ation", "ings", "ing", "ies", "ied", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            stem = word[: -len(suffix)]
            if suffix in ("ies", "ied"):
                stem += "y"
            return stem[:6]
    return word[:6]


_STOP_STEMS = frozenset(_stem(word) for word in _STOPWORDS)


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


def is_pending_text(text: str) -> bool:
    """True when the wording leaves a decision open (deferral or pending approval)."""
    return any(pattern.search(str(text or "")) for pattern in _PENDING_PATTERNS)


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
        tokens = content_tokens(text)
        return any(_overlaps(tokens, s.tokens) for s in self.pending)

    def resolves(self, text: str) -> bool:
        """True when a resolved answer covers ``text`` and no pending one does."""
        tokens = content_tokens(text)
        if not tokens or not any(_overlaps(tokens, s.tokens) for s in self.resolved):
            return False
        return not any(_overlaps(tokens, s.tokens) for s in self.pending)

    def pending_questions(self) -> list[str]:
        questions: list[str] = []
        for statement in self.pending:
            question = statement.question.strip()
            if question and question not in questions:
                questions.append(question)
        return questions


def questions_equivalent(first: str, second: str) -> bool:
    """True when two questions ask about the same subject."""
    a, b = content_tokens(first), content_tokens(second)
    if not a or not b:
        return False
    shared = len(a & b)
    if shared < min(2, len(a), len(b)):
        return False
    return shared / min(len(a), len(b)) >= 0.8 and shared / max(len(a), len(b)) >= 0.5


def dedupe_equivalent_questions(items: list) -> list:
    """Drop later questions equivalent to an earlier one. Keeps first occurrence."""
    kept: list = []
    kept_text: list[str] = []
    for item in items or []:
        text = str(item.get("question") if isinstance(item, dict) else item or "")
        if not text.strip():
            continue
        if any(questions_equivalent(text, existing) for existing in kept_text):
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
        text = item.get("question") if isinstance(item, dict) else str(item)
        if decisions.resolves(str(text or "")):
            continue
        kept.append(item)
    return kept


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


def apply_decisions_to_requirements(requirements: dict | None, state: dict | None) -> dict:
    """Write resolved decisions into requirements and keep pending ones open.

    Resolved statements become sourced requirements (and acceptance criteria)
    unless an equivalent entry already exists. Pending statements keep their
    question open. A structured ``clarified_decisions`` list records both.
    """
    requirements = dict(requirements or {})
    decisions = ClarificationDecisions(state)
    if not decisions.statements:
        return requirements

    functional = [str(i) for i in requirements.get("functional_requirements") or []]
    non_functional = [str(i) for i in requirements.get("non_functional_requirements") or []]
    acceptance = [str(i) for i in requirements.get("acceptance_criteria") or []]

    for statement in decisions.resolved:
        if _DELIVERY_ADMIN.search(f"{statement.question} {statement.text}"):
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

    open_questions = [str(i) for i in requirements.get("open_questions") or []]
    for question in decisions.pending_questions():
        if not any(questions_equivalent(question, existing) for existing in open_questions):
            open_questions.append(question)

    requirements["functional_requirements"] = functional
    requirements["non_functional_requirements"] = non_functional
    requirements["acceptance_criteria"] = acceptance
    requirements["open_questions"] = dedupe_equivalent_questions(
        drop_resolved(open_questions, decisions)
    )
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
