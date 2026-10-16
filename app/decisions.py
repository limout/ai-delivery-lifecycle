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

from app.assessment import repair_generated_grammar
from app.evidence import (
    _GENERIC_OBJECT_TOKENS,
    answer_retracts_scope,
    behavior_signatures,
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
        r"\b(?:will|must|should)\s+be\s+(?:confirmed|decided|approved|determined|agreed|defined|finali[sz]ed|specified|established)\b",
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


def _canonical_clarification_state(state: dict | None) -> dict:
    value = (state or {}).get("clarification_state")
    return value if isinstance(value, dict) else {}


def _canonical_decision_statements(state: dict | None) -> list[ClarifiedStatement]:
    canonical = _canonical_clarification_state(state)
    statements: list[ClarifiedStatement] = []
    seen: set[tuple[str, str, bool]] = set()
    for item in canonical.get("decisions") or []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        text = str(item.get("decision") or item.get("text") or "").strip()
        if not text:
            continue
        status = str(item.get("status") or "").strip().upper()
        resolved = status != "PENDING"
        key = (normalize_question_text(question), normalize_question_text(text), resolved)
        if key in seen:
            continue
        seen.add(key)
        question_tokens = content_tokens(question)
        own = content_tokens(text)
        statements.append(
            ClarifiedStatement(
                question=question,
                text=text,
                resolved=resolved,
                tokens=own | question_tokens,
                own_tokens=own,
            )
        )
    return statements


def _sentences(answer: str) -> list[str]:
    units = []
    for raw in _SENTENCE_SPLIT.split(str(answer or "")):
        unit = _BULLET.sub("", raw).strip()
        if unit:
            units.append(unit)
    return units


def _statements_from_legacy_sources(state: dict | None) -> list[ClarifiedStatement]:
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


def _statement_key(statement: ClarifiedStatement) -> tuple[str, str, bool]:
    return (
        normalize_question_text(statement.question),
        normalize_question_text(statement.text),
        statement.resolved,
    )


def _merged_clarification_statements(state: dict | None) -> list[ClarifiedStatement]:
    """Union freshly parsed answers with previously persisted ledger decisions.

    New history, ``new_clarification_records``, and ``clarification_answers``
    are parsed first so a later turn can add facts. Canonical decisions fill
    any accepted sentences that a partial client history omitted.
    """
    merged: list[ClarifiedStatement] = []
    seen: set[tuple[str, str, bool]] = set()
    for statement in (
        *_statements_from_legacy_sources(state),
        *_canonical_decision_statements(state),
    ):
        key = _statement_key(statement)
        if key in seen:
            continue
        seen.add(key)
        merged.append(statement)
    return merged


def clarified_statements(state: dict | None) -> list[ClarifiedStatement]:
    """Sentence-level statements from canonical state and legacy records.

    ``clarification_state`` is the authoritative, serialized ledger once a
    workflow response has carried it forward. Legacy clarification records are
    still parsed so new answers merge into an existing ledger instead of being
    ignored, and so old payloads without a ledger keep working.
    """
    return _merged_clarification_statements(state)


def _accepted_answer_records(state: dict | None) -> list[dict]:
    records: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for question, answer in _clarification_pairs(state):
        real_question, body = unpack_clarification_record(question, answer)
        if not str(body or "").strip():
            continue
        key = (normalize_question_text(real_question), normalize_question_text(body))
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "question": real_question,
                "answer": body,
                "status": (
                    "NON_SUBSTANTIVE"
                    if is_non_substantive_clarification_answer(body)
                    else "ACCEPTED"
                ),
                "source": SOURCE_LABEL,
            }
        )
    for item in _canonical_clarification_state(state).get("answers") or []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if not answer:
            continue
        key = (normalize_question_text(question), normalize_question_text(answer))
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "question": question,
                "answer": answer,
                "status": str(item.get("status") or "ACCEPTED").upper(),
                "source": str(item.get("source") or SOURCE_LABEL),
            }
        )
    return records


def _question_status_record(
    question: str,
    status: str,
    priority: str,
    blocks_workflow: bool,
    reason: str = "",
) -> dict:
    return {
        "question": str(question or "").strip(),
        "status": str(status or "OPEN").upper(),
        "priority": str(priority or "RECOMMENDED").upper(),
        "blocks_workflow": bool(blocks_workflow),
        "reason": str(reason or ""),
    }


def _iter_question_records(items, required: bool):
    for item in items or []:
        text = question_text(item)
        if not text:
            continue
        if isinstance(item, dict):
            blocks = bool(item.get("blocks_workflow", required))
            priority = str(
                item.get("priority")
                or ("REQUIRED" if blocks or required else "RECOMMENDED")
            ).upper()
            reason = str(item.get("reason") or "")
        else:
            blocks = required
            priority = "REQUIRED" if required else "RECOMMENDED"
            reason = ""
        yield _question_status_record(text, "OPEN", priority, blocks or required, reason)


def build_clarification_state(
    state: dict | None,
    blocking_questions: list | None = None,
    non_blocking_questions: list | None = None,
) -> dict:
    """Build the canonical clarification ledger carried between workflow runs.

    The ledger intentionally stores machine-readable facts, not display-only
    phrasing patches:

    * ``answers`` are customer-authored answer records with acceptance status.
    * ``decisions`` are sentence-level resolved/pending decisions consumed by
      ``ClarificationDecisions`` on the next run.
    * ``questions`` is the reconciled UI-facing question state, including
      priority and blocking semantics.
    """
    state = dict(state or {})
    previous = _canonical_clarification_state(state)
    answers = _accepted_answer_records(state)
    source_statements = _merged_clarification_statements(state)

    decisions = [
        {
            "question": statement.question,
            "decision": statement.text,
            "status": "RESOLVED" if statement.resolved else "PENDING",
            "source": SOURCE_LABEL,
        }
        for statement in source_statements
    ]

    previous_questions: dict[str, dict] = {}
    for item in previous.get("questions") or []:
        if not isinstance(item, dict):
            continue
        text = question_text(item)
        if text:
            previous_questions[normalize_question_text(text)] = dict(item)

    question_records: list[dict] = []
    seen_questions: set[str] = set()

    def add_question(record: dict) -> None:
        text = question_text(record)
        key = normalize_question_text(text)
        if not key or key in seen_questions:
            return
        inherited = previous_questions.get(key, {})
        merged = {
            **inherited,
            **record,
            "question": text,
            "status": str(record.get("status") or inherited.get("status") or "OPEN").upper(),
            "priority": str(
                record.get("priority")
                or inherited.get("priority")
                or "RECOMMENDED"
            ).upper(),
            "blocks_workflow": bool(
                record.get(
                    "blocks_workflow",
                    inherited.get("blocks_workflow", False),
                )
            ),
            "reason": str(record.get("reason") or inherited.get("reason") or ""),
        }
        question_records.append(merged)
        seen_questions.add(key)

    resolved_questions = {
        normalize_question_text(statement.question)
        for statement in source_statements
        if statement.resolved and str(statement.question or "").strip()
    }
    for answer in answers:
        if str(answer.get("status") or "").upper() != "ACCEPTED":
            continue
        text = question_text(answer.get("question"))
        if not text:
            continue
        if normalize_question_text(text) not in resolved_questions:
            continue
        inherited = previous_questions.get(normalize_question_text(text), {})
        add_question(
            _question_status_record(
                text,
                "RESOLVED",
                str(inherited.get("priority") or "REQUIRED"),
                bool(inherited.get("blocks_workflow", True)),
                str(inherited.get("reason") or ""),
            )
        )

    pending_state = {"clarification_state": {"decisions": decisions}}
    for text in ClarificationDecisions(pending_state).remainder_questions():
        add_question(_question_status_record(text, "OPEN", "RECOMMENDED", False))

    if blocking_questions is None:
        blocking_questions = (
            state.get("blocking_questions")
            or (state.get("validation") or {}).get("blocking_questions")
            or state.get("clarification_questions")
            or []
        )
    if non_blocking_questions is None:
        non_blocking_questions = (
            state.get("non_blocking_questions")
            or (state.get("validation") or {}).get("non_blocking_questions")
            or (state.get("requirements") or {}).get("open_questions")
            or (state.get("discovery") or {}).get("unknowns")
            or []
        )

    for record in _iter_question_records(blocking_questions, required=True):
        add_question(record)
    for record in _iter_question_records(non_blocking_questions, required=False):
        add_question(record)

    return {
        "version": 1,
        "answers": answers,
        "decisions": decisions,
        "questions": question_records,
    }


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
        remainders = self.remainder_questions()
        if any(
            _same_question_text(text, remainder) or questions_equivalent(text, remainder)
            for remainder in remainders
        ):
            return False
        # A PENDING decision item on the same original question is a separate
        # remainder. It does not reopen the covered original question.
        return True

    def pending_questions(self) -> list[str]:
        """Original clarification questions that still have a pending remainder."""
        questions: list[str] = []
        for statement in self.pending:
            question = statement.question.strip()
            if question and question not in questions:
                questions.append(question)
        return questions

    def remainder_questions(self) -> list[str]:
        """Narrow remaining questions for pending statements, not the original broads.

        Distinct pending refinements from one original answer stay separate.
        A pending unit that only restates the original question is kept when
        that question has no more specific remainder.
        """
        grouped: dict[str, list[ClarifiedStatement]] = {}
        for statement in self.pending:
            key = normalize_question_text(statement.question) or normalize_question_text(
                statement.text
            )
            grouped.setdefault(key, []).append(statement)
        remainders: list[str] = []
        seen: set[str] = set()

        def add(text: str) -> None:
            text = str(text or "").strip()
            key = normalize_question_text(text)
            if not text or not key or key in seen:
                return
            if any(questions_equivalent(text, existing) for existing in remainders):
                return
            remainders.append(text)
            seen.add(key)

        for statements in grouped.values():
            original = statements[0].question.strip()
            specific: list[str] = []
            fallback: list[str] = []
            for statement in statements:
                text = _narrowed_from_pending(original, [statement])
                if not text:
                    continue
                if original and not _same_question_text(text, original):
                    specific.append(text)
                else:
                    fallback.append(text)
            if specific:
                for text in specific:
                    add(text)
            elif fallback:
                add(fallback[0])
            elif original:
                add(_narrowed_from_pending(original, statements) or original)
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


def _same_ledger_question(first: str, second: str) -> bool:
    """True when two questions are the same ledger item, including repaired forms.

    Semantic equivalence is intentionally not used: a narrower remainder must
    not inherit RESOLVED status from its original question.
    """
    if _same_question_text(first, second):
        return True
    repaired_first = _repair_malformed_question(first) or first
    repaired_second = _repair_malformed_question(second) or second
    return _same_question_text(repaired_first, repaired_second)


def clarification_question_status(text: str, state: dict | None) -> str:
    """Ledger status for a question: RESOLVED, OPEN, or empty if unknown."""
    text = str(text or "").strip()
    if not text:
        return ""
    for item in _canonical_clarification_state(state).get("questions") or []:
        if not isinstance(item, dict):
            continue
        other = question_text(item)
        if other and _same_ledger_question(text, other):
            return str(item.get("status") or "").strip().upper()
    return ""


def _remainders_for_hits(text: str, pending_hits: list[ClarifiedStatement]) -> list[str]:
    remainders: list[str] = []
    seen: set[str] = set()
    for statement in pending_hits:
        source = statement.question.strip() or text
        narrowed = _narrowed_from_pending(source, [statement])
        key = normalize_question_text(narrowed)
        if not narrowed or not key or key in seen:
            continue
        if any(questions_equivalent(narrowed, existing) for existing in remainders):
            continue
        remainders.append(narrowed)
        seen.add(key)
    if not remainders and pending_hits:
        source = pending_hits[0].question.strip() or text
        remainders = [_narrowed_from_pending(source, pending_hits)]
    return [item for item in remainders if item]


def reconcile_open_questions(questions: list, state: dict | None) -> list:
    """Close, replace, or keep questions against all clarification answers.

    Resolved questions are dropped. A pending remainder replaces the original
    broad question. Equivalent paraphrases collapse to one canonical item.
    Distinct remaining decisions on the same topic stay separate.
    The canonical ledger is authoritative: a RESOLVED question is not kept
    even when a PENDING decision item still exists for a narrower remainder.
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
        repaired = _repair_malformed_question(text)
        if repaired and repaired != text:
            text = repaired
            item = _with_question_text(item, text)
        ledger_status = clarification_question_status(text, state)
        remainders = [
            narrowed
            for narrowed in _remainders_for_hits(text, pending_hits)
            if narrowed
            and not _MALFORMED_ASK.search(narrowed)
            and clarification_question_status(narrowed, state) != "RESOLVED"
            and not _same_ledger_question(narrowed, text)
        ]
        is_known_remainder = any(
            _same_ledger_question(text, remainder)
            for remainder in decisions.remainder_questions()
        )
        # A remainder question is its own open item. Sibling pending
        # statements from the same original must not replace it.
        if is_known_remainder and ledger_status != "RESOLVED":
            rewritten.append(item)
            continue
        # Canonical RESOLVED status, or covered original wording, drops the
        # question. Distinct PENDING remainders stay as separate open items.
        if ledger_status == "RESOLVED" or _MALFORMED_ASK.search(text):
            for narrowed in remainders:
                rewritten.append(_with_question_text(item, narrowed))
            continue
        if decisions.resolves(text) and not pending_hits:
            continue
        if pending_hits:
            if remainders:
                for narrowed in remainders:
                    rewritten.append(_with_question_text(item, narrowed))
            elif not decisions.resolves(text):
                rewritten.append(item)
            continue
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
    if any(
        len(statement_tokens - content_tokens(text)) <= allowed_missing
        for text in texts
    ):
        return True
    combined = content_tokens(" ".join(str(text or "") for text in texts))
    return len(statement_tokens - combined) <= allowed_missing


_VERIFIED_CLARIFICATION = re.compile(
    r"^verified by demonstration or test that:\s*",
    re.I,
)


def is_verified_clarification_item(text: str) -> bool:
    """True for raw sourced clarification sentences used as acceptance bullets."""
    return bool(_VERIFIED_CLARIFICATION.match(str(text or "").strip()))


def strip_verified_clarification_items(items) -> list:
    """Drop prefixed clarification restatements; keep testable acceptance text."""
    cleaned = []
    for item in items or []:
        text = str(item or "").strip()
        if text and not is_verified_clarification_item(text):
            cleaned.append(text)
    return cleaned


_MODAL_STEMS = frozenset(
    _stem(word) for word in ("allow", "able", "enable", "permit")
)
_BEHAVIOR_STEMS = frozenset(
    _stem(word)
    for word in (
        "complete",
        "record",
        "submit",
        "create",
        "attach",
        "prevent",
        "resolve",
        "persist",
        "synchronize",
        "synchronization",
        "queue",
        "queued",
        "network",
        "offline",
        "duplicate",
        "conflict",
        "review",
        "track",
        "integrate",
        "integration",
        "access",
        "search",
        "capture",
        "continue",
        "identify",
        "coordinate",
        "reconnect",
        "overwrite",
        "detect",
        "retry",
        "renew",
        "photo",
        "photograph",
    )
)


_ACTOR_STEMS = frozenset(
    _stem(word)
    for word in (
        "technician",
        "field",
        "member",
        "librarian",
        "receptionist",
        "operator",
        "officer",
        "clerk",
        "staff",
        "user",
        "coordinator",
        "picker",
    )
)


def _normalize_comparison_token(token: str) -> str:
    """Align gerund and base stems for comparison only.

    ``_stem`` strips ``ing`` before a trailing ``s``, so ``accessing`` stays
    ``access`` while ``access`` becomes ``acces``. It also drops the silent
    ``e`` in ``creating`` (``creat``) but not in ``create``.
    """
    if len(token) >= 5 and token.endswith("ss"):
        token = token[:-1]
    extended = token + "e"
    if len(token) >= 4 and extended in _BEHAVIOR_STEMS:
        token = extended
    return token


def _comparison_tokens(tokens: frozenset[str]) -> frozenset[str]:
    """Modal-free tokens used only when testing equivalence or subsets."""
    return frozenset(
        _normalize_comparison_token(token)
        for token in tokens
        if token not in _MODAL_STEMS
    )


def _scope_parts(
    tokens: frozenset[str],
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    behavior = tokens & _BEHAVIOR_STEMS
    actors = tokens & _ACTOR_STEMS
    objects = tokens - _BEHAVIOR_STEMS - _ACTOR_STEMS
    return behavior, actors, objects


def _same_behavior_and_objects(left: frozenset[str], right: frozenset[str]) -> bool:
    """True when the action and objects match, not merely the verb.

    One side may add a qualifier such as a source system. Different actors
    stay distinct. A shared behavior stem with different objects does not match.
    """
    left_behavior, left_actors, left_objects = _scope_parts(left)
    right_behavior, right_actors, right_objects = _scope_parts(right)
    if not left_behavior or left_behavior != right_behavior:
        return False
    if not left_objects or not right_objects:
        return False
    if left_actors and right_actors and left_actors != right_actors:
        return False
    if min(len(left_objects), len(right_objects)) < 3:
        return False
    return left_objects <= right_objects or right_objects <= left_objects


def _more_informative(
    new_text: str,
    new_tokens: frozenset[str],
    old_text: str,
    old_tokens: frozenset[str],
) -> bool:
    """Prefer the wording that keeps extra objects, such as a named source."""
    _new_behavior, _new_actors, new_objects = _scope_parts(new_tokens)
    _old_behavior, _old_actors, old_objects = _scope_parts(old_tokens)
    if len(new_objects) != len(old_objects):
        return len(new_objects) > len(old_objects)
    if len(new_tokens) != len(old_tokens):
        return len(new_tokens) > len(old_tokens)
    return len(new_text) > len(old_text)


def _tokens_covered_by(candidate: frozenset[str], reference: frozenset[str]) -> bool:
    if not candidate:
        return True
    return len(candidate - reference) <= len(candidate) // 8


def _equivalent_paraphrase(left: frozenset[str], right: frozenset[str]) -> bool:
    if not left or not right:
        return False
    return _tokens_covered_by(left, right) and _tokens_covered_by(right, left)


def _is_short_paraphrase(short_tokens: frozenset[str], long_tokens: frozenset[str]) -> bool:
    """True when short is the same behavior as long, not a distinct constituent."""
    if not short_tokens or short_tokens == long_tokens:
        return False
    if not short_tokens <= long_tokens:
        return False
    extra = long_tokens - short_tokens
    return bool(extra) and not (extra & _BEHAVIOR_STEMS)


def collapse_equivalent_scope_items(items) -> list:
    """Keep one wording per behavior; never drop a distinct action or qualifier.

    Later must/shall and gerund paraphrases of one kept item collapse.
    Modal scaffolding such as allow/able is ignored only while comparing
    items. A short fragment collapses into one longer statement of the same
    behavior only when the extra tokens are not additional actions or
    meaningful qualifiers. The more informative wording is kept, including
    a named source such as an asset registry. A compound bullet does not
    delete its constituent behaviors, and a later pass does not delete a
    distinct requirement merely because its tokens appear across several
    other bullets.
    """
    kept: list[str] = []
    kept_tokens: list[frozenset[str]] = []
    for item in items or []:
        text = str(item or "").strip()
        if not text:
            continue
        tokens = _comparison_tokens(content_tokens(_requirement_body(text)))
        replaced = False
        for index, existing in enumerate(kept_tokens):
            longer_than_existing = _is_short_paraphrase(existing, tokens)
            same_scope = (
                _equivalent_paraphrase(tokens, existing)
                or _same_behavior_and_objects(tokens, existing)
                or longer_than_existing
            )
            if not same_scope:
                continue
            if longer_than_existing and sum(
                1 for other in kept_tokens if other and other < tokens
            ) >= 2:
                replaced = True
                break
            if _more_informative(text, tokens, kept[index], existing):
                kept[index] = text
                kept_tokens[index] = tokens
            replaced = True
            break
        if replaced:
            continue
        kept.append(text)
        kept_tokens.append(tokens)

    compounds: set[int] = set()
    for index, tokens in enumerate(kept_tokens):
        covered = [
            other
            for other_index, other in enumerate(kept_tokens)
            if other_index != index and other and other < tokens
        ]
        if len(covered) >= 2:
            compounds.add(index)

    survivors: list[int] = []
    for index, tokens in enumerate(kept_tokens):
        if index in compounds:
            continue
        if any(
            other != index
            and other not in compounds
            and _is_short_paraphrase(tokens, kept_tokens[other])
            for other in range(len(kept_tokens))
        ):
            continue
        survivors.append(index)
    return [kept[index] for index in survivors]


_CONDITION_FLAGS = ("no network", "offline", "without connectivity")


def _condition_key(text: str) -> tuple[str, ...]:
    lower = str(text or "").lower()
    return tuple(flag for flag in _CONDITION_FLAGS if flag in lower)


def _statement_rank(text: str) -> tuple[int, int, int]:
    finite = 1 if re.search(r"\b(?:shall|must|can|cannot|able)\b", text, re.I) else 0
    return (finite, len(str(text).split()), len(str(text)))


def _object_tokens(obj: str) -> set[str]:
    return {part for part in str(obj or "").split() if part}


def _objects_match(left: str, right: str) -> bool:
    """Same object, allowing only generic extras such as 'service' or 'system'."""
    if left == right:
        return True
    left_tokens = _object_tokens(left)
    right_tokens = _object_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    if left_tokens <= right_tokens:
        extra = right_tokens - left_tokens
    elif right_tokens <= left_tokens:
        extra = left_tokens - right_tokens
    else:
        return False
    return bool(extra) and extra <= _GENERIC_OBJECT_TOKENS


def _signature_is_incomplete(signature: frozenset[tuple[str, str]]) -> bool:
    """An empty object means the distinctive outcome was not recovered.

    Authenticate is the exception: login and authentication are the same
    behavior and intentionally carry no object.
    """
    return any(not obj for family, obj in signature if family != "authenticate")


def _behaviors_equivalent(
    left: frozenset[tuple[str, str]],
    right: frozenset[tuple[str, str]],
) -> bool:
    """Same behavior, including two integrations that name the same system.

    Matching families with an empty object are not evidence of equivalence.
    """
    if _signature_is_incomplete(left) or _signature_is_incomplete(right):
        return False
    if left == right:
        return True
    if len(left) != 1 or len(right) != 1:
        return False
    (left_family, left_obj) = next(iter(left))
    (right_family, right_obj) = next(iter(right))
    if left_family != right_family:
        return False
    if left_family == "integrate":
        left_tokens = _object_tokens(left_obj)
        right_tokens = _object_tokens(right_obj)
        return bool(left_tokens and right_tokens and left_tokens & right_tokens)
    return _objects_match(left_obj, right_obj)


def _integrate_single_covered(
    signature: frozenset[tuple[str, str]],
    other: frozenset[tuple[str, str]],
) -> bool:
    """A one-behavior integration summary already named by another item."""
    if len(signature) != 1 or not other:
        return False
    family, obj = next(iter(signature))
    if family != "integrate":
        return False
    tokens = _object_tokens(obj)
    if not tokens:
        return False
    return any(
        other_family == "integrate" and tokens & _object_tokens(other_obj)
        for other_family, other_obj in other
    )


def _behavior_represented(
    behavior: tuple[str, str],
    other: frozenset[tuple[str, str]],
) -> bool:
    """True when one behavior is already stated, including under a broader object."""
    family, obj = behavior
    obj_tokens = _object_tokens(obj)
    for other_family, other_obj in other:
        if other_family != family:
            continue
        other_tokens = _object_tokens(other_obj)
        if obj == other_obj:
            if obj or family == "authenticate":
                return True
            continue
        if family == "integrate" and obj_tokens and other_tokens and (obj_tokens & other_tokens):
            return True
        if obj_tokens and other_tokens and obj_tokens <= other_tokens:
            return True
        if family == "authenticate" and not obj_tokens and not other_tokens:
            return True
    return False


def _absorb_integrate_summary(index, other, texts, signatures) -> bool:
    """Drop a generic integration line when a clearer item already names that system."""
    if not _integrate_single_covered(signatures[index], signatures[other]):
        return False
    summary_rank = _statement_rank(texts[index])
    other_rank = _statement_rank(texts[other])
    if summary_rank[0] == 1 and other_rank[0] == 0:
        return False
    if len(signatures[other]) == 1 and other_rank >= summary_rank:
        return True
    return len(signatures[other]) > 1 and summary_rank[0] == 0


def _nominal_integration_summary(index, other, behavior, texts, signatures) -> bool:
    """A vague integration label does not replace a finite integration requirement."""
    family, _obj = behavior
    return (
        family == "integrate"
        and len(signatures[other]) == 1
        and _statement_rank(texts[other])[0] == 0
        and _statement_rank(texts[index])[0] == 1
    )


_FINITE_CLAUSE = re.compile(r"\b(?:shall|must|should|can|will|given|when)\b", re.I)
_TRUNCATED_MODAL = re.compile(r"^the system shall [a-z]+(?: [a-z]+){0,4}\.$", re.I)
_FRAGMENT_HEADS = frozenset({
    "current", "status", "state", "new", "existing", "historical", "previous", "other",
})


def _complete_behavior_clause(text: str, behavior: tuple[str, str]) -> str | None:
    """A finite clause already written in ``text`` that states only this behavior.

    Signature leftovers are not turned into a new sentence. Splitting is safe
    only when the source already contains a complete clause for the outcome.
    """
    family, _obj = behavior
    whole = str(text or "").strip().rstrip(".").lower()
    pieces = re.split(r"\s*;\s+|(?<=[.!?])\s+|\s+\band\b\s+", str(text or ""), flags=re.I)
    for piece in pieces:
        clause = piece.strip(" .;")
        if len(clause.split()) < 6 or clause.lower() == whole:
            continue
        if not _FINITE_CLAUSE.search(clause):
            continue
        signature = behavior_signatures(clause)
        if len(signature) != 1:
            continue
        only = next(iter(signature))
        if only[0] != family:
            continue
        if not (
            _behavior_represented(behavior, signature)
            or _behavior_represented(only, frozenset({behavior}))
        ):
            continue
        if clause[0].islower():
            clause = clause[0].upper() + clause[1:]
        return clause if clause.endswith(".") else f"{clause}."
    return None


def _truncated_criterion(text: str) -> bool:
    """A modal line built from a verb plus leftover words, not a full outcome."""
    stripped = " ".join(str(text or "").split())
    if not _TRUNCATED_MODAL.match(stripped):
        return False
    complement = [word.lower() for word in stripped[:-1].split()[4:]]
    if not complement:
        return True
    if any(word in {"a", "an", "the", "their", "its", "this", "these", "those", "to", "with", "for", "from", "via", "of", "into"} for word in complement):
        return False
    if complement[-1] in _FRAGMENT_HEADS:
        return True
    return not complement[-1].endswith("s")


def _standalone_label(text: str, others: list[str]) -> bool:
    """A short name that adds no behavior already stated by another item."""
    raw = str(text or "").strip()
    if not raw or re.search(r"\b(?:shall|must|should|given|when|then)\b", raw, re.I):
        return False
    if behavior_signatures(raw):
        return False
    words = re.findall(r"[A-Za-z0-9]+", raw)
    if not words or len(words) > 3:
        return False
    tokens = [word.lower() for word in words if len(word) > 1]
    if not tokens:
        return False
    for other in others:
        if other == raw or not behavior_signatures(other):
            continue
        other_tokens = {word.lower() for word in re.findall(r"[A-Za-z0-9]+", other)}
        if all(token in other_tokens for token in tokens):
            return True
    return False


def normalize_paraphrase_duplicates(items) -> tuple[list[str], list[dict]]:
    """Drop same-behavior paraphrases. Keep distinct behaviors.

    A compound is removed only when every behavior it states is already a
    separate item. When a compound also states a behavior the other items
    do not, that remaining behavior is kept as its own line. A short name
    with no behavior of its own is dropped when a fuller item already
    names it. Unrecognized statements are left unchanged.
    """
    texts = [
        repair_generated_grammar(str(item or "").strip())
        for item in items or []
        if str(item or "").strip()
    ]
    signatures = [behavior_signatures(text) for text in texts]
    conditions = [_condition_key(text) for text in texts]
    kept: list[int] = []
    findings: list[dict] = []
    seen_exact: set[str] = set()

    for index, text in enumerate(texts):
        exact = text.lower()
        if exact in seen_exact:
            findings.append(
                {
                    "code": "EXACT_DUPLICATE",
                    "removed": text,
                    "kept": text,
                    "reason": "The same statement was already present.",
                }
            )
            continue
        seen_exact.add(exact)
        signature = signatures[index]
        if not signature:
            kept.append(index)
            continue
        match = next(
            (
                other
                for other in kept
                if signatures[other]
                and (
                    _behaviors_equivalent(signatures[other], signature)
                    or (
                        len(signature) == 1
                        and len(signatures[other]) == 1
                        and _integrate_single_covered(signature, signatures[other])
                    )
                )
                and conditions[other] == conditions[index]
            ),
            None,
        )
        if match is None:
            kept.append(index)
            continue
        if _statement_rank(text)[0] > _statement_rank(texts[match])[0]:
            removed = texts[match]
            texts[match] = text
            signatures[match] = signature
            conditions[match] = conditions[index]
            kept_text = text
        else:
            removed = text
            kept_text = texts[match]
        findings.append(
            {
                "code": "PARAPHRASE_COLLAPSED",
                "removed": removed,
                "kept": kept_text,
                "reason": "The statement repeats a behavior already in this list.",
            }
        )

    still_kept: list[int] = []
    for index in kept:
        signature = signatures[index]
        if len(signature) == 1 and any(
            other != index and _absorb_integrate_summary(index, other, texts, signatures)
            for other in kept
        ):
            keeper = next(
                texts[other]
                for other in kept
                if other != index and _absorb_integrate_summary(index, other, texts, signatures)
            )
            findings.append(
                {
                    "code": "PARAPHRASE_COLLAPSED",
                    "removed": texts[index],
                    "kept": keeper,
                    "reason": "The statement repeats an integration already in this list.",
                }
            )
            continue
        still_kept.append(index)
    kept = still_kept

    def _coverage(index: int, pool: list[int]) -> tuple[list[str], list[tuple[str, str]]]:
        represented: list[str] = []
        missing: list[tuple[str, str]] = []
        for behavior in signatures[index]:
            covers = [
                texts[other]
                for other in pool
                if other != index
                and signatures[other]
                and _behavior_represented(behavior, signatures[other])
                and not _nominal_integration_summary(index, other, behavior, texts, signatures)
            ]
            if covers:
                represented.append(covers[0])
            else:
                missing.append(behavior)
        return represented, missing

    redundant = {
        index
        for index in kept
        if len(signatures[index]) >= 2 and not _coverage(index, kept)[1]
    }
    final: list[str] = []
    for index in kept:
        signature = signatures[index]
        text = texts[index]
        if index in redundant:
            represented, _missing = _coverage(index, kept)
            findings.append(
                {
                    "code": "COMPOUND_REDUNDANT",
                    "removed": text,
                    "kept": represented,
                    "reason": "Every behavior in this item is already stated separately.",
                }
            )
            continue
        if len(signature) >= 2:
            represented, missing = _coverage(
                index, [other for other in kept if other not in redundant]
            )
            if represented and missing:
                missing_families = {family for family, _obj in missing}
                if "integrate" in missing_families and _statement_rank(text)[0] == 1:
                    final.append(text)
                    continue
                clauses = []
                meaningful = [
                    behavior
                    for behavior in missing
                    if any(
                        part not in {
                            "customer", "customers", "user", "users", "member", "members",
                            "staff", "client", "clients",
                        }
                        for part in behavior[1].split()
                    )
                ]
                for behavior in meaningful:
                    clause = _complete_behavior_clause(text, behavior)
                    if clause is None:
                        clauses = []
                        break
                    if clause.lower() not in {item.lower() for item in (*final, *clauses)}:
                        clauses.append(clause)
                if not clauses:
                    findings.append(
                        {
                            "code": "AMBIGUOUS_OVERLAP",
                            "item": text,
                            "overlaps": represented,
                            "reason": (
                                "This item overlaps an existing behavior and also states "
                                "a distinct one. It was left unchanged."
                            ),
                        }
                    )
                    final.append(text)
                    continue
                findings.append(
                    {
                        "code": "COMPOUND_SPLIT",
                        "removed": text,
                        "kept": clauses,
                        "reason": (
                            "Overlapping wording was removed. "
                            "The remaining outcome was already stated as a complete clause."
                        ),
                    }
                )
                final.extend(clauses)
                continue
        final.append(text)
    labeled = []
    for text in final:
        if _standalone_label(text, final):
            findings.append(
                {
                    "code": "LABEL_ABSORBED",
                    "removed": text,
                    "kept": "",
                    "reason": "The item names a technology already stated by another requirement.",
                }
            )
            continue
        labeled.append(text)
    return labeled, findings


_FINAL_SCOPE_FIELDS = (
    ("solution", "key_capabilities"),
    ("solution", "integration_approach"),
    ("proposal", "scope"),
    ("sow", "in_scope"),
    ("sow", "acceptance"),
)


def _string_leaves(value, location: str):
    if isinstance(value, str):
        if value.strip():
            yield location, value
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _string_leaves(item, f"{location}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _string_leaves(item, f"{location}.{key}")


def repair_final_scope_lists(payload: dict | None) -> dict:
    """Remove equivalent items from the assembled scope lists."""
    payload = payload or {}
    for artifact_key, field in _FINAL_SCOPE_FIELDS:
        artifact = payload.get(artifact_key)
        if not isinstance(artifact, dict) or not isinstance(artifact.get(field), list):
            continue
        normalized, _findings = normalize_paraphrase_duplicates(artifact.get(field) or [])
        artifact[field] = collapse_equivalent_scope_items(normalized)
    return payload


def _text_defects(location: str, text: str) -> list[dict]:
    from app.assessment import duplicated_sentence_fragments, joined_sentence_boundaries

    defects: list[dict] = []
    if duplicated_sentence_fragments(text):
        defects.append(
            {
                "kind": "duplicated_sentence_fragment",
                "field": location,
                "message": f"Malformed duplicated sentence fragment in {location}.",
            }
        )
    if joined_sentence_boundaries(text):
        defects.append(
            {
                "kind": "joined_sentence",
                "field": location,
                "message": f"Missing sentence separator in {location}.",
            }
        )
    return defects


def final_artifact_defects(payload: dict | None) -> list[dict]:
    """Residual equivalent scope items and malformed sentence joins."""
    payload = payload or {}
    defects: list[dict] = []
    for artifact_key, field in _FINAL_SCOPE_FIELDS:
        artifact = payload.get(artifact_key)
        if not isinstance(artifact, dict):
            continue
        current = [str(entry).strip() for entry in artifact.get(field) or [] if str(entry).strip()]
        _kept, findings = normalize_paraphrase_duplicates(current)
        seen_subjects: set[str] = set()
        for item in findings:
            if not isinstance(item, dict):
                continue
            subject = str(item.get("item") or item.get("removed") or "").strip()
            if not subject or subject not in current or subject in seen_subjects:
                continue
            if item.get("code") == "EXACT_DUPLICATE" and current.count(subject) < 2:
                continue
            seen_subjects.add(subject)
            defects.append(
                {
                    "kind": "equivalent_scope_item",
                    "field": f"{artifact_key}.{field}",
                    "code": item.get("code"),
                    "removed": subject,
                    "message": (
                        f"Equivalent scope items remain in {artifact_key}.{field}: {subject}"
                    ),
                }
            )
        for entry in current:
            if not _truncated_criterion(entry):
                continue
            defects.append(
                {
                    "kind": "truncated_criterion",
                    "field": f"{artifact_key}.{field}",
                    "message": f"Truncated criterion in {artifact_key}.{field}: {entry}",
                }
            )
    for artifact_key in (
        "proposal",
        "sow",
        "solution",
        "delivery_plan",
        "estimate",
        "delivery_review",
        "assessment",
    ):
        artifact = payload.get(artifact_key)
        if not isinstance(artifact, dict):
            continue
        for location, text in _string_leaves(artifact, artifact_key):
            defects.extend(_text_defects(location, text))
    for key in ("assessment_text", "print_assessment_text"):
        text = payload.get(key)
        if isinstance(text, str):
            defects.extend(_text_defects(key, text))
    artifact_texts = payload.get("artifact_texts")
    if isinstance(artifact_texts, dict):
        for location, text in _string_leaves(artifact_texts, "artifact_texts"):
            defects.extend(_text_defects(location, text))
    return defects


def _refresh_assembled_texts(payload: dict) -> None:
    """Rebuild copy text from the fields that will actually be returned."""
    if "artifact_texts" not in payload:
        return
    from app.artifact_export import build_artifact_texts

    payload["artifact_texts"] = build_artifact_texts(payload)


def apply_final_artifact_quality(payload: dict | None) -> list[dict]:
    """Repair equivalent scope items, then grade the assembled artifact.

    Copy text is rebuilt after list repair. The clean flag is taken from that
    final payload, so an earlier cleanup cannot hide a defect that is still
    present.
    """
    payload = payload or {}
    repair_final_scope_lists(payload)
    _refresh_assembled_texts(payload)
    defects = final_artifact_defects(payload)
    if not defects:
        payload["artifact_quality"] = "CLEAN"
        return []
    review = payload.get("delivery_review")
    if not isinstance(review, dict):
        review = {}
        payload["delivery_review"] = review
    warnings = [str(item) for item in review.get("warnings") or [] if str(item).strip()]
    for defect in defects:
        message = defect["message"]
        if message not in warnings:
            warnings.append(message)
    review["warnings"] = warnings
    review["artifact_quality"] = "DEFECTS"
    payload["artifact_quality"] = "DEFECTS"
    return defects


_OFFLINE_DESIGN = re.compile(
    r"\b(?:offline|synchron\w*|sync)\b.+\b(?:module|architecture|design|mechanism)\b|"
    r"\b(?:module|architecture|design|mechanism)\b.+\b(?:offline|synchron\w*|sync)\b|"
    r"\b(?:last[- ]write[- ]wins|conflict[- ]resolution rule)\b",
    re.I,
)
_PROVISIONAL_DELIVERABLE_PREFIX = (
    "Provisional planning item, pending unresolved offline behavior "
    "and synchronization rules: "
)
_PROVISIONAL_SYNC_ASSUMPTION = (
    "Exact offline behavior and synchronization rules are unresolved. "
    "Any synchronization module or conflict-resolution approach is a "
    "provisional planning item, not a customer-approved design."
)


def _pending_offline_sync(state: dict | None) -> bool:
    decisions = ClarificationDecisions(state)
    texts = [statement.text for statement in decisions.pending]
    texts.extend(decisions.remainder_questions())
    texts.extend(unanswered_request_items(state))
    return any(
        re.search(r"\b(?:offline|synchron\w*|sync)\b", str(text or ""), re.I)
        for text in texts
    )


def qualify_unresolved_sow_deliverables(sow: dict | None, state: dict | None) -> dict:
    """Mark an unresolved sync design as provisional without removing the topic.

    Does not move the deliverable out of scope and does not alter solution
    capabilities. A customer-approved design is left unchanged when no
    offline or synchronization decision is still pending.
    """
    if not isinstance(sow, dict) or not _pending_offline_sync(state):
        return sow or {}
    deliverables = []
    qualified = False
    for item in sow.get("deliverables") or []:
        text = str(item or "").strip()
        if not text:
            continue
        if text.startswith(_PROVISIONAL_DELIVERABLE_PREFIX):
            deliverables.append(text)
            qualified = True
            continue
        if _OFFLINE_DESIGN.search(text):
            deliverables.append(_PROVISIONAL_DELIVERABLE_PREFIX + text)
            qualified = True
            continue
        deliverables.append(text)
    if not qualified:
        return sow
    updated = dict(sow)
    updated["deliverables"] = deliverables
    assumptions = [
        str(item).strip()
        for item in updated.get("assumptions") or []
        if str(item).strip()
    ]
    if _PROVISIONAL_SYNC_ASSUMPTION not in assumptions:
        assumptions.append(_PROVISIONAL_SYNC_ASSUMPTION)
    updated["assumptions"] = assumptions
    return updated


def drop_unresolved_out_of_scope_items(items, state: dict | None) -> list:
    """Keep explicit exclusions; drop bullets that only restate open decisions."""
    kept: list[str] = []
    open_token_sets = _unresolved_scope_token_sets(state)
    for item in items or []:
        text = str(item or "").strip()
        if not text:
            continue
        if answer_retracts_scope(text, state):
            kept.append(text)
            continue
        if _restates_unresolved_scope(text, open_token_sets):
            continue
        kept.append(text)
    return kept


def _unresolved_scope_token_sets(state: dict | None) -> list[frozenset[str]]:
    decisions = ClarificationDecisions(state)
    units = [statement.text for statement in decisions.pending]
    units.extend(decisions.remainder_questions())
    units.extend(unanswered_request_items(state))
    return [content_tokens(text) for text in units if str(text or "").strip()]


def _restates_unresolved_scope(text: str, open_token_sets: list[frozenset[str]]) -> bool:
    if is_pending_text(text):
        return True
    tokens = content_tokens(text)
    if not tokens:
        return False
    for other in open_token_sets:
        shared = tokens & other
        if len(shared) >= 2 and (shared & _BEHAVIOR_STEMS):
            return True
    return False


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


def _is_incomplete_requirement_fragment(text: str) -> bool:
    """True for colon-truncated or empty clarification leftovers, not named requirements."""
    body = _requirement_body(text).rstrip()
    return (not body) or body.endswith(":")


def _unsupported_resolution_policy(text: str, decisions: ClarificationDecisions) -> bool:
    """True when a generated last-write/overwrite policy was not customer-confirmed."""
    if not _RESOLUTION_POLICY.search(str(text or "")):
        return False
    return not any(_RESOLUTION_POLICY.search(statement.text) for statement in decisions.resolved)


def _is_product_statement(statement: ClarifiedStatement) -> bool:
    blob = f"{statement.question} {statement.text}"
    if _DELIVERY_ADMIN.search(blob):
        return False
    if is_pending_text(statement.text):
        return False
    if _is_incomplete_requirement_fragment(statement.text):
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
        and not is_pending_text(_requirement_body(item))
        and not _is_incomplete_requirement_fragment(item)
    ]


def apply_decisions_to_requirements(requirements: dict | None, state: dict | None) -> dict:
    """Write resolved product decisions into requirements and keep pending ones open.

    Resolved product-behavior statements become sourced requirements unless
    an equivalent entry already exists. They are not copied into acceptance
    as "Verified by demonstration..." sentences. Planning facts, capacity
    unknowns, and existing-state evidence stay in ``clarified_decisions``
    with provenance. Pending statements keep their question open.
    """
    requirements = dict(requirements or {})
    decisions = ClarificationDecisions(state)
    if not decisions.statements:
        if "acceptance_criteria" in requirements:
            requirements["acceptance_criteria"] = collapse_equivalent_scope_items(
                strip_verified_clarification_items(
                    requirements.get("acceptance_criteria")
                )
            )
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

    open_questions = reconcile_open_questions(
        [str(i) for i in requirements.get("open_questions") or []]
        + decisions.remainder_questions()
        + unanswered_request_items(state),
        state,
    )

    requirements["functional_requirements"] = collapse_equivalent_scope_items(functional)
    requirements["non_functional_requirements"] = non_functional
    requirements["acceptance_criteria"] = collapse_equivalent_scope_items(
        strip_verified_clarification_items(acceptance)
    )
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


_LEADING_CONJUNCTION = re.compile(r"^(?:but|and|or|,)\s+(?:the\s+)?", re.I)
_MALFORMED_ASK = re.compile(
    r"\bthe (?:but|and|or) the\b|"
    r"^(?:what (?:are|is) the) (?:but|and|or)\b",
    re.I,
)


def _as_open_question(subject: str) -> str:
    text = re.sub(r"\b(?:also|still)\s*$", "", str(subject or "").strip().rstrip(". "), flags=re.I).strip()
    text = _LEADING_CONJUNCTION.sub("", text).strip()
    if not text:
        return ""
    if text.endswith("?"):
        candidate = text
    elif re.match(r"^(which|what|who|how|when|where|whether)\b", text, re.I):
        candidate = text + "?"
    else:
        text = re.sub(r"^(?:the|a|an)\s+", "", text, flags=re.I)
        candidate = f"What are the {text}?"
    candidate = _repair_malformed_question(candidate)
    if not candidate or _MALFORMED_ASK.search(candidate):
        return ""
    return candidate


def _repair_malformed_question(text: str) -> str:
    """Drop contrast-clause leftovers such as 'What are the but the …?'."""
    repaired = str(text or "").strip()
    if not repaired:
        return ""
    repaired = re.sub(
        r"\b((?:what|which)\s+(?:are|is)\s+the)\s+(?:but|and|or)\s+(?:the\s+)?",
        r"\1 ",
        repaired,
        flags=re.I,
    )
    repaired = re.sub(r"\bthe\s+(?:but|and|or)\s+the\b", "the", repaired, flags=re.I)
    return re.sub(r"\s+", " ", repaired).strip()


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
        contrast = re.split(r"\b(?:but|however)\b", head, maxsplit=1, flags=re.I)
        if len(contrast) == 2 and contrast[1].strip():
            head = contrast[1].strip()
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
