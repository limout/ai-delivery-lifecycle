"""Clarification answers are authoritative over older unresolved request wording.

Synthetic scenarios only: each has an original request that states a decision
is open, a clarification that resolves it, and clarifications that are still
pending approval. The checks are domain independent.
"""

from dataclasses import dataclass, field

import pytest

from app.agents import (
    DISCOVERY_SCHEMA,
    REQUIREMENTS_SCHEMA,
    VALIDATION_SCHEMA,
    _ground_downstream_artifact,
    discovery_agent,
    requirements_agent,
    validation_agent,
)
from app.api import workflow_response
from app.decisions import (
    ClarificationDecisions,
    apply_decisions_to_requirements,
    dedupe_equivalent_questions,
)
from app.resume import apply_clarification_facts


@dataclass(frozen=True)
class Scenario:
    request: str
    resolved: tuple  # (question, answer) pairs that settle an open statement
    pending: tuple  # (question, answer) pairs awaiting approval
    stale_unknowns: tuple  # reworded unresolved items the resolved answers settle
    pending_variants: tuple  # groups of equivalent still-open questions
    resolved_detail: str  # sentence that must become a sourced requirement
    resolved_fragments: tuple = field(default=())  # words that must not stay open


WAREHOUSE = Scenario(
    request=(
        "We want a tablet app for warehouse pickers to scan items and confirm "
        "picks. Which tablet platforms we will target is undecided. The rules "
        "for working without network coverage are undecided."
    ),
    resolved=(
        (
            "Which tablet platforms should the first release support?",
            "Both Windows and Linux tablets must be supported.",
        ),
        (
            "How should the app behave without network coverage?",
            "Pickers can scan and confirm picks with no connection. Confirmed "
            "picks are queued on the device and synchronized automatically when "
            "the connection returns. If the same pick was changed elsewhere, "
            "the most recent confirmation wins.",
        ),
    ),
    pending=(
        (
            "Which hosting provider and region should be used?",
            "We propose a regional provider in the EU, but the hosting "
            "provider and region have not been approved yet.",
        ),
        (
            "What retention period applies to pick photos?",
            "We suggest three years; the retention period is pending approval "
            "by our legal team.",
        ),
        (
            "Is the supervisor dashboard part of the first release?",
            "Pending decision from the operations director.",
        ),
    ),
    stale_unknowns=(
        "Which tablet platforms will be targeted?",
        "The tablet platform decision is still open.",
        "What should the app do when there is no network coverage?",
    ),
    pending_variants=(
        (
            "Has the customer approved the hosting provider and region?",
            "Which hosting provider and region should be used?",
            "Hosting provider and region approval is outstanding",
        ),
        (
            "What retention period applies to pick photos?",
            "Is the proposed pick photo retention period approved?",
        ),
        (
            "Is the supervisor dashboard part of the first release?",
            "Is the supervisor dashboard in scope for the first release?",
        ),
    ),
    resolved_detail="synchronized automatically when the connection returns",
    resolved_fragments=("platform", "network coverage"),
)

CLINIC = Scenario(
    request=(
        "We need a patient portal for appointment booking. Which languages the "
        "portal supports is not decided. The reminder schedule is undecided."
    ),
    resolved=(
        (
            "Which languages must the portal support?",
            "The portal must support English and Spanish.",
        ),
        (
            "When should appointment reminders be sent?",
            "Patients receive an SMS reminder 24 hours before the appointment. "
            "A second reminder is sent two hours before if the first was not "
            "acknowledged.",
        ),
    ),
    pending=(
        (
            "Which payment gateway will be used?",
            "Finance has not approved a gateway yet.",
        ),
    ),
    stale_unknowns=(
        "Which languages will the portal support?",
        "The portal language list is undecided.",
        "When will appointment reminders be sent?",
    ),
    pending_variants=(
        (
            "Which payment gateway will be used?",
            "Has finance approved the payment gateway?",
            "Payment gateway approval is outstanding",
        ),
    ),
    resolved_detail="second reminder is sent two hours before",
    resolved_fragments=("language", "reminder"),
)

SCENARIOS = pytest.mark.parametrize("scenario", [WAREHOUSE, CLINIC], ids=["a", "b"])


def _history(scenario: Scenario) -> list[dict]:
    return [
        {"question": q, "answer": a}
        for q, a in (*scenario.resolved, *scenario.pending)
    ]


def _state(scenario: Scenario, **extra) -> dict:
    state = {
        "user_request": scenario.request,
        "clarification_history": _history(scenario),
        "iteration": 2,
    }
    state.update(extra)
    return state


class ScriptedProvider:
    """Returns a fixed artifact per schema, like a model that re-reads the request."""

    def __init__(self, discovery=None, requirements=None, validation=None):
        self.responses = {
            id(DISCOVERY_SCHEMA): discovery,
            id(REQUIREMENTS_SCHEMA): requirements,
            id(VALIDATION_SCHEMA): validation,
        }

    def generate_json(self, prompt, schema):
        return dict(self.responses[id(schema)])


def _discovery(scenario: Scenario) -> dict:
    return {
        "problem": "Operational app",
        "business_goal": "Faster operations",
        "users": ["Operators"],
        "stakeholders": [],
        "existing_systems": [],
        "constraints": [],
        "assumptions": [],
        "unknowns": [
            *scenario.stale_unknowns,
            *[variants[0] for variants in scenario.pending_variants],
        ],
        "clarification_questions": [*scenario.stale_unknowns],
    }


def _lower_all(items) -> str:
    return " ".join(str(item) for item in items).lower()


@SCENARIOS
def test_statements_are_classified_resolved_or_pending(scenario):
    decisions = ClarificationDecisions(_state(scenario))
    resolved_text = _lower_all(s.text for s in decisions.resolved)
    pending_text = _lower_all(s.text for s in decisions.pending)
    assert scenario.resolved_detail in resolved_text
    for _question, answer in scenario.pending:
        assert answer.lower() in pending_text
        assert answer.lower() not in resolved_text


@SCENARIOS
def test_resolved_decision_is_sourced_requirement_and_acceptance(scenario):
    requirements = apply_decisions_to_requirements(
        {
            "functional_requirements": ["Operators complete their core task."],
            "non_functional_requirements": [],
            "acceptance_criteria": [],
            "open_questions": [],
            "contradictions": [],
        },
        _state(scenario),
    )
    functional = [
        item for item in requirements["functional_requirements"]
        if scenario.resolved_detail in item
    ]
    assert len(functional) == 1
    assert "Source: customer clarification" in functional[0]
    assert any(
        scenario.resolved_detail in item
        for item in requirements["acceptance_criteria"]
    )
    statuses = {d["status"] for d in requirements["clarified_decisions"]}
    assert statuses == {"RESOLVED", "PENDING"}


@SCENARIOS
def test_applying_decisions_twice_adds_nothing(scenario):
    once = apply_decisions_to_requirements({"open_questions": []}, _state(scenario))
    twice = apply_decisions_to_requirements(once, _state(scenario))
    for key in (
        "functional_requirements",
        "non_functional_requirements",
        "acceptance_criteria",
        "open_questions",
    ):
        assert twice[key] == once[key]


@SCENARIOS
def test_existing_equivalent_requirement_is_not_duplicated(scenario):
    detail = next(
        answer for _q, answer in scenario.resolved if scenario.resolved_detail in answer
    )
    requirements = apply_decisions_to_requirements(
        {"functional_requirements": [detail], "acceptance_criteria": [detail]},
        _state(scenario),
    )
    mentions = [
        item for item in requirements["functional_requirements"]
        if scenario.resolved_detail in item
    ]
    assert mentions == [detail]


@SCENARIOS
def test_resume_path_reconciles_discovery_and_requirements(scenario):
    merged = apply_clarification_facts(
        _state(
            scenario,
            discovery=_discovery(scenario),
            requirements={
                "functional_requirements": [],
                "open_questions": list(scenario.stale_unknowns),
                "contradictions": [
                    f"The request leaves the {scenario.stale_unknowns[0].lower()[:-1]} "
                    "undecided, which contradicts the later answer."
                ],
            },
        )
    )
    unknowns = _lower_all(merged["discovery"]["unknowns"])
    open_questions = _lower_all(merged["requirements"]["open_questions"])
    for fragment in scenario.resolved_fragments:
        assert fragment not in unknowns
        assert fragment not in open_questions
    assert merged["requirements"]["contradictions"] == []
    assert any(
        scenario.resolved_detail in item
        for item in merged["requirements"]["functional_requirements"]
    )
    for variants in scenario.pending_variants:
        assert variants[0] in merged["discovery"]["unknowns"]


@SCENARIOS
def test_discovery_and_requirements_agents_drop_stale_wording(scenario):
    state = _state(scenario)
    discovery = discovery_agent(
        state, ScriptedProvider(discovery=_discovery(scenario))
    )["discovery"]
    assert not set(scenario.stale_unknowns) & set(discovery["unknowns"])
    assert discovery["clarification_questions"] == []

    requirements = requirements_agent(
        {**state, "discovery": discovery},
        ScriptedProvider(
            requirements={
                "functional_requirements": ["Operators complete their core task."],
                "non_functional_requirements": [],
                "acceptance_criteria": ["The core task can be completed."],
                "open_questions": list(scenario.stale_unknowns),
                "contradictions": [],
            }
        ),
    )["requirements"]
    for fragment in scenario.resolved_fragments:
        assert fragment not in _lower_all(requirements["open_questions"])
    assert any(
        scenario.resolved_detail in item
        for item in requirements["functional_requirements"]
    )
    assert any(
        scenario.resolved_detail in item
        for item in requirements["acceptance_criteria"]
    )


@SCENARIOS
def test_validation_keeps_pending_once_and_drops_resolved(scenario):
    state = _state(
        scenario,
        discovery={**_discovery(scenario), "unknowns": list(scenario.stale_unknowns)},
        requirements={
            "functional_requirements": ["Operators complete their core task."],
            "open_questions": [
                variant for variants in scenario.pending_variants for variant in variants
            ],
            "contradictions": [],
        },
    )
    validation = validation_agent(
        state,
        ScriptedProvider(
            validation={
                "status": "READY",
                "reasons": ["Ready for preliminary shaping."],
                "questions": [],
                "non_blocking_questions": [
                    *scenario.stale_unknowns,
                    *[v for variants in scenario.pending_variants for v in variants],
                ],
            }
        ),
    )["validation"]

    questions = validation["non_blocking_questions"]
    text = _lower_all(questions)
    for fragment in scenario.resolved_fragments:
        assert fragment not in text
    for variants in scenario.pending_variants:
        matches = [
            q for q in questions
            if any(
                dedupe_equivalent_questions([q, variant]) == [q]
                for variant in variants
            )
        ]
        assert len(matches) == 1, (variants, questions)
    assert len(dedupe_equivalent_questions(questions)) == len(questions)


@SCENARIOS
def test_pending_answer_does_not_close_its_own_question(scenario):
    pending_question = scenario.pending[0][0]
    validation = validation_agent(
        _state(
            scenario,
            discovery={**_discovery(scenario), "unknowns": []},
            requirements={"functional_requirements": ["x y z"], "open_questions": []},
        ),
        ScriptedProvider(
            validation={
                "status": "READY",
                "reasons": ["Ready for preliminary shaping."],
                "questions": [],
                "non_blocking_questions": [pending_question],
            }
        ),
    )["validation"]
    assert pending_question in validation["non_blocking_questions"]


@SCENARIOS
def test_downstream_artifacts_drop_resolved_decisions_only(scenario):
    stale = f"Customer to decide: {scenario.stale_unknowns[0]}"
    pending = f"Customer to decide: {scenario.pending_variants[0][1]}"
    cleaned = _ground_downstream_artifact(
        {"dependencies": [stale, pending, "Provision build servers"]},
        _state(scenario),
    )
    assert stale not in cleaned["dependencies"]
    assert pending in cleaned["dependencies"]
    assert "Provision build servers" in cleaned["dependencies"]


@SCENARIOS
def test_original_request_is_preserved_in_response(scenario):
    result = {
        "user_request": scenario.request,
        "clarification_history": _history(scenario),
        "requirements": apply_decisions_to_requirements({}, _state(scenario)),
        "validation": {"status": "READY", "non_blocking_questions": []},
        "workflow_status": "COMPLETE",
    }
    payload = workflow_response(result, run_id="reconcile-test")
    assert payload["user_request"] == scenario.request
    assert payload["requirements"]["clarified_decisions"]


def test_unrelated_answer_does_not_close_unrelated_question():
    state = {
        "user_request": "Build a reporting dashboard.",
        "clarification_history": [
            {
                "question": "Which tablet platforms should the first release support?",
                "answer": "Both Windows and Linux tablets must be supported.",
            }
        ],
    }
    unrelated = "Which hosting provider and region should be used?"
    requirements = apply_decisions_to_requirements(
        {"open_questions": [unrelated]}, state
    )
    assert requirements["open_questions"] == [unrelated]


def test_dedupe_keeps_distinct_questions_and_first_variant():
    questions = [
        "Which hosting provider and region should be used?",
        "Which retention period applies to photos?",
        "Has the customer approved the hosting provider and region?",
    ]
    assert dedupe_equivalent_questions(questions) == questions[:2]
    items = [{"question": questions[0]}, {"question": questions[2]}]
    assert dedupe_equivalent_questions(items) == items[:1]


def test_without_clarifications_requirements_are_untouched():
    requirements = {"functional_requirements": ["a b c"], "open_questions": ["Q one?"]}
    assert apply_decisions_to_requirements(requirements, {"user_request": "x"}) == requirements
