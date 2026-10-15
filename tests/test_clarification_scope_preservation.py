"""Clarification answers supplement the original request; they do not replace it.

No live LLM. Two unrelated product domains: a library catalog and a lobby kiosk.
"""

import pytest

from app.agents import (
    _SCOPE_SUPPLEMENT_RULE,
    delivery_planning_agent,
    discovery_agent,
    estimation_agent,
    proposal_agent,
    requirements_agent,
    solution_shaping_agent,
    sow_agent,
    validation_agent,
)
from app.api import workflow_response
from app.evidence import apply_original_scope_consistency, original_scope_contradictions
from app.providers import AIProvider


LIBRARY = {
    "request": (
        "Build a public library catalog so members can search holdings and create holds. "
        "Do not send marketing email to members."
    ),
    "original_user": "Members",
    "added_user": "Librarians",
    "additive_answer": (
        "Librarians will also use the first release to check in returns."
    ),
    "ambiguous_answer": "Librarians will use it.",
    "withdrawal_answer": (
        "Members can no longer create holds; that work is out of scope and "
        "should be excluded from the first release."
    ),
    "prior_requirement": "Members can create holds.",
    "original_system": "Library catalog database",
    "added_system": "Interlibrary loan service",
    "third_system": "Patron identity directory",
    "lost_oos_item": "Members searching holdings",
    "outcome_fragment": "search holdings",
    "prohibition_capability": "Send marketing email to members.",
}

KIOSK = {
    "request": (
        "Build a lobby kiosk so receptionists can search visitor appointments "
        "and create check-in records. Do not store visitor payment card numbers."
    ),
    "original_user": "Receptionists",
    "added_user": "Security officers",
    "additive_answer": (
        "Security officers will also use the first release to review today's check-ins."
    ),
    "ambiguous_answer": "Security officers will use it.",
    "withdrawal_answer": (
        "Receptionists can no longer create check-in records; that work is "
        "out of scope and should be excluded from the first release."
    ),
    "prior_requirement": "Receptionists can create check-in records.",
    "original_system": "Visitor appointment register",
    "added_system": "Staff messaging bus",
    "third_system": "Building access panel",
    "lost_oos_item": "Receptionists searching visitor appointments",
    "outcome_fragment": "search visitor",
    "prohibition_capability": "Store visitor payment card numbers.",
}

DOMAINS = pytest.mark.parametrize("domain", [LIBRARY, KIOSK], ids=["library", "kiosk"])


class RecordingProvider(AIProvider):
    def __init__(self, payload=None):
        self.payload = dict(payload or {})
        self.prompts = []

    def generate_json(self, prompt, schema):
        self.prompts.append(str(prompt or ""))
        return dict(self.payload)


def _history(domain, answer):
    return [
        {
            "question": "Who will use the first release, and what will they do in it?",
            "answer": answer,
        }
    ]


def _discovery(users, **overrides):
    payload = {
        "problem": "Operational need",
        "business_goal": "Faster operations",
        "users": list(users),
        "stakeholders": [],
        "existing_systems": [],
        "constraints": [],
        "assumptions": [],
        "unknowns": [],
        "clarification_questions": [],
    }
    payload.update(overrides)
    return payload


def _requirements(functional=None, **overrides):
    payload = {
        "functional_requirements": list(functional or []),
        "non_functional_requirements": [],
        "acceptance_criteria": [],
        "open_questions": [],
        "contradictions": [],
    }
    payload.update(overrides)
    return payload


def _drifted_payload(domain):
    return {
        "user_request": domain["request"],
        "clarification_history": _history(domain, domain["additive_answer"]),
        "clarification_state": {
            "version": 1,
            "answers": [
                {
                    "question": "Who will use the first release, and what will they do in it?",
                    "answer": domain["additive_answer"],
                    "status": "ACCEPTED",
                }
            ],
            "questions": [
                {
                    "question": "Who will use the first release, and what will they do in it?",
                    "status": "RESOLVED",
                    "priority": "REQUIRED",
                    "blocks_workflow": True,
                }
            ],
            "decisions": [
                {
                    "question": "Who will use the first release, and what will they do in it?",
                    "decision": domain["additive_answer"],
                    "status": "RESOLVED",
                }
            ],
        },
        "discovery": _discovery([domain["added_user"]]),
        "requirements": _requirements(
            [f"{domain['added_user']} can review incoming work."]
        ),
        "validation": {
            "status": "READY",
            "reasons": ["Ready for preliminary shaping."],
            "questions": [],
            "non_blocking_questions": [],
        },
        "solution": {
            "solution_summary": f"A product for {domain['added_user']}.",
            "key_capabilities": [f"{domain['added_user']} can review incoming work."],
            "integration_approach": [],
        },
        "delivery_plan": {"delivery_phases": [f"Build for {domain['added_user']}"]},
        "estimate": {"duration_range": "4-6 weeks", "assumptions": ["Scope is the added role only"]},
        "proposal": {
            "executive_summary": f"A product for {domain['added_user']}.",
            "scope": [f"{domain['added_user']} review work"],
        },
        "sow": {
            "objectives": [f"Serve {domain['added_user']}"],
            "deliverables": [f"{domain['added_user']} increment"],
            "in_scope": [f"{domain['added_user']} review work"],
            "out_of_scope": [domain["lost_oos_item"]],
            "acceptance": [f"{domain['added_user']} can review incoming work"],
        },
        "workflow_status": "COMPLETE",
        "delivery_review": {"status": "READY", "blocking_issues": []},
    }


@DOMAINS
def test_additive_answer_keeps_original_audience(domain):
    state = {
        "user_request": domain["request"],
        "clarification_history": _history(domain, domain["additive_answer"]),
        "discovery": _discovery([domain["original_user"]]),
    }
    discovery = discovery_agent(
        state,
        RecordingProvider(_discovery([domain["added_user"]])),
    )["discovery"]
    users = " ".join(str(item).lower() for item in discovery["users"])
    assert domain["original_user"].lower() in users
    assert domain["added_user"].lower() in users


@DOMAINS
def test_original_requirement_loss_is_not_silent(domain):
    payload = workflow_response(_drifted_payload(domain), run_id="scope-loss")
    contradictions = " ".join(
        str(item).lower()
        for item in (payload.get("requirements") or {}).get("contradictions") or []
    )
    assert domain["outcome_fragment"] in contradictions
    out_of_scope = " ".join(
        str(item).lower() for item in (payload.get("sow") or {}).get("out_of_scope") or []
    )
    assert domain["original_user"].lower() not in out_of_scope
    assert payload["user_request"] == domain["request"]
    ledger = payload.get("clarification_state") or {}
    assert ledger.get("answers")
    assert any(
        str(item.get("status") or "").upper() == "RESOLVED"
        for item in ledger.get("questions") or []
    )


@DOMAINS
def test_explicit_withdrawal_drops_prior_requirement(domain):
    state = {
        "user_request": domain["request"],
        "clarification_history": _history(domain, domain["withdrawal_answer"]),
        "requirements": _requirements([domain["prior_requirement"]]),
        "discovery": _discovery([domain["original_user"]]),
    }
    requirements = requirements_agent(
        state,
        RecordingProvider(
            _requirements([f"{domain['added_user']} can review incoming work."])
        ),
    )["requirements"]
    blob = " ".join(
        str(item).lower()
        for item in requirements.get("functional_requirements") or []
    )
    assert domain["prior_requirement"].lower() not in blob
    withdrawn = domain["prior_requirement"].lower()
    findings = original_scope_contradictions(
        {**state, "requirements": requirements}
    )
    assert not any(withdrawn in item.lower() for item in findings)


@DOMAINS
def test_ambiguous_answer_does_not_withdraw_original_scope(domain):
    state = {
        "user_request": domain["request"],
        "clarification_history": _history(domain, domain["ambiguous_answer"]),
        "discovery": _discovery([domain["original_user"]]),
        "requirements": _requirements([domain["prior_requirement"]]),
    }
    discovery = discovery_agent(
        state,
        RecordingProvider(_discovery([domain["added_user"]])),
    )["discovery"]
    requirements = requirements_agent(
        {**state, "discovery": discovery},
        RecordingProvider(
            _requirements([f"{domain['added_user']} can review incoming work."])
        ),
    )["requirements"]
    users = " ".join(str(item).lower() for item in discovery["users"])
    assert domain["original_user"].lower() in users
    blob = " ".join(
        str(item).lower()
        for item in requirements.get("functional_requirements") or []
    )
    assert domain["prior_requirement"].lower() in blob


@DOMAINS
def test_prohibition_is_not_a_positive_capability(domain):
    state = _drifted_payload(domain)
    state["solution"]["key_capabilities"] = [domain["prohibition_capability"]]
    state["requirements"]["functional_requirements"] = [
        domain["prohibition_capability"]
    ]
    updates = apply_original_scope_consistency(state)
    caps = " ".join(
        str(item).lower()
        for item in (updates.get("solution") or {}).get("key_capabilities") or []
    )
    frs = " ".join(
        str(item).lower()
        for item in (updates.get("requirements") or {}).get("functional_requirements") or []
    )
    assert domain["prohibition_capability"].lower() not in caps
    assert domain["prohibition_capability"].lower() not in frs


def test_downstream_prompts_include_original_request_and_supplement_rule():
    request = LIBRARY["request"]
    state = {
        "user_request": request,
        "clarification_history": _history(LIBRARY, LIBRARY["additive_answer"]),
        "discovery": _discovery(["Members", "Librarians"]),
        "requirements": _requirements(["Members can search holdings."]),
        "solution": {
            "solution_summary": "Library catalog",
            "key_capabilities": ["Members can search holdings."],
            "integration_approach": [],
            "assumptions": [],
        },
        "delivery_plan": {"delivery_phases": ["Build"]},
        "estimate": {
            "duration_range": "4-6 weeks",
            "standard_deadline_fit": "NOT_DEMONSTRATED",
            "assumptions": [],
        },
    }
    for agent, extra in (
        (validation_agent, {}),
        (solution_shaping_agent, {}),
        (delivery_planning_agent, {}),
        (proposal_agent, {}),
        (sow_agent, {}),
    ):
        provider = RecordingProvider(
            {
                "status": "READY",
                "reasons": ["Ready"],
                "questions": [],
                "non_blocking_questions": [],
                "solution_summary": "Library catalog",
                "key_capabilities": ["Members can search holdings."],
                "integration_approach": [],
                "assumptions": [],
                "delivery_phases": ["Build"],
                "executive_summary": "Catalog",
                "scope": ["Search holdings"],
                "objectives": ["Catalog"],
                "deliverables": ["Increment"],
                "in_scope": ["Search holdings"],
                "out_of_scope": [],
                "acceptance": ["Members can search holdings"],
            }
        )
        agent({**state, **extra}, provider)
        assert provider.prompts
        combined = "\n".join(provider.prompts)
        assert request in combined
        assert "supplement" in combined.lower()

    estimate_provider = RecordingProvider(
        {
            "effort_range": "20-30 person-days",
            "duration_range": "4-6 weeks",
            "confidence": "MEDIUM",
            "assumptions": [],
            "risks_affecting_estimate": [],
        }
    )
    estimation_agent(state, estimate_provider)
    if estimate_provider.prompts:
        combined = "\n".join(estimate_provider.prompts)
        assert request in combined
        assert _SCOPE_SUPPLEMENT_RULE.split(".")[0] in combined


def _blob(*parts) -> str:
    texts = []
    for part in parts:
        if isinstance(part, dict):
            texts.extend(str(value) for value in part.values())
        elif isinstance(part, list):
            texts.extend(str(item) for item in part)
        else:
            texts.append(str(part or ""))
    return " ".join(texts).lower()


def _complete(state: dict) -> dict:
    payload = dict(state)
    payload.setdefault(
        "validation",
        {
            "status": "READY",
            "reasons": ["Ready for preliminary shaping."],
            "questions": [],
            "non_blocking_questions": [],
        },
    )
    payload.setdefault("workflow_status", "COMPLETE")
    payload.setdefault("delivery_review", {"status": "READY", "blocking_issues": []})
    return workflow_response(payload, run_id="scope-e2e")


def _active_blob(payload: dict) -> str:
    return _blob(
        (payload.get("discovery") or {}).get("users"),
        (payload.get("requirements") or {}).get("functional_requirements"),
        (payload.get("solution") or {}).get("solution_summary"),
        (payload.get("solution") or {}).get("key_capabilities"),
        (payload.get("sow") or {}).get("in_scope"),
        (payload.get("sow") or {}).get("objectives"),
        (payload.get("proposal") or {}).get("scope"),
    )


@DOMAINS
def test_workflow_detects_first_discovery_omission(domain):
    payload = _complete(
        {
            "user_request": domain["request"],
            "discovery": _discovery(["Unrelated operators"]),
            "requirements": _requirements(["Unrelated operators can file tickets."]),
            "solution": {
                "solution_summary": "A ticket console for operators.",
                "key_capabilities": ["Unrelated operators can file tickets."],
                "integration_approach": [],
            },
            "sow": {
                "objectives": ["Ticket console"],
                "deliverables": ["Increment"],
                "in_scope": ["Operator ticket filing"],
                "out_of_scope": [],
                "acceptance": ["Operators can file tickets"],
            },
        }
    )
    contradictions = " ".join(
        str(item).lower()
        for item in (payload.get("requirements") or {}).get("contradictions") or []
    )
    assert domain["outcome_fragment"] in contradictions
    users = " ".join(
        str(item).lower() for item in (payload.get("discovery") or {}).get("users") or []
    )
    assert domain["original_user"].lower() not in users


def test_unparsed_original_verb_is_a_detection_blind_spot():
    payload = _complete(
        {
            "user_request": (
                "Build a warehouse handheld so pickers complete picks and capture "
                "bin photos."
            ),
            "discovery": _discovery(["Dispatchers"]),
            "requirements": _requirements(["Dispatchers can assign jobs."]),
            "solution": {
                "solution_summary": "A dispatcher console.",
                "key_capabilities": ["Dispatchers can assign jobs."],
                "integration_approach": [],
            },
            "sow": {
                "objectives": ["Dispatch jobs"],
                "deliverables": ["Increment"],
                "in_scope": ["Job assignment"],
                "out_of_scope": [],
                "acceptance": [],
            },
        }
    )
    contradictions = " ".join(
        str(item).lower()
        for item in (payload.get("requirements") or {}).get("contradictions") or []
    )
    assert "complete" not in contradictions
    assert "capture" not in contradictions
    assert "photo" not in contradictions


@DOMAINS
def test_additive_clarification_final_artifacts_keep_original_audience(domain):
    prior = {
        "user_request": domain["request"],
        "clarification_history": _history(domain, domain["additive_answer"]),
        "discovery": _discovery(
            [domain["original_user"]],
            existing_systems=[
                domain["original_system"],
                domain["third_system"],
            ],
        ),
        "requirements": _requirements([domain["prior_requirement"]]),
    }
    discovery = discovery_agent(
        prior,
        RecordingProvider(
            _discovery(
                [domain["added_user"]],
                existing_systems=[domain["added_system"]],
            )
        ),
    )["discovery"]
    requirements = requirements_agent(
        {**prior, "discovery": discovery},
        RecordingProvider(
            _requirements([f"{domain['added_user']} can review incoming work."])
        ),
    )["requirements"]
    solution = solution_shaping_agent(
        {**prior, "discovery": discovery, "requirements": requirements},
        RecordingProvider(
            {
                "solution_summary": f"A product for {domain['added_user']}.",
                "key_capabilities": [f"{domain['added_user']} can review incoming work."],
                "integration_approach": [f"Integrate with {domain['added_system']}."],
                "technical_considerations": [],
                "delivery_risks": [],
                "dependencies": [],
                "assumptions": [],
            }
        ),
    )["solution"]
    sow = sow_agent(
        {
            **prior,
            "discovery": discovery,
            "requirements": requirements,
            "solution": solution,
            "delivery_plan": {"delivery_phases": ["Build"]},
            "estimate": {
                "duration_range": "4-6 weeks",
                "standard_deadline_fit": "NOT_DEMONSTRATED",
                "assumptions": [],
            },
        },
        RecordingProvider(
            {
                "objectives": [f"Serve {domain['added_user']}"],
                "deliverables": ["Increment"],
                "in_scope": [f"{domain['added_user']} review work"],
                "out_of_scope": [domain["lost_oos_item"]],
                "dependencies": [],
                "acceptance": [f"{domain['added_user']} can review incoming work"],
                "timeline": "See estimate",
                "assumptions": [],
            }
        ),
    )["sow"]
    payload = _complete(
        {
            **prior,
            "discovery": discovery,
            "requirements": requirements,
            "solution": solution,
            "sow": sow,
        }
    )
    users = " ".join(
        str(item).lower() for item in (payload.get("discovery") or {}).get("users") or []
    )
    assert domain["original_user"].lower() in users
    assert domain["added_user"].lower() in users
    out_of_scope = " ".join(
        str(item).lower() for item in (payload.get("sow") or {}).get("out_of_scope") or []
    )
    assert domain["original_user"].lower() not in out_of_scope
    frs = " ".join(
        str(item).lower()
        for item in (payload.get("requirements") or {}).get("functional_requirements") or []
    )
    assert domain["prior_requirement"].lower() in frs
    solution_caps = " ".join(
        str(item).lower()
        for item in (payload.get("solution") or {}).get("key_capabilities") or []
    )
    sow_in = " ".join(
        str(item).lower()
        for item in (payload.get("sow") or {}).get("in_scope") or []
    )
    integrations = " ".join(
        str(item).lower()
        for item in (payload.get("solution") or {}).get("integration_approach") or []
    )
    assert domain["original_user"].lower() in solution_caps
    assert domain["added_user"].lower() in solution_caps
    assert domain["prior_requirement"].lower() in solution_caps
    assert domain["original_user"].lower() in sow_in
    assert domain["added_user"].lower() in sow_in
    assert domain["prior_requirement"].lower() in sow_in
    assert domain["original_system"].lower() in integrations
    assert domain["added_system"].lower() in integrations
    assert domain["third_system"].lower() in integrations


@DOMAINS
def test_sow_prompt_distinguishes_field_roles(domain):
    provider = RecordingProvider(
        {
            "objectives": [f"Serve {domain['added_user']}"],
            "deliverables": ["Increment"],
            "in_scope": [f"{domain['added_user']} review work"],
            "out_of_scope": [],
            "dependencies": [],
            "acceptance": [f"{domain['added_user']} can review incoming work"],
            "timeline": "See estimate",
            "assumptions": [],
        }
    )
    sow_agent(
        {
            "user_request": domain["request"],
            "discovery": _discovery([domain["original_user"], domain["added_user"]]),
            "requirements": _requirements([domain["prior_requirement"]]),
            "solution": {
                "solution_summary": f"A product for {domain['added_user']}.",
                "key_capabilities": [domain["prior_requirement"]],
                "integration_approach": [],
            },
            "delivery_plan": {"delivery_phases": ["Build"]},
            "estimate": {
                "duration_range": "4-6 weeks",
                "standard_deadline_fit": "NOT_DEMONSTRATED",
                "assumptions": [],
            },
        },
        provider,
    )
    prompt = " ".join(provider.prompts).lower()
    assert "business outcomes" in prompt
    assert "work products produced" in prompt
    assert "do not paste the functional-requirements list" in prompt
    assert "testable evidence" in prompt
    assert "unconfirmed planning facts" in prompt
    assert "external inputs, access, or participation required" in prompt
    assert "do not repeat the same capability across every field" in prompt


@DOMAINS
def test_workflow_response_carries_established_scope_into_drifted_downstream(domain):
    payload = _complete(
        {
            "user_request": domain["request"],
            "clarification_history": _history(domain, domain["additive_answer"]),
            "discovery": _discovery(
                [domain["original_user"], domain["added_user"]],
                existing_systems=[
                    domain["original_system"],
                    domain["added_system"],
                    domain["third_system"],
                ],
            ),
            "requirements": _requirements(
                [
                    domain["prior_requirement"],
                    f"{domain['added_user']} can review incoming work.",
                    f"Integrate with {domain['original_system']}.",
                    f"Integrate with {domain['added_system']}.",
                    f"Integrate with {domain['third_system']}.",
                ]
            ),
            "solution": {
                "solution_summary": f"A product for {domain['added_user']}.",
                "key_capabilities": [f"{domain['added_user']} can review incoming work."],
                "integration_approach": [f"Integrate with {domain['added_system']}."],
            },
            "sow": {
                "objectives": [f"Serve {domain['added_user']}"],
                "deliverables": ["Increment"],
                "in_scope": [f"{domain['added_user']} review work"],
                "out_of_scope": [domain["lost_oos_item"]],
                "acceptance": [],
            },
        }
    )
    caps = " ".join(
        str(item).lower()
        for item in (payload.get("solution") or {}).get("key_capabilities") or []
    )
    sow_in = " ".join(
        str(item).lower()
        for item in (payload.get("sow") or {}).get("in_scope") or []
    )
    integrations = " ".join(
        str(item).lower()
        for item in (payload.get("solution") or {}).get("integration_approach") or []
    )
    assert domain["original_user"].lower() in caps
    assert domain["added_user"].lower() in caps
    assert domain["prior_requirement"].lower() in caps
    assert domain["original_user"].lower() in sow_in
    assert domain["added_user"].lower() in sow_in
    assert domain["prior_requirement"].lower() in sow_in
    assert domain["original_system"].lower() in integrations
    assert domain["added_system"].lower() in integrations
    assert domain["third_system"].lower() in integrations
    out_of_scope = " ".join(
        str(item).lower()
        for item in (payload.get("sow") or {}).get("out_of_scope") or []
    )
    assert domain["original_user"].lower() not in out_of_scope


@DOMAINS
def test_workflow_response_does_not_dump_cross_field_scope(domain):
    nfr = "The service must encrypt stored records at rest."
    sourced_ac = (
        "Verified by demonstration or test that: "
        f"{domain['added_user']} can review incoming work "
        "(Source: customer clarification)"
    )
    payload = _complete(
        {
            "user_request": domain["request"],
            "clarification_history": _history(domain, domain["additive_answer"]),
            "discovery": _discovery(
                [domain["original_user"], domain["added_user"]],
                existing_systems=[
                    domain["original_system"],
                    domain["added_system"],
                    domain["third_system"],
                ],
            ),
            "requirements": _requirements(
                [
                    domain["prior_requirement"],
                    f"{domain['added_user']} can review incoming work.",
                    f"Integrate with {domain['original_system']}.",
                    f"Integrate with {domain['added_system']}.",
                    f"Integrate with {domain['third_system']}.",
                ],
                non_functional_requirements=[nfr],
                acceptance_criteria=[
                    sourced_ac,
                    f"A {domain['original_user'].lower()} can complete the original task.",
                ],
            ),
            "solution": {
                "solution_summary": f"A product for {domain['added_user']}.",
                "key_capabilities": [f"{domain['added_user']} can review incoming work."],
                "integration_approach": [f"Integrate with {domain['added_system']}."],
            },
            "sow": {
                "objectives": [f"Serve {domain['added_user']}"],
                "deliverables": ["Increment"],
                "in_scope": [f"{domain['added_user']} review work"],
                "out_of_scope": [domain["lost_oos_item"]],
                "acceptance": [],
            },
        }
    )
    caps = [
        str(item).strip()
        for item in (payload.get("solution") or {}).get("key_capabilities") or []
    ]
    sow_in = list((payload.get("sow") or {}).get("in_scope") or [])
    sow_acceptance = list((payload.get("sow") or {}).get("acceptance") or [])
    sow_objectives = list((payload.get("sow") or {}).get("objectives") or [])
    assert sow_in != sow_acceptance
    assert sow_in != sow_objectives
    assert domain["original_user"] not in caps
    assert domain["added_user"] not in caps
    assert nfr not in caps
    assert not any("verified by demonstration" in item.lower() for item in caps)
    sow_in_blob = " ".join(str(item).lower() for item in sow_in)
    assert domain["prior_requirement"].lower() in sow_in_blob
    assert domain["added_user"].lower() in sow_in_blob
    scope_blob = _blob(
        (payload.get("requirements") or {}).get("functional_requirements"),
        sow_in,
        (payload.get("solution") or {}).get("integration_approach"),
    )
    assert domain["original_system"].lower() in scope_blob
    assert domain["added_system"].lower() in scope_blob
    assert domain["third_system"].lower() in scope_blob
    sow_acceptance_blob = " ".join(str(item).lower() for item in sow_acceptance)
    assert "verified by demonstration" not in sow_acceptance_blob
    assert domain["added_user"].lower() in _blob(
        (payload.get("requirements") or {}).get("functional_requirements")
    )


@DOMAINS
def test_workflow_response_collapses_modal_paraphrases_and_keeps_distinct_scope(domain):
    must = (
        f"The system must allow {domain['original_user'].lower()} to "
        f"{domain['outcome_fragment']}."
    )
    shall = (
        f"The system shall allow {domain['original_user'].lower()} to "
        f"{domain['outcome_fragment']}."
    )
    om = f"{domain['added_user']} can review incoming work."
    offline = (
        f"{domain['original_user']} can continue work with no network connection."
    )
    sync = (
        "Queued updates persist locally and synchronize when connectivity returns."
    )
    duplicate = "The system must prevent duplicate submissions."
    conflict = "The system must provide a way to resolve synchronization conflicts."
    integrations = [
        f"Integrate with {domain['original_system']}.",
        f"Integrate with {domain['added_system']}.",
        f"Integrate with {domain['third_system']}.",
    ]
    verified = (
        "Verified by demonstration or test that: "
        f"{domain['original_user']} can {domain['outcome_fragment']} "
        "(Source: customer clarification)"
    )
    payload = _complete(
        {
            "user_request": domain["request"],
            "clarification_history": _history(domain, domain["additive_answer"]),
            "discovery": _discovery(
                [domain["original_user"], domain["added_user"]],
                existing_systems=[
                    domain["original_system"],
                    domain["added_system"],
                    domain["third_system"],
                ],
            ),
            "requirements": _requirements(
                [must, shall, om, offline, sync, duplicate, conflict, *integrations]
            ),
            "solution": {
                "solution_summary": f"A product for {domain['added_user']}.",
                "key_capabilities": [must, shall, om],
                "integration_approach": list(integrations),
            },
            "proposal": {
                "executive_summary": f"A product for {domain['added_user']}.",
                "scope": [must, shall, f"View {domain['outcome_fragment']}"],
            },
            "sow": {
                "objectives": [f"Serve {domain['original_user']} with faster operations."],
                "deliverables": ["Increment"],
                "in_scope": [must, shall, om],
                "out_of_scope": [],
                "acceptance": [
                    verified,
                    f"A {domain['original_user'].lower()} can {domain['outcome_fragment']}.",
                ],
            },
        }
    )
    frs = list(
        (payload.get("requirements") or {}).get("functional_requirements") or []
    )
    proposal_scope = list((payload.get("proposal") or {}).get("scope") or [])
    sow_in = list((payload.get("sow") or {}).get("in_scope") or [])
    sow_acceptance = list((payload.get("sow") or {}).get("acceptance") or [])
    sow_objectives = list((payload.get("sow") or {}).get("objectives") or [])

    def _modal_count(items):
        return sum(
            1
            for item in items
            if domain["outcome_fragment"] in str(item).lower()
            and "network" not in str(item).lower()
            and (
                "must allow" in str(item).lower()
                or "shall allow" in str(item).lower()
            )
        )

    assert _modal_count(frs) == 1
    assert _modal_count(proposal_scope) <= 1
    assert _modal_count(sow_in) <= 1
    blob = _blob(frs, proposal_scope, sow_in)
    assert domain["outcome_fragment"] in blob
    assert domain["added_user"].lower() in blob
    assert "no network" in blob
    assert "synchronize" in blob or "connectivity" in blob
    assert "duplicate" in blob
    assert "conflict" in blob
    assert domain["original_system"].lower() in blob
    assert domain["added_system"].lower() in blob
    assert domain["third_system"].lower() in blob
    assert "verified by demonstration" not in " ".join(
        str(item).lower() for item in sow_acceptance
    )
    assert domain["outcome_fragment"] in _blob(frs)
    assert "must allow" not in " ".join(str(item).lower() for item in sow_objectives)
    assert domain["prior_requirement"].lower() not in " ".join(
        str(item).lower() for item in sow_objectives
    )


def test_explicit_replacement_drops_withdrawn_product_from_active_scope():
    request = (
        "Build a mobile application so inspectors can search assigned sites "
        "and create inspection reports."
    )
    answer = (
        "Replace the mobile app with a web portal; the mobile app is no longer "
        "in scope."
    )
    prior = {
        "user_request": request,
        "clarification_history": [
            {
                "question": "Should the first release be a mobile app or a web portal?",
                "answer": answer,
            }
        ],
        "discovery": _discovery(["Inspectors"]),
        "requirements": _requirements(
            [
                "Inspectors can search assigned sites.",
                "Inspectors can create inspection reports.",
            ]
        ),
        "solution": {
            "solution_summary": "A mobile application for inspectors.",
            "key_capabilities": [
                "Mobile application checklists",
                "Create inspection reports on a mobile app",
            ],
            "integration_approach": [],
            "assumptions": [],
        },
        "sow": {
            "objectives": ["Mobile application for inspectors"],
            "deliverables": ["Increment"],
            "in_scope": ["Mobile application for inspectors", "Search assigned sites"],
            "out_of_scope": [],
            "acceptance": [],
            "assumptions": [],
        },
    }
    discovery = discovery_agent(
        prior, RecordingProvider(_discovery(["Office coordinators"]))
    )["discovery"]
    requirements = requirements_agent(
        {**prior, "discovery": discovery},
        RecordingProvider(
            _requirements(["Office coordinators can review work on a web portal."])
        ),
    )["requirements"]
    solution = solution_shaping_agent(
        {**prior, "discovery": discovery, "requirements": requirements},
        RecordingProvider(
            {
                "solution_summary": "A web portal for office coordinators.",
                "key_capabilities": ["Web portal work review"],
                "integration_approach": [],
                "technical_considerations": [],
                "delivery_risks": [],
                "dependencies": [],
                "assumptions": [],
            }
        ),
    )["solution"]
    sow = sow_agent(
        {
            **prior,
            "discovery": discovery,
            "requirements": requirements,
            "solution": solution,
            "delivery_plan": {"delivery_phases": ["Build"]},
            "estimate": {
                "duration_range": "4-6 weeks",
                "standard_deadline_fit": "NOT_DEMONSTRATED",
                "assumptions": [],
            },
        },
        RecordingProvider(
            {
                "objectives": ["Web portal"],
                "deliverables": ["Increment"],
                "in_scope": ["Web portal for office coordinators"],
                "out_of_scope": ["The mobile app"],
                "dependencies": [],
                "acceptance": ["A coordinator can review work"],
                "timeline": "See estimate",
                "assumptions": [],
            }
        ),
    )["sow"]
    payload = _complete(
        {
            **prior,
            "discovery": discovery,
            "requirements": requirements,
            "solution": solution,
            "sow": sow,
            "proposal": {
                "executive_summary": "Web portal",
                "scope": ["Web portal for office coordinators"],
            },
        }
    )
    active = _active_blob(payload)
    assert "web portal" in active
    assert "mobile app" not in active
    assert "mobile application" not in active
    out_of_scope = _blob((payload.get("sow") or {}).get("out_of_scope"))
    assert "mobile app" in out_of_scope
    users = " ".join(
        str(item).lower() for item in (payload.get("discovery") or {}).get("users") or []
    )
    assert "inspector" in users
    frs = _blob((payload.get("requirements") or {}).get("functional_requirements"))
    assert "no longer in scope" not in frs


def test_explicit_replacement_second_domain_drops_withdrawn_kiosk():
    request = (
        "Build a lobby kiosk so receptionists can search visitor appointments "
        "and create check-in records."
    )
    answer = (
        "Replace the kiosk with a staff web portal; the kiosk is no longer in scope."
    )
    payload = _complete(
        {
            "user_request": request,
            "clarification_history": [
                {"question": "Should the first release stay on the kiosk?", "answer": answer}
            ],
            "discovery": _discovery(["Receptionists", "Clerks"]),
            "requirements": _requirements(
                [
                    "Receptionists can search visitor appointments.",
                    "The lobby kiosk prints visitor badges.",
                ]
            ),
            "solution": {
                "solution_summary": "A staff web portal.",
                "key_capabilities": [
                    "Lobby kiosk badge printing",
                    "Staff web portal check-in",
                ],
                "integration_approach": [],
            },
            "sow": {
                "objectives": ["Staff web portal"],
                "deliverables": ["Increment"],
                "in_scope": ["Lobby kiosk badge printing", "Staff web portal check-in"],
                "out_of_scope": [],
                "acceptance": [],
            },
        }
    )
    active = _active_blob(payload)
    assert "web portal" in active
    assert "lobby kiosk" not in active
    assert "kiosk badge" not in active


@DOMAINS
def test_prohibition_is_removed_from_final_in_scope_artifacts(domain):
    payload = _complete(
        {
            "user_request": domain["request"],
            "discovery": _discovery([domain["original_user"]]),
            "requirements": _requirements(
                [
                    domain["prior_requirement"],
                    domain["prohibition_capability"],
                ]
            ),
            "solution": {
                "solution_summary": f"A product for {domain['original_user']}.",
                "key_capabilities": [
                    domain["prior_requirement"],
                    domain["prohibition_capability"],
                ],
                "integration_approach": [],
            },
            "sow": {
                "objectives": [domain["prior_requirement"]],
                "deliverables": ["Increment"],
                "in_scope": [domain["prior_requirement"], domain["prohibition_capability"]],
                "out_of_scope": [],
                "acceptance": [domain["prior_requirement"]],
            },
        }
    )
    active = _active_blob(payload)
    assert domain["prohibition_capability"].lower() not in active
    assert domain["original_user"].lower() in _blob(
        (payload.get("discovery") or {}).get("users")
    )
