"""End-to-end reconciliation of clarification state and Assessment views.

Deterministic stand-in for the field-inspection run whose exported JSON
showed stale discovery unknowns, divergent Assessment fields, planning
facts promoted to requirements, and dropped unanswered request flags.
No live model call and no in-memory production run ID.
"""

import json

from fastapi.testclient import TestClient

from app.agents import (
    DISCOVERY_SCHEMA,
    REQUIREMENTS_SCHEMA,
    VALIDATION_SCHEMA,
    _ground_downstream_artifact,
    discovery_agent,
    requirements_agent,
    validation_agent,
)
from app.api import get_provider, workflow_response
from app.assessment import ASK_NEXT_LIMIT
from app.decisions import questions_equivalent
from app.evidence import normalize_question_text
from app.main import app
from app.providers import MockProvider
from app.resume import apply_clarification_facts

REQUEST = (
    "Build a mobile inspection app for field technicians who inspect and "
    "maintain installed assets. We have not yet decided whether the first "
    "release should support iOS, Android, or both platforms. Field technicians "
    "should view assigned sites and jobs, complete inspections, capture photos, "
    "and submit reports. Hosting arrangements, photo retention policies, and "
    "the detailed inspection checklist requirements also need clarification."
)

HISTORY = [
    {
        "question": "Should the first release support iOS, Android, or both platforms?",
        "answer": "Both iOS and Android must be supported.",
    },
    {
        "question": "Who will use the first release, and what will they do in it?",
        "answer": (
            "Field technicians are the primary users of the mobile app. They will "
            "view assigned sites and jobs, complete inspection and maintenance "
            "workflows, capture photos, and submit reports. Operations managers "
            "participate in weekly reviews of inspection results. Whether the "
            "Operations Manager needs a dedicated first-release interface has "
            "not been decided."
        ),
    },
    {
        "question": (
            "What are the specific requirements for offline behavior and data "
            "synchronization when technicians work at remote sites with unreliable connectivity?"
        ),
        "answer": (
            "Assigned-job data and checklists are available offline. Users can "
            "perform inspection work offline. Changes are stored locally and "
            "queued. Offline, pending-sync, and failure status must be visible. "
            "Retries must not silently lose or duplicate data. Conflicts must be "
            "detected rather than silently overwriting changes. The exact "
            "conflict-resolution workflow for conflicting synchronized changes "
            "has not yet been defined."
        ),
    },
    {
        "question": "Which existing systems are the source of truth, and is API access available?",
        "answer": (
            "The asset registry is the source of truth. API access and technical "
            "documentation are available and have been verified."
        ),
    },
    {
        "question": "What are the hosting arrangements and infrastructure preferences?",
        "answer": (
            "We propose managed cloud hosting with baseline security and "
            "infrastructure controls, but the cloud provider, hosting region, "
            "data residency requirements, and disaster-recovery targets have "
            "not been approved yet."
        ),
    },
    {
        "question": "What photo retention and deletion policy should apply?",
        "answer": (
            "We propose retaining inspection photographs for three years; the "
            "proposed retention and deletion policy has not been approved yet."
        ),
    },
    {
        "question": "What is the expected user volume and concurrent load?",
        "answer": (
            "The expected user volume has not yet been established. Obtain "
            "estimates from the customer for user counts, active installations, "
            "inspection volume, photo uploads, and peak concurrency. Do not "
            "assume a capacity target."
        ),
    },
    {
        "question": "What are the expected user roles and permissions?",
        "answer": (
            "Field Technician and Operations Manager roles and their broad "
            "responsibilities are described. We propose those two roles; the "
            "exact permission matrix and report-correction workflow are not "
            "yet defined."
        ),
    },
]

STALE_UNKNOWN = [
    "Who will use the first release, and what will they do in it?",
    "What are the expected user roles and permissions?",
    "What are the specific requirements for offline behavior and data synchronization when technicians work at remote sites with unreliable connectivity?",
    "Has the proposed user volume been approved?",
    "What are the hosting arrangements and infrastructure preferences?",
    "What photo retention and deletion policy should apply?",
]

MANDATORY_USERS_QUESTION = "Who will use the first release, and what will they do in it?"
MANDATORY_INTEGRATION_QUESTION = (
    "Which systems must the first release integrate with, and what "
    "is the source of truth?"
)
PENDING_INTERFACE_QUESTION = (
    "Has the Operations Manager dedicated first-release interface been decided?"
)
PENDING_PERMISSION_QUESTION = (
    "Have the exact permission matrix and report-correction workflow been defined?"
)

PRODUCTION_SHAPED_REQUEST = (
    "Build a mobile inspection first release to view assigned sites and jobs, "
    "complete inspections, capture photos, submit reports, and integrate with "
    "existing systems."
)

MANDATORY_ANSWERS = [
    (
        f"{MANDATORY_USERS_QUESTION}: "
        "Field technicians are the primary users of the mobile app. They will "
        "view assigned sites and jobs, complete inspection and maintenance "
        "workflows, capture photos, and submit reports. Operations managers "
        "participate in weekly reviews of inspection results. Whether the "
        "Operations Manager needs a dedicated first-release interface has not "
        "been decided. Field Technician and Operations Manager roles are "
        "identified, but the exact permission matrix and report-correction "
        "workflow are not yet defined."
    ),
    (
        f"{MANDATORY_INTEGRATION_QUESTION}: "
        "The Salesforce Asset Registry API is the source of truth for installed "
        "assets. API access and technical documentation are available and have "
        "been verified."
    ),
]

POLLUTED_FRS = [
    "Technicians can complete assigned inspections on a mobile device.",
    "Obtain estimates from the customer for user counts and peak concurrency.",
    "The expected user volume has not yet been established.",
    "API access has been verified.",
    "Conflicting offline edits are resolved by last-write-wins.",
]

POLLUTED_ACS = [
    "Verified by demonstration or test that: obtain estimates from the customer.",
    "Verified by demonstration or test that: API access has been verified.",
    "Verified by demonstration or test that: the expected user volume has not yet been established.",
]


class ScriptedProvider:
    def __init__(self, discovery=None, requirements=None, validation=None):
        self.responses = {
            id(DISCOVERY_SCHEMA): discovery,
            id(REQUIREMENTS_SCHEMA): requirements,
            id(VALIDATION_SCHEMA): validation,
        }

    def generate_json(self, prompt, schema):
        return dict(self.responses[id(schema)])


class StaleRegenerationProvider(MockProvider):
    def generate_json(self, prompt, schema):
        required = tuple((schema or {}).get("required") or [])
        if required == tuple(DISCOVERY_SCHEMA["required"]):
            return {
                "problem": "Mobile inspection app",
                "business_goal": "Improve field inspection execution",
                "users": ["Field technicians", "Operations Manager"],
                "stakeholders": [],
                "existing_systems": ["Salesforce Asset Registry API"],
                "constraints": [],
                "assumptions": [],
                "unknowns": [
                    MANDATORY_USERS_QUESTION,
                    MANDATORY_INTEGRATION_QUESTION,
                    PENDING_INTERFACE_QUESTION,
                    PENDING_PERMISSION_QUESTION,
                    "What are the hosting arrangements and infrastructure preferences?",
                    "What photo retention and deletion policy should apply?",
                    "What is the expected user volume and concurrent load?",
                ],
                "clarification_questions": [
                    MANDATORY_USERS_QUESTION,
                    MANDATORY_INTEGRATION_QUESTION,
                ],
            }
        if required == tuple(REQUIREMENTS_SCHEMA["required"]):
            return {
                "functional_requirements": [
                    "The system should support field inspections on mobile devices."
                ],
                "non_functional_requirements": [],
                "acceptance_criteria": [
                    "An authorized user can complete and submit an inspection."
                ],
                "open_questions": [
                    MANDATORY_USERS_QUESTION,
                    MANDATORY_INTEGRATION_QUESTION,
                    PENDING_INTERFACE_QUESTION,
                    PENDING_PERMISSION_QUESTION,
                ],
                "contradictions": [],
            }
        if required == tuple(VALIDATION_SCHEMA["required"]):
            return {
                "status": "READY",
                "reasons": ["The scripted provider intentionally repeats stale questions."],
                "questions": [],
                "non_blocking_questions": [
                    MANDATORY_USERS_QUESTION,
                    MANDATORY_INTEGRATION_QUESTION,
                    PENDING_INTERFACE_QUESTION,
                    PENDING_PERMISSION_QUESTION,
                ],
            }
        return super().generate_json(prompt, schema)


def _state(**extra):
    state = {
        "user_request": REQUEST,
        "clarification_history": [dict(item) for item in HISTORY],
        "iteration": 2,
        "regenerate_upstream": True,
    }
    state.update(extra)
    return state


def _stale_discovery():
    return {
        "problem": "Field inspection mobile app",
        "business_goal": "Complete inspections despite poor connectivity",
        "users": ["Field technicians", "Operations Manager"],
        "stakeholders": [],
        "existing_systems": ["Asset registry"],
        "constraints": ["Managed cloud hosting is proposed"],
        "assumptions": ["Photo retention of three years is approved"],
        "unknowns": list(STALE_UNKNOWN),
        "clarification_questions": list(STALE_UNKNOWN),
    }


def _stale_requirements():
    return {
        "functional_requirements": list(POLLUTED_FRS),
        "non_functional_requirements": [],
        "acceptance_criteria": list(POLLUTED_ACS),
        "open_questions": list(STALE_UNKNOWN),
        "contradictions": [],
    }


def _lower(items) -> str:
    return " ".join(str(item) for item in items).lower()


def _snapshot(payload: dict) -> dict:
    assessment = payload.get("assessment") or {}
    requirements = payload.get("requirements") or {}
    discovery = payload.get("discovery") or {}
    validation = payload.get("validation") or {}
    return {
        "user_request": payload.get("user_request"),
        "history_len": len(payload.get("clarification_history") or []),
        "unknowns": list(discovery.get("unknowns") or []),
        "open_questions": list(requirements.get("open_questions") or []),
        "non_blocking": list(validation.get("non_blocking_questions") or []),
        "users": list(discovery.get("users") or []),
        "stakeholders": list(discovery.get("stakeholders") or []),
        "what_is_uncertain": list(assessment.get("what_is_uncertain") or []),
        "ask_next": list(assessment.get("ask_next") or []),
        "functional": list(requirements.get("functional_requirements") or []),
        "acceptance": list(requirements.get("acceptance_criteria") or []),
        "decisions": [
            {
                "status": item.get("status"),
                "decision": item.get("decision"),
            }
            for item in requirements.get("clarified_decisions") or []
        ],
    }


def _assert_pending_present(questions, *needles):
    blob = _lower(questions)
    for needle in needles:
        assert needle in blob, (needle, questions)


def _assert_closed(questions, *needles):
    blob = _lower(questions)
    for needle in needles:
        assert needle not in blob, (needle, questions)


def test_field_inspection_assessment_views_share_reconciled_state():
    original_history = [dict(item) for item in HISTORY]
    state = _state(discovery=_stale_discovery(), requirements=_stale_requirements())

    resumed = apply_clarification_facts(state)
    provider = ScriptedProvider(
        discovery=_stale_discovery(),
        requirements=_stale_requirements(),
        validation={
            "status": "READY",
            "reasons": ["Ready for preliminary shaping."],
            "questions": [],
            "non_blocking_questions": list(STALE_UNKNOWN) + [
                "What conflict-resolution policy applies when two technicians edit the same offline record?",
                "How should conflicts be resolved when concurrent offline submissions update the same inspection?",
            ],
        },
    )
    discovery = discovery_agent({**state, **resumed}, provider)["discovery"]
    requirements = requirements_agent(
        {**state, **resumed, "discovery": discovery},
        provider,
    )["requirements"]
    validated = validation_agent(
        {**state, **resumed, "discovery": discovery, "requirements": requirements},
        provider,
    )

    solution = _ground_downstream_artifact(
        {
            "key_capabilities": ["Last-write-wins conflict handling"],
            "delivery_risks": ["Customer to decide who will use the first release"],
            "dependencies": [
                "Customer to decide: What are the specific requirements for offline behavior?",
                "Confirm the exact conflict-resolution workflow",
            ],
        },
        {**state, "discovery": validated["discovery"], "requirements": validated["requirements"]},
    )
    plan = _ground_downstream_artifact(
        {
            "delivery_phases": ["Build"],
            "dependencies": ["Customer to decide iOS versus Android"],
            "next_steps": ["Confirm hosting provider approval"],
        },
        {**state, **validated},
    )
    estimate = _ground_downstream_artifact(
        {
            "duration_range": "10-14 weeks",
            "baseline_duration_range": "10-14 weeks",
            "risks_affecting_estimate": ["Offline behavior is still undefined"],
        },
        {**state, **validated},
    )
    sow = _ground_downstream_artifact(
        {
            "in_scope": ["Mobile inspection app"],
            "out_of_scope": ["Analytics"],
            "deliverables": ["iOS and Android clients"],
            "dependencies": ["Customer to decide who will use the first release"],
        },
        {**state, **validated},
    )

    payload = workflow_response(
        {
            "user_request": REQUEST,
            "clarification_history": original_history,
            "discovery": validated["discovery"],
            "requirements": validated["requirements"],
            "validation": validated["validation"],
            "solution": solution,
            "delivery_plan": plan,
            "estimate": estimate,
            "delivery_review": {"status": "READY", "blocking_issues": []},
            "proposal": {"summary": "Inspection app"},
            "sow": sow,
            "workflow_status": "COMPLETE",
        },
        run_id="assessment-reconcile-e2e",
    )
    snapshot = _snapshot(payload)

    assert payload["user_request"] == REQUEST
    assert payload["clarification_history"] == original_history

    question_lists = (
        snapshot["unknowns"],
        snapshot["open_questions"],
        snapshot["non_blocking"],
        [
            item
            for item in snapshot["what_is_uncertain"]
            if item in snapshot["open_questions"] or any(
                questions_equivalent(item, question) for question in snapshot["open_questions"]
            )
        ],
    )
    assert snapshot["unknowns"] == snapshot["open_questions"] == snapshot["non_blocking"]
    canonical = snapshot["open_questions"]
    assert canonical
    blocking = []
    for item in payload.get("blocking_questions") or []:
        text = item["question"] if isinstance(item, dict) else str(item)
        if str(text).strip():
            blocking.append(text)
    expected_ask = []
    seen = set()
    for item in [*blocking, *canonical]:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        expected_ask.append(item)
        if len(expected_ask) >= ASK_NEXT_LIMIT:
            break
    assert snapshot["ask_next"] == expected_ask, (snapshot["ask_next"], expected_ask, blocking)
    for view in question_lists:
        _assert_closed(
            view,
            "who will use the first release",
            "specific requirements for offline behavior",
            "ios, android, or both",
            "proposed user volume been approved",
            "has the proposed user volume",
        )
        _assert_pending_present(view, "conflict")
        _assert_pending_present(view, "hosting")
        _assert_pending_present(view, "retention")
        _assert_pending_present(view, "volume")
        _assert_pending_present(view, "permission")
        _assert_pending_present(view, "interface")
        _assert_pending_present(view, "checklist")

    volume = [item for item in canonical if "volume" in item.lower() or "concurren" in item.lower()]
    assert volume, canonical
    assert all("approv" not in item.lower() for item in volume), volume
    assert all("proposed user volume" not in item.lower() for item in volume), volume
    assert any(
        "count" in item.lower() or "estimate" in item.lower() or "expected" in item.lower()
        for item in volume
    ), volume

    users_blob = _lower(snapshot["users"])
    assert "operations manager" not in users_blob
    assert "technician" in users_blob
    known = _lower(payload["assessment"]["what_we_know"])
    assert "users: operations manager" not in known

    functional = _lower(snapshot["functional"])
    acceptance = _lower(snapshot["acceptance"])
    assert "obtain estimates" not in functional
    assert "has not yet been established" not in functional
    assert "api access has been verified" not in functional
    assert "last-write-wins" not in functional
    assert "last-write-wins" not in acceptance
    assert "obtain estimates" not in acceptance
    assert "api access has been verified" not in acceptance
    assert "verified by demonstration or test that: obtain estimates" not in acceptance
    assert "offline" in functional or "queued" in functional
    assert "ios" in functional or "android" in functional

    decisions = snapshot["decisions"]
    assert decisions
    pending_text = _lower(
        item["decision"] for item in decisions if item["status"] == "PENDING"
    )
    resolved_text = _lower(
        item["decision"] for item in decisions if item["status"] == "RESOLVED"
    )
    assert "not yet been established" in pending_text
    assert "api access" in resolved_text and "verified" in resolved_text
    assert "conflict-resolution workflow" in pending_text
    status_items = [
        item for item in decisions
        if "status" in (item["decision"] or "").lower() and "offline" in (item["decision"] or "").lower()
    ]
    assert status_items
    assert all(item["status"] == "RESOLVED" for item in status_items), status_items

    assessment_text = (payload.get("assessment_text") or "").lower()
    print_text = (payload.get("print_assessment_text") or "").lower()
    for stale in (
        "who will use the first release",
        "specific requirements for offline behavior",
        "proposed user volume been approved",
    ):
        assert stale not in assessment_text
        assert stale not in print_text
    assert "conflict" in assessment_text
    assert "conflict" in print_text or "uncertain" in print_text

    grounded_blob = _lower(
        solution.get("delivery_risks", [])
        + solution.get("dependencies", [])
        + plan.get("dependencies", [])
        + estimate.get("risks_affecting_estimate", [])
        + sow.get("dependencies", [])
    )
    assert "who will use the first release" not in grounded_blob
    assert "ios versus android" not in grounded_blob
    assert "offline behavior is still undefined" not in grounded_blob
    assert "conflict-resolution" in _lower(solution.get("dependencies") or []) or any(
        "conflict" in item.lower() for item in canonical
    )

    assert validated["discovery"]["unknowns"] == validated["requirements"]["open_questions"]
    assert validated["validation"]["non_blocking_questions"] == validated["requirements"]["open_questions"]
    assert snapshot["history_len"] == len(HISTORY)
    assert ASK_NEXT_LIMIT == 5


def _question_items(items) -> list[str]:
    result = []
    for item in items or []:
        if isinstance(item, dict):
            text = str(item.get("question") or item.get("text") or "").strip()
        else:
            text = str(item or "").strip()
        if text:
            result.append(text)
    return result


def _all_ui_open_questions(payload: dict) -> list[str]:
    assessment = payload.get("assessment") or {}
    return (
        _question_items((payload.get("discovery") or {}).get("unknowns"))
        + _question_items((payload.get("requirements") or {}).get("open_questions"))
        + _question_items((payload.get("validation") or {}).get("non_blocking_questions"))
        + _question_items(payload.get("blocking_questions"))
        + _question_items(payload.get("non_blocking_questions"))
        + _question_items(payload.get("clarification_questions"))
        + _question_items(assessment.get("what_is_uncertain"))
        + _question_items(assessment.get("ask_next"))
    )


def _assert_authoritative_clarification_state(payload: dict):
    open_blob = _lower(_all_ui_open_questions(payload))
    assert "who will use the first release" not in open_blob
    assert "source of truth" not in open_blob
    assert "operations manager" in open_blob
    assert "permission matrix" in open_blob

    root_optional = _question_items(payload.get("non_blocking_questions"))
    _assert_closed(root_optional, "who will use the first release", "source of truth")
    for item in payload.get("non_blocking_questions") or []:
        assert isinstance(item, dict)
        assert item.get("status") == "OPEN", item
        assert item.get("priority") in {"RECOMMENDED", "OPTIONAL"}, item
        assert item.get("blocks_workflow") is False, item

    canonical = payload.get("clarification_state") or {}
    assert canonical.get("version") == 1
    answers_blob = _lower(item.get("answer") for item in canonical.get("answers") or [])
    assert "field technicians are the primary users" in answers_blob
    assert "salesforce asset registry api" in answers_blob

    decisions = canonical.get("decisions") or []
    resolved = _lower(
        item.get("decision")
        for item in decisions
        if item.get("status") == "RESOLVED"
    )
    pending = _lower(
        item.get("decision")
        for item in decisions
        if item.get("status") == "PENDING"
    )
    assert "field technicians are the primary users" in resolved
    assert "salesforce asset registry api" in resolved
    assert "operations manager" in pending
    assert "permission matrix" in pending

    question_state = {
        normalize_question_text(item.get("question")): item
        for item in canonical.get("questions") or []
        if isinstance(item, dict)
    }
    for question in (MANDATORY_USERS_QUESTION, MANDATORY_INTEGRATION_QUESTION):
        item = question_state[normalize_question_text(question)]
        assert item["status"] == "RESOLVED"
        assert item["priority"] == "REQUIRED"
        assert item["blocks_workflow"] is True
    for question in (PENDING_INTERFACE_QUESTION, PENDING_PERMISSION_QUESTION):
        matching = [
            item for text, item in question_state.items()
            if questions_equivalent(text, normalize_question_text(question))
            or normalize_question_text(question) in text
        ]
        assert matching, (question, question_state)
        assert all(item["status"] == "OPEN" for item in matching)
        assert all(item["blocks_workflow"] is False for item in matching)

    discovery_unknowns = _question_items((payload.get("discovery") or {}).get("unknowns"))
    requirement_open = _question_items((payload.get("requirements") or {}).get("open_questions"))
    validation_open = _question_items((payload.get("validation") or {}).get("non_blocking_questions"))
    assert discovery_unknowns == requirement_open == validation_open


def _fresh_clarify(client: TestClient, payload: dict, answer: str) -> dict:
    serialized = json.loads(json.dumps(payload))
    response = client.post(
        "/clarify",
        json={
            "user_request": PRODUCTION_SHAPED_REQUEST,
            "clarification_answers": [answer],
            "clarification_history": serialized.get("clarification_history") or [],
            "clarification_state": serialized.get("clarification_state") or {},
            "prior_state": serialized,
            "iteration": serialized.get("iteration") or 1,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_canonical_clarification_state_survives_serialized_regeneration_path(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("RAG_ENABLED", "false")
    provider = StaleRegenerationProvider()
    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_provider] = lambda: provider
    client = TestClient(app)
    try:
        first = client.post(
            "/analyze",
            json={"user_request": PRODUCTION_SHAPED_REQUEST},
        ).json()
        assert first["status"] == "NEEDS_INFO"
        blocking = _lower(_question_items(first.get("blocking_questions")))
        assert "who will use the first release" in blocking
        assert "source of truth" in blocking

        second = client.post(
            "/clarify",
            json={
                "user_request": PRODUCTION_SHAPED_REQUEST,
                "clarification_answers": list(MANDATORY_ANSWERS),
                "clarification_history": first.get("clarification_history") or [],
                "clarification_state": first.get("clarification_state") or {},
                "prior_state": json.loads(json.dumps(first)),
                "iteration": first.get("iteration") or 1,
            },
        ).json()
        assert second["execution"]["regenerate_upstream"] is True
        _assert_authoritative_clarification_state(second)

        third = _fresh_clarify(
            client,
            second,
            (
                f"{PENDING_INTERFACE_QUESTION}: The Operations Manager dedicated "
                "interface has not yet been decided."
            ),
        )
        _assert_authoritative_clarification_state(third)

        fourth = _fresh_clarify(
            client,
            third,
            (
                f"{PENDING_PERMISSION_QUESTION}: The exact permission matrix and "
                "report-correction workflow are not yet defined."
            ),
        )
        _assert_authoritative_clarification_state(fourth)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


def _ledger_stale_artifacts() -> dict:
    return {
        "discovery": {
            "problem": "Mobile inspection app",
            "business_goal": "Improve field inspection execution",
            "users": ["Field technicians", "Operations Manager"],
            "stakeholders": [],
            "existing_systems": ["Salesforce Asset Registry API"],
            "constraints": [],
            "assumptions": [],
            "unknowns": [
                MANDATORY_USERS_QUESTION,
                MANDATORY_INTEGRATION_QUESTION,
                PENDING_INTERFACE_QUESTION,
                PENDING_PERMISSION_QUESTION,
            ],
            "clarification_questions": [
                MANDATORY_USERS_QUESTION,
                MANDATORY_INTEGRATION_QUESTION,
            ],
        },
        "requirements": {
            "functional_requirements": [
                "The system should support field inspections on mobile devices."
            ],
            "non_functional_requirements": [],
            "acceptance_criteria": [
                "An authorized user can complete and submit an inspection."
            ],
            "open_questions": [
                MANDATORY_USERS_QUESTION,
                MANDATORY_INTEGRATION_QUESTION,
                PENDING_INTERFACE_QUESTION,
                PENDING_PERMISSION_QUESTION,
            ],
            "contradictions": [],
        },
        "validation": {
            "status": "READY",
            "reasons": ["Scripted stale payload"],
            "questions": [],
            "non_blocking_questions": [
                MANDATORY_USERS_QUESTION,
                MANDATORY_INTEGRATION_QUESTION,
                PENDING_INTERFACE_QUESTION,
                PENDING_PERMISSION_QUESTION,
            ],
        },
    }


def test_legacy_history_without_canonical_ledger_is_reconstructed():
    artifacts = _ledger_stale_artifacts()
    state = {
        "user_request": PRODUCTION_SHAPED_REQUEST,
        "clarification_history": [
            {
                "question": MANDATORY_USERS_QUESTION,
                "answer": MANDATORY_ANSWERS[0].split(": ", 1)[1],
            },
            {
                "question": MANDATORY_INTEGRATION_QUESTION,
                "answer": MANDATORY_ANSWERS[1].split(": ", 1)[1],
            },
        ],
        "discovery": artifacts["discovery"],
        "requirements": artifacts["requirements"],
        "validation": artifacts["validation"],
        "workflow_status": "COMPLETE",
    }
    payload = workflow_response(state, run_id="legacy-history-canonical-rebuild")
    _assert_authoritative_clarification_state(payload)


def test_partial_client_history_does_not_reopen_canonical_answers(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("RAG_ENABLED", "false")
    provider = StaleRegenerationProvider()
    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_provider] = lambda: provider
    client = TestClient(app)
    try:
        first = client.post(
            "/analyze",
            json={"user_request": PRODUCTION_SHAPED_REQUEST},
        ).json()
        second = client.post(
            "/clarify",
            json={
                "user_request": PRODUCTION_SHAPED_REQUEST,
                "clarification_answers": list(MANDATORY_ANSWERS),
                "clarification_history": first.get("clarification_history") or [],
                "clarification_state": first.get("clarification_state") or {},
                "prior_state": json.loads(json.dumps(first)),
                "iteration": first.get("iteration") or 1,
            },
        ).json()
        _assert_authoritative_clarification_state(second)
        serialized = json.loads(json.dumps(second))
        history = list(serialized.get("clarification_history") or [])
        partial_history = history[-1:] if history else []
        third = client.post(
            "/clarify",
            json={
                "user_request": PRODUCTION_SHAPED_REQUEST,
                "clarification_answers": [
                    (
                        f"{PENDING_INTERFACE_QUESTION}: The Operations Manager "
                        "dedicated interface has not yet been decided."
                    )
                ],
                "clarification_history": partial_history,
                "clarification_state": serialized.get("clarification_state") or {},
                "prior_state": serialized,
                "iteration": serialized.get("iteration") or 1,
            },
        ).json()
        _assert_authoritative_clarification_state(third)
        answers_blob = _lower(
            item.get("answer")
            for item in (third.get("clarification_state") or {}).get("answers") or []
        )
        assert "field technicians are the primary users" in answers_blob
        assert "salesforce asset registry api" in answers_blob
        restored_history = " ".join(
            str(item.get("answer") or "")
            for item in third.get("clarification_history") or []
        ).lower()
        assert "field technicians are the primary users" in restored_history
        assert "salesforce asset registry api" in restored_history
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
