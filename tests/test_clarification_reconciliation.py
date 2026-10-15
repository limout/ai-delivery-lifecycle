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
    apply_established_scope_carry,
    discovery_agent,
    requirements_agent,
    validation_agent,
)
from app.api import workflow_response
from app.decisions import (
    ClarificationDecisions,
    apply_decisions_to_requirements,
    collapse_equivalent_scope_items,
    dedupe_equivalent_questions,
    is_pending_text,
    questions_equivalent,
    reconcile_open_questions,
    strip_verified_clarification_items,
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
    assert not any(
        "verified by demonstration" in str(item).lower()
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
    remaining = list(merged["discovery"]["unknowns"]) + list(
        merged["requirements"]["open_questions"]
    )
    for variants in scenario.pending_variants:
        assert any(
            questions_equivalent(variant, item)
            for variant in variants
            for item in remaining
        ), remaining


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
        assert not any(
            "verified by demonstration" in str(item).lower()
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
    remaining = validation["non_blocking_questions"]
    assert any(questions_equivalent(pending_question, item) for item in remaining), remaining


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


def _round_two_state(history, previous_questions, extra_questions, request):
    return {
        "user_request": request,
        "clarification_history": history,
        "discovery": {
            "problem": "Operational app",
            "business_goal": "Faster operations",
            "users": ["Operators"],
            "stakeholders": [],
            "existing_systems": [],
            "constraints": [],
            "assumptions": [],
            "unknowns": list(previous_questions),
            "clarification_questions": [],
        },
        "requirements": {
            "functional_requirements": ["Operators complete their core task."],
            "non_functional_requirements": [],
            "acceptance_criteria": ["The core task can be completed."],
            "open_questions": list(previous_questions),
            "contradictions": [],
        },
        "iteration": 3,
    }, list(previous_questions) + list(extra_questions)


WAREHOUSE_REQUEST = WAREHOUSE.request
CLINIC_REQUEST = CLINIC.request


def test_later_round_closes_broad_offline_and_replaces_hosting():
    history = _history(WAREHOUSE)
    previous = [
        "Which tablet platforms should the first release support?",
        "How should the app behave without network coverage?",
        "Which hosting provider and region should be used?",
        "What retention period applies to pick photos?",
        "Is the supervisor dashboard part of the first release?",
    ]
    follow_ups = [
        "What conflict-resolution policy applies when two pickers confirm the same item offline?",
        "How should conflicts be resolved when concurrent offline confirmations update the same pick?",
        "Has the proposed three-year pick photo retention period been approved?",
    ]
    state, candidates = _round_two_state(history, previous, follow_ups, WAREHOUSE_REQUEST)
    original_history = [dict(item) for item in history]
    validation = validation_agent(
        state,
        ScriptedProvider(
            validation={
                "status": "READY",
                "reasons": ["Ready for preliminary shaping."],
                "questions": [],
                "non_blocking_questions": candidates,
            }
        ),
    )
    questions = validation["validation"]["non_blocking_questions"]
    open_questions = validation["requirements"]["open_questions"]
    blob = _lower_all(questions)

    assert questions == open_questions
    assert "network coverage" not in blob
    assert "tablet platforms" not in blob
    assert "which hosting provider and region should be used?" not in blob
    assert "what retention period applies to pick photos?" not in blob
    conflict = [q for q in questions if "conflict" in q.lower()]
    assert len(conflict) == 1, questions
    assert any("approved" in q.lower() and "host" in q.lower() for q in questions), questions
    assert any("supervisor dashboard" in q.lower() for q in questions)
    assert state["user_request"] == WAREHOUSE_REQUEST
    assert state["clarification_history"] == original_history


def test_clinic_domain_partial_answer_leaves_unresolved_remainder():
    history = _history(CLINIC)
    previous = [
        "Which languages must the portal support?",
        "When should appointment reminders be sent?",
        "Which payment gateway will be used?",
        "What are the expected user roles and permissions?",
    ]
    follow_ups = [
        "What is the exact permission matrix for the proposed clinic-staff and patient roles?",
        "Has finance approved the payment gateway?",
    ]
    history = list(history) + [
        {
            "question": "What are the expected user roles and permissions?",
            "answer": (
                "We propose clinic staff and patients as the user roles; "
                "the permission matrix is not yet defined."
            ),
        }
    ]
    state, candidates = _round_two_state(history, previous, follow_ups, CLINIC_REQUEST)
    result = validation_agent(
        state,
        ScriptedProvider(
            validation={
                "status": "READY",
                "reasons": ["Ready for preliminary shaping."],
                "questions": [],
                "non_blocking_questions": candidates,
            }
        ),
    )
    questions = result["validation"]["non_blocking_questions"]
    blob = _lower_all(questions)
    assert "which languages" not in blob
    assert "appointment reminders" not in blob
    assert questions == result["requirements"]["open_questions"]
    assert any("permission" in q.lower() for q in questions), questions
    assert any("gateway" in q.lower() for q in questions), questions
    assert not any(
        q.lower() == "what are the expected user roles and permissions?"
        for q in questions
    )
    permission = [q for q in questions if "permission" in q.lower()]
    assert permission
    assert state["user_request"] == CLINIC_REQUEST


def test_equivalent_conflict_questions_are_deduplicated_without_answers():
    questions = [
        "What conflict-resolution policy applies when two technicians edit the same offline record?",
        "How should conflicts be resolved when concurrent offline submissions update the same inspection?",
        "What is the expected user volume and concurrent load for the web application?",
    ]
    assert len(dedupe_equivalent_questions(questions)) == 2
    reconciled = reconcile_open_questions(questions, {"user_request": "Build an inspection app."})
    texts = [q if isinstance(q, str) else q["question"] for q in reconciled]
    assert len([q for q in texts if "conflict" in q.lower()]) == 1
    assert any("user volume" in q.lower() for q in texts)


def test_distinct_same_topic_questions_remain_separate():
    questions = [
        "Which hosting provider should be used?",
        "Which region should hosting use?",
        "Has the proposed hosting provider been approved?",
    ]
    state = {
        "user_request": "Build a warehouse tablet app.",
        "clarification_history": [
            {
                "question": "Which hosting provider should be used?",
                "answer": "We propose Provider A, but the hosting provider has not been approved yet.",
            }
        ],
    }
    reconciled = [str(q) for q in reconcile_open_questions(questions, state)]
    blob = _lower_all(reconciled)
    assert "which region should hosting use?" in blob
    assert "which hosting provider should be used?" not in blob
    assert any("approved" in q.lower() and "provider" in q.lower() for q in reconciled)


def test_resolved_question_does_not_reappear_in_later_validation():
    state = _state(
        WAREHOUSE,
        discovery={**_discovery(WAREHOUSE), "unknowns": []},
        requirements={
            "functional_requirements": ["Operators complete their core task."],
            "open_questions": [],
            "contradictions": [],
        },
    )
    first = validation_agent(
        state,
        ScriptedProvider(
            validation={
                "status": "READY",
                "reasons": ["Ready for preliminary shaping."],
                "questions": [],
                "non_blocking_questions": [
                    "How should the app behave without network coverage?",
                    "Which hosting provider and region should be used?",
                ],
            }
        ),
    )
    later_state = {
        **state,
        "requirements": first["requirements"],
        "validation": first["validation"],
    }
    second = validation_agent(
        later_state,
        ScriptedProvider(
            validation={
                "status": "READY",
                "reasons": ["Ready for preliminary shaping."],
                "questions": [],
                    "non_blocking_questions": [
                        "How should the app behave without network coverage?",
                        "What should the app do when there is no network coverage?",
                        "Which hosting provider and region should be used?",
                    ],
            }
        ),
    )
    blob = _lower_all(second["validation"]["non_blocking_questions"])
    assert "network coverage" not in blob
    assert "offline behavior" not in blob
    payload = workflow_response(
        {
            "user_request": WAREHOUSE.request,
            "clarification_history": _history(WAREHOUSE),
            "requirements": second["requirements"],
            "validation": second["validation"],
            "workflow_status": "COMPLETE",
            "sow": {
                "in_scope": ["Core picking"],
                "out_of_scope": ["Analytics"],
                "deliverables": ["Tablet app"],
            },
            "solution": {"key_capabilities": ["Confirm picks"]},
            "delivery_plan": {
                "delivery_phases": ["Build"],
                "workstreams": ["App"],
                "milestones": ["Release"],
            },
        },
        run_id="question-lifecycle",
    )
    assert payload["user_request"] == WAREHOUSE.request
    assert payload["clarification_history"] == _history(WAREHOUSE)
    assert payload["requirements"]["open_questions"] == [
        item["question"] for item in payload["non_blocking_questions"]
    ]
    assert "network coverage" not in _lower_all(payload["requirements"]["open_questions"])


def test_thirteen_question_accumulation_is_reconciled():
    """Focused stand-in for the UI 13-question accumulation case. No LLM."""
    request = (
        "Build a mobile inspection app for technicians. The mobile platform "
        "and offline rules are undecided. Hosting, retention, checklists, "
        "and manager oversight still need confirmation."
    )
    history = [
        {
            "question": "Should the first release support iOS, Android, or both platforms?",
            "answer": "Both iOS and Android must be supported.",
        },
        {
            "question": (
                "What are the specific requirements for offline behavior and data "
                "synchronization when technicians work at remote sites with unreliable connectivity?"
            ),
            "answer": (
                "Technicians can view jobs, complete checklists, and attach photos "
                "with no connection. Completed work is queued and synchronized "
                "automatically when connectivity returns."
            ),
        },
        {
            "question": (
                "What are the hosting arrangements and infrastructure preferences "
                "for backend services or data storage?"
            ),
            "answer": (
                "We propose a regional cloud provider in the EU, but the hosting "
                "provider and region have not been approved yet."
            ),
        },
        {
            "question": (
                "What are the specific photo retention policies and storage limits "
                "required for inspection photographs?"
            ),
            "answer": (
                "We suggest retaining inspection photographs for three years; that "
                "retention period is pending approval."
            ),
        },
        {
            "question": (
                "What are the detailed inspection checklist requirements and defect "
                "categories for the first release?"
            ),
            "answer": (
                "The detailed inspection checklist and defect categories have not "
                "been signed off yet."
            ),
        },
        {
            "question": "Is the manager oversight interface in scope for the first release?",
            "answer": (
                "Whether the manager oversight interface belongs in the first-release "
                "scope has not been decided yet."
            ),
        },
        {
            "question": "What are the expected user roles and permissions?",
            "answer": (
                "We propose field technicians and operations managers as the user "
                "roles; the permission matrix is not yet defined."
            ),
        },
    ]
    thirteen = [
        "Should the first release support iOS, Android, or both platforms?",
        "What are the specific requirements for offline behavior and data synchronization when technicians work at remote sites with unreliable connectivity?",
        "What are the hosting arrangements and infrastructure preferences for backend services or data storage?",
        "What are the specific photo retention policies and storage limits required for inspection photographs?",
        "What are the detailed inspection checklist requirements and defect categories for the first release?",
        "Is the manager oversight interface in scope for the first release?",
        "What is the expected user volume and concurrent load for the web application?",
        "What are the expected user roles and permissions?",
        "Which cloud provider, region, data residency, and recovery arrangement should be confirmed?",
        "Has the proposed three-year photo retention period been approved?",
        "What conflict-resolution policy applies when two technicians edit the same offline record?",
        "How should conflicts be resolved when concurrent offline submissions update the same inspection?",
        "What is the exact permission matrix for the proposed field-technician and operations-manager roles?",
    ]
    assert len(thirteen) == 13
    state, candidates = _round_two_state(history, thirteen[:8], thirteen[8:], request)
    original_history = [dict(item) for item in history]
    result = validation_agent(
        state,
        ScriptedProvider(
            validation={
                "status": "READY",
                "reasons": ["Ready for preliminary shaping."],
                "questions": [],
                "non_blocking_questions": candidates,
            }
        ),
    )
    questions = result["validation"]["non_blocking_questions"]
    blob = _lower_all(questions)
    assert questions == result["requirements"]["open_questions"]
    assert "ios" not in blob and "android" not in blob
    assert "specific requirements for offline behavior" not in blob
    assert "hosting arrangements and infrastructure preferences" not in blob
    assert "specific photo retention policies" not in blob
    assert len([q for q in questions if "conflict" in q.lower()]) == 1
    assert any("manager oversight" in q.lower() for q in questions)
    assert any("permission" in q.lower() for q in questions)
    assert any("volume" in q.lower() for q in questions)
    assert "what are the expected user roles and permissions?" not in blob
    assert state["user_request"] == request
    assert state["clarification_history"] == original_history
    assert len(questions) < 13


def _decision_state(request: str, question: str, answer: str) -> dict:
    return {
        "user_request": request,
        "clarification_history": [{"question": question, "answer": answer}],
        "clarification_state": {
            "version": 1,
            "answers": [
                {
                    "question": question,
                    "answer": answer,
                    "status": "ACCEPTED",
                    "source": "customer clarification",
                }
            ],
            "decisions": [
                {
                    "question": question,
                    "decision": answer,
                    "status": "RESOLVED",
                    "source": "customer clarification",
                }
            ],
            "questions": [
                {
                    "question": question,
                    "status": "RESOLVED",
                    "priority": "REQUIRED",
                    "blocks_workflow": True,
                    "reason": "",
                }
            ],
        },
    }


def test_compound_restatement_does_not_create_mega_requirement():
    question = "Who will use the first release, and what will they do in it?"
    restatement = (
        "They will search holdings, create holds, and renew loans."
    )
    requirements = apply_decisions_to_requirements(
        {
            "functional_requirements": [
                "Members can search holdings.",
                "Members can create holds.",
                "Members can renew loans.",
            ],
            "non_functional_requirements": [],
            "acceptance_criteria": [
                "A member can search holdings.",
                "A member can create holds.",
                "A member can renew loans.",
            ],
            "open_questions": [],
            "contradictions": [],
        },
        _decision_state(
            "Build a catalog so members can search holdings, create holds, "
            "and renew loans.",
            question,
            restatement,
        ),
    )
    sourced = [
        item
        for item in requirements["functional_requirements"]
        if "Source: customer clarification" in item
    ]
    assert not any(
        "search holdings" in item.lower()
        and "create holds" in item.lower()
        and "renew loans" in item.lower()
        for item in sourced
    )
    assert "Members can search holdings." in requirements["functional_requirements"]
    assert "Members can create holds." in requirements["functional_requirements"]
    assert "Members can renew loans." in requirements["functional_requirements"]


def test_additive_clarification_still_creates_requirement():
    question = "Who will use the first release, and what will they do in it?"
    additive = (
        "Librarians will also review incoming returns through a staff console."
    )
    requirements = apply_decisions_to_requirements(
        {
            "functional_requirements": [
                "Members can search holdings.",
                "Members can create holds.",
            ],
            "non_functional_requirements": [],
            "acceptance_criteria": [
                "A member can search holdings.",
                "A member can create holds.",
            ],
            "open_questions": [],
            "contradictions": [],
        },
        _decision_state(
            "Build a catalog so members can search holdings and create holds.",
            question,
            additive,
        ),
    )
    functional = " ".join(requirements["functional_requirements"]).lower()
    assert "review incoming returns" in functional
    assert any(
        "Source: customer clarification" in item
        for item in requirements["functional_requirements"]
    )


def test_additive_integration_clarification_still_creates_requirement():
    question = (
        "Which systems must the first release integrate with, and what is "
        "the source of truth?"
    )
    additive = (
        "The first release must integrate with the interlibrary loan service."
    )
    requirements = apply_decisions_to_requirements(
        {
            "functional_requirements": [
                "Members can search holdings.",
                "Integrate with the library catalog database.",
            ],
            "non_functional_requirements": [],
            "acceptance_criteria": [
                "A member can search holdings.",
            ],
            "open_questions": [],
            "contradictions": [],
        },
        _decision_state(
            "Build a catalog so members can search holdings.",
            question,
            additive,
        ),
    )
    functional = " ".join(requirements["functional_requirements"]).lower()
    assert "interlibrary loan" in functional
    assert "library catalog database" in functional


def test_kiosk_compound_restatement_does_not_create_mega_requirement():
    question = "Who will use the first release, and what will they do in it?"
    restatement = (
        "They will search visitor appointments and create check-in records."
    )
    requirements = apply_decisions_to_requirements(
        {
            "functional_requirements": [
                "Receptionists can search visitor appointments.",
                "Receptionists can create check-in records.",
            ],
            "non_functional_requirements": [],
            "acceptance_criteria": [
                "A receptionist can search visitor appointments.",
                "A receptionist can create check-in records.",
            ],
            "open_questions": [],
            "contradictions": [],
        },
        _decision_state(
            "Build a lobby kiosk so receptionists can search visitor "
            "appointments and create check-in records.",
            question,
            restatement,
        ),
    )
    sourced = [
        item
        for item in requirements["functional_requirements"]
        if "Source: customer clarification" in item
    ]
    assert not any(
        "search visitor appointments" in item.lower()
        and "create check-in records" in item.lower()
        for item in sourced
    )


def test_additive_offline_clarification_still_creates_requirement():
    question = (
        "What are the offline behavior and data synchronization rules?"
    )
    additive = (
        "Receptionists can search visitor appointments with no network "
        "connection. Queued check-ins synchronize automatically when "
        "connectivity returns."
    )
    requirements = apply_decisions_to_requirements(
        {
            "functional_requirements": [
                "Receptionists can search visitor appointments.",
                "Receptionists can create check-in records.",
            ],
            "non_functional_requirements": [],
            "acceptance_criteria": [
                "A receptionist can search visitor appointments.",
            ],
            "open_questions": [],
            "contradictions": [],
        },
        _decision_state(
            "Build a lobby kiosk so receptionists can search visitor "
            "appointments and create check-in records.",
            question,
            additive,
        ),
    )
    functional = " ".join(requirements["functional_requirements"]).lower()
    assert "network" in functional or "offline" in functional or "queued" in functional
    assert "synchronize" in functional or "connectivity" in functional


def test_must_shall_paraphrase_collapses_without_dropping_distinct_behaviors():
    collapsed = collapse_equivalent_scope_items(
        [
            "The system must allow members to search holdings.",
            "The system shall allow members to search holdings.",
            "Members can create holds.",
            "Librarians can review incoming returns.",
            "Integrate with the library catalog database.",
            "Integrate with the interlibrary loan service.",
            "Integrate with the patron identity directory.",
            "Members can search holdings with no network connection.",
            "Queued updates persist locally and synchronize when connectivity returns.",
            "The system must prevent duplicate submissions.",
            "The system must provide a way to resolve synchronization conflicts.",
        ]
    )
    blob = " ".join(collapsed).lower()
    search_online = [
        item
        for item in collapsed
        if "search holdings" in item.lower() and "network" not in item.lower()
    ]
    assert len(search_online) == 1
    assert "create holds" in blob
    assert "review incoming returns" in blob
    assert "library catalog database" in blob
    assert "interlibrary loan" in blob
    assert "patron identity" in blob
    assert "network" in blob
    assert "synchronize" in blob or "connectivity" in blob
    assert "duplicate" in blob
    assert "conflict" in blob


def test_kiosk_must_shall_paraphrase_collapses_without_dropping_distinct_behaviors():
    collapsed = collapse_equivalent_scope_items(
        [
            "The system must allow receptionists to search visitor appointments.",
            "The system shall allow receptionists to search visitor appointments.",
            "Receptionists can create check-in records.",
            "Security officers can review today's check-ins.",
            "Integrate with the visitor appointment register.",
            "Integrate with the staff messaging bus.",
            "Integrate with the building access panel.",
            "Receptionists can search visitor appointments with no network connection.",
            "Queued check-ins persist locally and synchronize when connectivity returns.",
            "The system must prevent duplicate submissions.",
            "The system must provide a way to resolve synchronization conflicts.",
        ]
    )
    blob = " ".join(collapsed).lower()
    search_online = [
        item
        for item in collapsed
        if "search visitor" in item.lower() and "network" not in item.lower()
    ]
    assert len(search_online) == 1
    assert "check-in records" in blob
    assert "security officers" in blob
    assert "visitor appointment register" in blob
    assert "staff messaging bus" in blob
    assert "building access panel" in blob
    assert "network" in blob
    assert "duplicate" in blob
    assert "conflict" in blob


def test_strip_verified_clarification_keeps_testable_acceptance():
    cleaned = strip_verified_clarification_items(
        [
            "A member can search holdings.",
            "Verified by demonstration or test that: Members can search holdings "
            "(Source: customer clarification)",
            "A librarian can review incoming returns.",
        ]
    )
    blob = " ".join(cleaned).lower()
    assert "verified by demonstration" not in blob
    assert "a member can search holdings." in blob
    assert "a librarian can review incoming returns." in blob


def _constituent_survives(items, phrase, excluded):
    return any(
        phrase in item.lower() and excluded not in item.lower()
        for item in items
    )


def test_compound_first_does_not_drop_constituent_behaviors():
    collapsed = collapse_equivalent_scope_items(
        [
            "Members can complete inspection checklists and record equipment defects.",
            "Members can complete inspection checklists.",
            "Members can record equipment defects.",
        ]
    )
    blob = " ".join(collapsed).lower()
    assert "complete inspection checklists" in blob
    assert "record equipment defects" in blob
    assert _constituent_survives(
        collapsed, "complete inspection checklists", "record equipment defects"
    )
    assert _constituent_survives(
        collapsed, "record equipment defects", "complete inspection checklists"
    )


def test_compound_last_does_not_drop_constituent_behaviors():
    collapsed = collapse_equivalent_scope_items(
        [
            "Members can complete inspection checklists.",
            "Members can record equipment defects.",
            "Members can complete inspection checklists and record equipment defects.",
        ]
    )
    blob = " ".join(collapsed).lower()
    assert "complete inspection checklists" in blob
    assert "record equipment defects" in blob
    assert _constituent_survives(
        collapsed, "complete inspection checklists", "record equipment defects"
    )
    assert _constituent_survives(
        collapsed, "record equipment defects", "complete inspection checklists"
    )


def test_short_view_fragment_collapses_into_equivalent_must_shall():
    collapsed = collapse_equivalent_scope_items(
        [
            "View assigned jobs",
            "The system must allow technicians to view assigned jobs.",
            "The system shall allow technicians to view assigned jobs.",
        ]
    )
    view_items = [
        item for item in collapsed if "view assigned jobs" in item.lower()
    ]
    assert len(view_items) == 1

    reversed_order = collapse_equivalent_scope_items(
        [
            "The system must allow technicians to view assigned jobs.",
            "View assigned jobs",
            "The system shall allow technicians to view assigned jobs.",
        ]
    )
    reversed_view = [
        item for item in reversed_order if "view assigned jobs" in item.lower()
    ]
    assert len(reversed_view) == 1


def test_offline_conflict_manager_and_integrations_remain_distinct():
    collapsed = collapse_equivalent_scope_items(
        [
            "The system must allow members to search holdings.",
            "The system shall allow members to search holdings.",
            "Members can search holdings with no network connection.",
            "Queued updates persist locally and synchronize when connectivity returns.",
            "The system must prevent duplicate submissions.",
            "The system must provide a way to resolve synchronization conflicts.",
            "Librarians can review incoming work.",
            "Librarians can track delivery status.",
            "Librarians can identify blockers.",
            "Librarians can coordinate follow-up.",
            "Integrate with the library catalog database.",
            "Integrate with the interlibrary loan service.",
            "Integrate with the patron identity directory.",
        ]
    )
    blob = " ".join(collapsed).lower()
    search_online = [
        item
        for item in collapsed
        if "search holdings" in item.lower() and "network" not in item.lower()
    ]
    assert len(search_online) == 1
    assert "network" in blob
    assert "synchronize" in blob or "connectivity" in blob
    assert "duplicate" in blob
    assert "conflict" in blob
    assert "review incoming work" in blob
    assert "track delivery status" in blob
    assert "identify blockers" in blob
    assert "coordinate follow-up" in blob
    assert "library catalog database" in blob
    assert "interlibrary loan" in blob
    assert "patron identity" in blob


def test_apply_decisions_strips_verified_acceptance_without_statements():
    requirements = apply_decisions_to_requirements(
        {
            "functional_requirements": [
                "Members can search holdings.",
                "The system must prevent duplicate submissions.",
            ],
            "acceptance_criteria": [
                "A member can search holdings from the catalog.",
                "Verified by demonstration or test that: Members can search holdings "
                "(Source: customer clarification)",
            ],
        },
        {"user_request": "x"},
    )
    acceptance = [str(item).lower() for item in requirements["acceptance_criteria"]]
    assert not any("verified by demonstration" in item for item in acceptance)
    assert any("a member can search holdings from the catalog." in item for item in acceptance)
    functional = " ".join(requirements["functional_requirements"]).lower()
    assert "search holdings" in functional
    assert "duplicate" in functional


def test_apply_decisions_strips_verified_acceptance_with_statements():
    requirements = apply_decisions_to_requirements(
        {
            "functional_requirements": ["Members can search holdings."],
            "non_functional_requirements": [],
            "acceptance_criteria": [
                "A member can search holdings from the catalog.",
                "Verified by demonstration or test that: Members can search holdings "
                "(Source: customer clarification)",
            ],
            "open_questions": [],
            "contradictions": [],
        },
        _decision_state(
            "Build a catalog so members can search holdings.",
            "Who will use the first release, and what will they do in it?",
            "Librarians will also review incoming returns through a staff console.",
        ),
    )
    acceptance = [str(item).lower() for item in requirements["acceptance_criteria"]]
    assert not any("verified by demonstration" in item for item in acceptance)
    assert any("a member can search holdings from the catalog." in item for item in acceptance)
    functional = " ".join(requirements["functional_requirements"]).lower()
    assert "search holdings" in functional
    assert "review incoming returns" in functional


def test_requirements_agent_strips_verified_acceptance_after_merge():
    state = {
        "user_request": "Build a catalog so members can search holdings.",
        "clarification_history": [],
        "discovery": {
            "problem": "Catalog",
            "business_goal": "Faster holds",
            "users": ["Members"],
            "stakeholders": [],
            "existing_systems": [],
            "constraints": [],
            "assumptions": [],
            "unknowns": [],
            "clarification_questions": [],
        },
        "requirements": {
            "functional_requirements": ["Members can search holdings."],
            "acceptance_criteria": [
                "Verified by demonstration or test that: Members can search holdings.",
            ],
        },
    }
    requirements = requirements_agent(
        state,
        ScriptedProvider(
            requirements={
                "functional_requirements": ["Members can search holdings."],
                "non_functional_requirements": [],
                "acceptance_criteria": [
                    "A member can search holdings from the catalog.",
                    "Verified by demonstration or test that: Members can create holds.",
                ],
                "open_questions": [],
                "contradictions": [],
            }
        ),
    )["requirements"]
    acceptance = [str(item).lower() for item in requirements["acceptance_criteria"]]
    assert not any("verified by demonstration" in item for item in acceptance)
    assert any("a member can search holdings from the catalog." in item for item in acceptance)
    functional = " ".join(requirements["functional_requirements"]).lower()
    assert "search holdings" in functional


SHALL_ALLOW_VIEW = (
    "The system shall allow technicians to view assigned sites and inspection jobs."
)
MUST_BE_ABLE_VIEW = (
    "Field technicians must be able to view assigned commercial solar "
    "installation sites and inspection jobs."
)
EQUIVALENT_BEHAVIOR_PAIRS = (
    (
        "The system shall allow technicians to access installation details "
        "and previous inspection reports.",
        "Field technicians must be able to access installation details and "
        "previous inspection reports.",
        "access installation details",
    ),
    (
        "The system shall allow technicians to complete inspection checklists.",
        "Field technicians must be able to complete inspection checklists.",
        "complete inspection checklists",
    ),
    (
        "The system shall allow technicians to record equipment defects.",
        "Field technicians must be able to record equipment defects.",
        "record equipment defects",
    ),
    (
        "The system shall allow technicians to submit inspection reports.",
        "Field technicians must be able to submit inspection reports.",
        "submit inspection reports",
    ),
    (
        "The system shall allow technicians to create follow-up actions.",
        "Field technicians must be able to create follow-up actions.",
        "create follow-up",
    ),
)


def test_shall_allow_and_must_be_able_view_jobs_collapse_to_one():
    collapsed = collapse_equivalent_scope_items(
        [SHALL_ALLOW_VIEW, MUST_BE_ABLE_VIEW]
    )
    assert len(collapsed) == 1
    blob = collapsed[0].lower()
    assert "view assigned" in blob
    assert "inspection jobs" in blob
    reversed_order = collapse_equivalent_scope_items(
        [MUST_BE_ABLE_VIEW, SHALL_ALLOW_VIEW]
    )
    assert len(reversed_order) == 1


def test_shall_allow_and_must_be_able_equivalent_behaviors_collapse():
    for shall, able, fragment in EQUIVALENT_BEHAVIOR_PAIRS:
        collapsed = collapse_equivalent_scope_items([shall, able])
        assert len(collapsed) == 1, fragment
        assert fragment in collapsed[0].lower()


def test_modal_collapse_keeps_distinct_checklist_defect_offline_and_integrations():
    collapsed = collapse_equivalent_scope_items(
        [
            SHALL_ALLOW_VIEW,
            MUST_BE_ABLE_VIEW,
            "Members can complete inspection checklists.",
            "Members can record equipment defects.",
            "Members can complete inspection checklists and record equipment defects.",
            "Members can search holdings with no network connection.",
            "Queued updates persist locally and synchronize when connectivity returns.",
            "The system must prevent duplicate submissions.",
            "The system must provide a way to resolve synchronization conflicts.",
            "Integrate with the asset registry.",
            "Integrate with the project management system.",
            "Integrate with the source-code repository.",
        ]
    )
    blob = " ".join(collapsed).lower()
    view_items = [
        item for item in collapsed if "view assigned" in item.lower()
    ]
    assert len(view_items) == 1
    assert _constituent_survives(
        collapsed, "complete inspection checklists", "record equipment defects"
    )
    assert _constituent_survives(
        collapsed, "record equipment defects", "complete inspection checklists"
    )
    assert "network" in blob
    assert "synchronize" in blob or "connectivity" in blob
    assert "duplicate" in blob
    assert "conflict" in blob
    assert "asset registry" in blob
    assert "project management" in blob
    assert "source-code" in blob


def test_apply_decisions_collapses_equivalent_acceptance_criteria():
    requirements = apply_decisions_to_requirements(
        {
            "functional_requirements": ["Technicians can view assigned jobs."],
            "acceptance_criteria": [SHALL_ALLOW_VIEW, MUST_BE_ABLE_VIEW],
        },
        {"user_request": "x"},
    )
    acceptance = requirements["acceptance_criteria"]
    assert len(acceptance) == 1
    assert "view assigned" in acceptance[0].lower()


def test_apply_decisions_collapses_acceptance_and_functional_with_statements():
    requirements = apply_decisions_to_requirements(
        {
            "functional_requirements": [SHALL_ALLOW_VIEW, MUST_BE_ABLE_VIEW],
            "non_functional_requirements": [],
            "acceptance_criteria": [SHALL_ALLOW_VIEW, MUST_BE_ABLE_VIEW],
            "open_questions": [],
            "contradictions": [],
        },
        _decision_state(
            "Build a mobile inspection app for field technicians.",
            "Who will use the first release, and what will they do in it?",
            "Field technicians will view assigned jobs.",
        ),
    )
    view_frs = [
        item
        for item in requirements["functional_requirements"]
        if "view assigned" in item.lower()
    ]
    view_acceptance = [
        item
        for item in requirements["acceptance_criteria"]
        if "view assigned" in item.lower()
    ]
    assert len(view_frs) == 1
    assert len(view_acceptance) == 1


def test_apply_decisions_drops_pending_and_colon_truncated_sourced_fragments():
    colon_fragment = (
        "The first release must integrate with three existing systems: "
        "(Source: customer clarification)"
    )
    pending_fragment = (
        "The exact system names and integration details will be confirmed "
        "during implementation planning (Source: customer clarification)"
    )
    assert is_pending_text(
        "The exact system names and integration details will be confirmed "
        "during implementation planning"
    )
    requirements = apply_decisions_to_requirements(
        {
            "functional_requirements": [
                colon_fragment,
                pending_fragment,
                "Integrate with the asset registry.",
                "Integrate with the project management system.",
                "Integrate with the source-code repository.",
            ],
            "non_functional_requirements": [],
            "acceptance_criteria": [colon_fragment],
            "open_questions": [],
            "contradictions": [],
        },
        _decision_state(
            "Build a mobile inspection app for field technicians.",
            "Which systems must the first release integrate with, and what is "
            "the source of truth?",
            "The first release must integrate with three existing systems:\n"
            "The exact system names and integration details will be confirmed "
            "during implementation planning.\n"
            "Integrate with the asset registry. Integrate with the project "
            "management system. Integrate with the source-code repository.",
        ),
    )
    functional = " ".join(requirements["functional_requirements"]).lower()
    assert "three existing systems:" not in functional
    assert "will be confirmed during implementation planning" not in functional
    assert "asset registry" in functional
    assert "project management" in functional
    assert "source-code repository" in functional
    acceptance = " ".join(requirements["acceptance_criteria"]).lower()
    assert "three existing systems:" not in acceptance


def test_carry_collapses_modal_duplicates_across_capability_fields():
    state = {
        "user_request": "Build a mobile inspection app.",
        "requirements": {
            "functional_requirements": [SHALL_ALLOW_VIEW, MUST_BE_ABLE_VIEW],
            "acceptance_criteria": [SHALL_ALLOW_VIEW, MUST_BE_ABLE_VIEW],
        },
        "solution": {
            "key_capabilities": [SHALL_ALLOW_VIEW],
            "integration_approach": [],
        },
        "proposal": {"scope": [MUST_BE_ABLE_VIEW]},
        "sow": {
            "in_scope": [SHALL_ALLOW_VIEW],
            "acceptance": [MUST_BE_ABLE_VIEW],
            "out_of_scope": ["Analytics"],
        },
    }
    carried = apply_established_scope_carry(state)
    for field, items in (
        ("key_capabilities", carried["solution"]["key_capabilities"]),
        ("scope", carried["proposal"]["scope"]),
        ("in_scope", carried["sow"]["in_scope"]),
        ("acceptance", carried["sow"]["acceptance"]),
    ):
        view_items = [
            item for item in items if "view assigned" in str(item).lower()
        ]
        assert len(view_items) == 1, field
    assert "Analytics" in carried["sow"]["out_of_scope"]
