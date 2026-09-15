"""Clarification resume: reuse upstream artifacts when answers do not change scope.

A clarification turn can either:
- merge customer facts into the existing discovery/requirements and continue, or
- regenerate discovery and requirements when the answer materially changes
  capability, users, systems, or scope.

Timeline and similar metadata answers do not justify repeating Discovery/Requirements.
"""

from __future__ import annotations

from app.agents import (
    _clarification_records,
    _extract_explicit_timeline_facts,
    _filter_answered_discovery,
    _filter_answered_requirement_questions,
)
from app.state import DeliveryState


_TIMELINE_MARKERS = (
    "timeline",
    "deadline",
    "due date",
    "by when",
    "target delivery",
    "duration",
    "how long",
)

_METADATA_MARKERS = (
    "user volume",
    "expected volume",
    "roles",
    "permissions",
    "security",
    "compliance",
    "privacy",
    "budget",
)

_SCOPE_MARKERS = (
    "capabilit",
    "who will use",
    "which users",
    "main features",
    "scope",
    "integrate",
    "integration",
    "existing system",
    "source of truth",
    "what should the",
    "what are the main",
)

_SCOPE_CHANGE_IN_ANSWER = (
    "instead",
    "no longer",
    "not only",
    "in addition",
    "also need",
    "also requires",
    "replace",
    "different product",
    "out of scope",
    "new integration",
    "another system",
)


def _text(value) -> str:
    return str(value or "").strip().lower()


def _is_timeline_text(text: str) -> bool:
    return any(marker in text for marker in _TIMELINE_MARKERS)


def _is_metadata_text(text: str) -> bool:
    return any(marker in text for marker in _METADATA_MARKERS)


def _is_scope_text(text: str) -> bool:
    return any(marker in text for marker in _SCOPE_MARKERS)


def answers_require_upstream_regen(state: DeliveryState) -> bool:
    """True when Discovery/Requirements must be regenerated from the new answers."""
    if not state.get("discovery") or not state.get("requirements"):
        return True

    records = state.get("new_clarification_records")
    if records is None:
        records = _clarification_records(state)
    if not records:
        return False

    for record in records:
        question = _text(record.get("question"))
        answer = _text(record.get("answer"))
        combined = f"{question} {answer}"
        if _is_scope_text(combined):
            return True
        if any(marker in answer for marker in _SCOPE_CHANGE_IN_ANSWER):
            return True

    return False


def apply_clarification_facts(state: DeliveryState) -> dict:
    """Merge clarification answers into existing upstream artifacts without an LLM.

    Customer answers remain available to every downstream agent via
    clarification_context. This node also writes timeline/metadata facts into
    discovery.constraints so deadline parsers keep working when Discovery is skipped.
    """
    discovery = dict(state.get("discovery") or {})
    requirements = dict(state.get("requirements") or {})
    if not discovery:
        return {}

    constraints = list(discovery.get("constraints") or [])
    constraint_text = " ".join(str(item).lower() for item in constraints)

    for record in _clarification_records(state):
        question = str(record.get("question") or "").strip()
        answer = str(record.get("answer") or "").strip()
        if not answer:
            continue

        combined = f"{question} {answer}"
        timeline_facts = _extract_explicit_timeline_facts(answer)
        if _is_timeline_text(combined.lower()) or timeline_facts:
            fact = (
                timeline_facts[0]
                if timeline_facts
                else f"Target delivery timeline: {answer}"
            )
            if fact.lower() not in constraint_text:
                constraints.append(fact)
                constraint_text += " " + fact.lower()
            continue

        if _is_metadata_text(combined.lower()):
            fact = f"Customer clarification — {question}: {answer}".strip(" —:")
            if fact.lower() not in constraint_text:
                constraints.append(fact)
                constraint_text += " " + fact.lower()

    discovery["constraints"] = constraints
    discovery = _filter_answered_discovery(discovery, state)
    requirements = _filter_answered_requirement_questions(requirements, state)

    return {
        "discovery": discovery,
        "requirements": requirements,
    }


def route_after_start(state: DeliveryState) -> str:
    """Choose whether this run starts at Discovery or resumes at Validation."""
    resume = bool(state.get("resume_after_clarification"))
    has_upstream = bool(state.get("discovery")) and bool(state.get("requirements"))
    if resume and has_upstream and not state.get("regenerate_upstream"):
        return "apply_clarification"
    return "discovery"
