import re

from app.agents import (
    _deterministic_delivery_gate,
    _extract_explicit_timeline_facts,
    _ground_requirements_to_discovery,
    _rewrite_commitment_overclaim,
    delivery_review_agent,
    discovery_agent,
    proposal_agent,
    sow_agent,
)
from app.api import workflow_response
from app.assessment import canonical_fit_comparison, sanitize_comparison_wording
from app.timeline import (
    COMMITMENT_ASPIRATIONAL,
    COMMITMENT_CONTRACTUAL,
    COMMITMENT_INTERNAL_TARGET,
    COMMITMENT_UNSPECIFIED,
    classify_date_commitment,
    sanitize_timeline_constraints,
)
from tests.test_phase0 import ScriptedProvider, _estimate_state


INTERNAL_TARGET_REQUEST = (
    "Build a catalog so members can search holdings. "
    "The first release is an internal target of 8 weeks, not a contractual deadline."
)
CONTRACTUAL_REQUEST = (
    "Build a catalog so members can search holdings. "
    "The first release is a contractual deadline of 8 weeks with penalties for missing it."
)
ASPIRATIONAL_REQUEST = (
    "Build a catalog so members can search holdings. "
    "Go live in 8 weeks if possible; this is an aspirational stretch goal."
)
UNSPECIFIED_REQUEST = (
    "Build a catalog so members can search holdings. "
    "The first production release is in 8 weeks."
)
TWELVE_WEEK_INTERNAL_REQUEST = (
    "Build a catalog so members can search holdings. "
    "We want to launch in approximately 12 weeks. This is a target, "
    "not an approved delivery commitment."
)


def _review_state(request: str, duration: str, constraints=None):
    facts = _extract_explicit_timeline_facts(request)
    state = _estimate_state(constraints if constraints is not None else facts, duration)
    state["user_request"] = request
    state["estimate"] = {
        "effort_range": "40-80 person-days",
        "duration_range": duration,
        "confidence": "MEDIUM",
        "assumptions": [],
        "risks_affecting_estimate": [],
        "standard_deadline_fit": "EXCEEDS" if "12" in duration else "FITS",
    }
    return state


def test_explicit_internal_target_is_not_a_binding_deadline():
    assert classify_date_commitment([INTERNAL_TARGET_REQUEST]) == COMMITMENT_INTERNAL_TARGET
    facts = _extract_explicit_timeline_facts(INTERNAL_TARGET_REQUEST)
    joined = " ".join(facts).lower()
    assert "internal planning target" in joined
    assert "not a contractual" in joined
    assert "mandatory deadline" in joined
    assert not any("is a contractual delivery deadline" == item.lower() for item in facts)
    warning = _rewrite_commitment_overclaim(
        "There is a mandatory target delivery timeline and an explicit customer deadline.",
        COMMITMENT_INTERNAL_TARGET,
    ).lower()
    assert "mandatory" not in warning
    assert "explicit customer deadline" not in warning
    assert "internal" in warning and "target" in warning


def test_explicit_contractual_deadline_stays_contractual():
    assert classify_date_commitment([CONTRACTUAL_REQUEST]) == COMMITMENT_CONTRACTUAL
    facts = _extract_explicit_timeline_facts(CONTRACTUAL_REQUEST)
    assert any("contractual delivery deadline" in item.lower() for item in facts)
    assert not any("internal planning target" in item.lower() for item in facts)
    original = "Honor the contractual deadline."
    assert _rewrite_commitment_overclaim(original, COMMITMENT_CONTRACTUAL) == original


def test_aspirational_date_is_distinct_from_deadline_and_target():
    assert classify_date_commitment([ASPIRATIONAL_REQUEST]) == COMMITMENT_ASPIRATIONAL
    facts = _extract_explicit_timeline_facts(ASPIRATIONAL_REQUEST)
    joined = " ".join(facts).lower()
    assert "aspirational" in joined
    assert "not a deadline" in joined
    assert "contractual delivery deadline" not in joined
    rewritten = _rewrite_commitment_overclaim(
        "This is a binding deadline.",
        COMMITMENT_ASPIRATIONAL,
    ).lower()
    assert "binding deadline" not in rewritten
    assert "aspirational" in rewritten


def test_missing_commitment_status_is_left_uncertain():
    assert classify_date_commitment([UNSPECIFIED_REQUEST]) == COMMITMENT_UNSPECIFIED
    facts = _extract_explicit_timeline_facts(UNSPECIFIED_REQUEST)
    joined = " ".join(facts).lower()
    assert "target delivery timeline" in joined
    assert "contractual delivery deadline" not in joined
    assert "internal planning target" not in joined
    assert "aspirational" not in joined
    rewritten = _rewrite_commitment_overclaim(
        "This is a mandatory deadline.",
        COMMITMENT_UNSPECIFIED,
    ).lower()
    assert "mandatory deadline" not in rewritten
    assert "unconfirmed" in rewritten


def test_feasibility_still_compares_internal_target_to_independent_estimate():
    blocking, warnings, checks = _deterministic_delivery_gate(
        discovery={
            "constraints": _extract_explicit_timeline_facts(INTERNAL_TARGET_REQUEST),
            "unknowns": [],
        },
        requirements={"functional_requirements": [], "non_functional_requirements": [], "acceptance_criteria": []},
        estimate={"duration_range": "12-16 weeks", "standard_deadline_fit": "EXCEEDS"},
        source_text=INTERNAL_TARGET_REQUEST,
    )
    joined = " ".join(warnings).lower()
    assert blocking == []
    assert "exceeds" in joined
    assert "stated internal target" in joined
    assert "mandatory" not in joined
    assert "explicit customer deadline" not in joined
    assert "contractual" not in joined

    _blocking, _warnings, fit_checks = _deterministic_delivery_gate(
        discovery={
            "constraints": _extract_explicit_timeline_facts(INTERNAL_TARGET_REQUEST),
            "unknowns": [],
        },
        requirements={"functional_requirements": [], "non_functional_requirements": [], "acceptance_criteria": []},
        estimate={"duration_range": "4-6 weeks", "standard_deadline_fit": "FITS"},
        source_text=INTERNAL_TARGET_REQUEST,
    )
    assert any("does not exceed the stated internal target" in item.lower() for item in fit_checks)


def test_delivery_review_sanitizes_internal_target_overclaims_and_keeps_the_gap():
    class CaptureProvider(ScriptedProvider):
        def __init__(self, payload):
            super().__init__(payload)
            self.prompts = []

        def generate_json(self, prompt: str, schema: dict) -> dict:
            self.prompts.append(prompt)
            return super().generate_json(prompt, schema)

    provider = CaptureProvider(
        {
            "status": "READY",
            "blocking_issues": [],
            "clarification_questions": [],
            "warnings": ["The mandatory target delivery timeline cannot be ignored."],
            "checks": ["Confirmed an explicit customer deadline."],
        }
    )
    result = delivery_review_agent(
        _review_state(INTERNAL_TARGET_REQUEST, "12-16 weeks"),
        provider,
    )["delivery_review"]
    blob = " ".join(result["warnings"] + result["checks"]).lower()
    assert "exceeds" in blob
    assert "stated internal target" in blob
    assert "mandatory" not in blob
    assert "explicit customer deadline" not in blob
    assert "commitment status" in provider.prompts[0].lower()
    assert result["status"] == "READY"
    assert not result["blocking_issues"]


def test_twelve_week_non_binding_target_is_source_internal():
    assert classify_date_commitment([TWELVE_WEEK_INTERNAL_REQUEST]) == (
        COMMITMENT_INTERNAL_TARGET
    )
    assert classify_date_commitment([UNSPECIFIED_REQUEST]) == COMMITMENT_UNSPECIFIED
    facts = _extract_explicit_timeline_facts(TWELVE_WEEK_INTERNAL_REQUEST)
    joined = " ".join(facts).lower()
    assert "12" in joined and "week" in joined
    assert "internal planning target" in joined
    assert "not a contractual" in joined
    assert not any("is a contractual delivery deadline" == item.lower() for item in facts)


def test_llm_constraint_cannot_reclassify_a_non_binding_target():
    mixed = sanitize_timeline_constraints(
        [
            "Target delivery timeline: 12 weeks",
            "The 12-week launch is a contractual deadline.",
        ],
        [TWELVE_WEEK_INTERNAL_REQUEST],
    )
    blob = " ".join(mixed).lower()
    assert "internal planning target" in blob
    assert not any(
        "contractual" in item.lower() and "not a contractual" not in item.lower()
        for item in mixed
    )
    assert classify_date_commitment([TWELVE_WEEK_INTERNAL_REQUEST, *mixed]) == (
        COMMITMENT_INTERNAL_TARGET
    )


def test_discovery_keeps_twelve_week_target_non_contractual():
    provider = ScriptedProvider(
        {
            "problem": "Members need a catalog.",
            "business_goal": "Search holdings.",
            "users": ["Members"],
            "stakeholders": [],
            "existing_systems": [],
            "constraints": [
                "The launch in 12 weeks is a contractual deadline.",
            ],
            "assumptions": [],
            "unknowns": [
                "Whether the 12-week date is a contractual deadline or an internal target",
            ],
            "clarification_questions": [
                "Is the 12-week date a target or a contractual deadline?",
            ],
        }
    )
    discovery = discovery_agent(
        {"user_request": TWELVE_WEEK_INTERNAL_REQUEST},
        provider,
    )["discovery"]
    constraints = " ".join(str(item) for item in discovery["constraints"]).lower()
    assert "internal planning target" in constraints
    assert "12" in constraints
    assert not any(
        "contractual deadline" in str(item).lower()
        and "not a contractual" not in str(item).lower()
        for item in discovery["constraints"]
    )
    assert discovery["unknowns"] == []
    assert discovery["clarification_questions"] == []


def test_requirements_do_not_contradict_stated_non_binding_target():
    grounded = _ground_requirements_to_discovery(
        {
            "problem": "Members need a catalog.",
            "business_goal": "Search holdings.",
            "users": ["Members"],
            "stakeholders": [],
            "existing_systems": [],
            "constraints": _extract_explicit_timeline_facts(TWELVE_WEEK_INTERNAL_REQUEST),
            "assumptions": [],
            "unknowns": [],
        },
        {
            "functional_requirements": ["Members can search holdings."],
            "non_functional_requirements": [],
            "acceptance_criteria": ["A member can search holdings."],
            "open_questions": [],
            "contradictions": [
                "Discovery treats the 12-week launch as a contractual deadline, "
                "but the request says it is a target, not an approved delivery commitment."
            ],
        },
        source_text=TWELVE_WEEK_INTERNAL_REQUEST,
    )
    assert grounded["contradictions"] == []


def test_twelve_week_target_still_compared_to_independent_estimate():
    facts = _extract_explicit_timeline_facts(TWELVE_WEEK_INTERNAL_REQUEST)
    blocking, warnings, checks = _deterministic_delivery_gate(
        discovery={"constraints": facts, "unknowns": []},
        requirements={
            "functional_requirements": [],
            "non_functional_requirements": [],
            "acceptance_criteria": [],
        },
        estimate={"duration_range": "16-20 weeks", "standard_deadline_fit": "EXCEEDS"},
        source_text=TWELVE_WEEK_INTERNAL_REQUEST,
    )
    joined = " ".join(warnings).lower()
    assert blocking == []
    assert "exceeds" in joined
    assert "stated internal target" in joined
    assert "feasibility" in joined
    assert "contractual" not in joined
    assert "mandatory" not in joined
    assert checks == [] or "contractual" not in " ".join(checks).lower()

    provider = ScriptedProvider(
        {
            "status": "READY",
            "blocking_issues": [],
            "clarification_questions": [],
            "warnings": ["The contractual deadline of 12 weeks is at risk."],
            "checks": [],
        }
    )
    review = delivery_review_agent(
        _review_state(TWELVE_WEEK_INTERNAL_REQUEST, "16-20 weeks", constraints=facts),
        provider,
    )["delivery_review"]
    blob = " ".join(review["warnings"] + review["checks"]).lower()
    assert "exceeds" in blob
    assert "stated internal target" in blob
    assert "contractual" not in blob
    assert review["status"] == "READY"


FIELD_SERVICE_INTERNAL_REQUEST = (
    "Build a field-service dispatch board so coordinators can assign jobs. "
    "The first release is an internal target of 2 months, not a contractual deadline."
)


def _proposal_payload(summary: str, risks=None):
    return {
        "executive_summary": summary,
        "scope": ["Dispatch board"],
        "delivery_approach": ["Phased"],
        "timeline": summary,
        "assumptions": [],
        "risks": risks or [summary],
        "next_steps": ["Review"],
        "objectives": ["Assign jobs"],
        "deliverables": ["Dispatch board"],
        "in_scope": ["Job assignment"],
        "out_of_scope": [],
        "dependencies": [],
        "acceptance": [],
    }


def _no_target_exceeds_estimate(text: str) -> None:
    compact = re.sub(r"\s+", " ", str(text or "").lower().replace("–", "-").replace("—", "-"))
    assert re.search(
        r"(?:internal\s+target|stated\s+(?:internal\s+)?target|2-month|2 months)"
        r".{0,40}exceeds.{0,40}(?:independent|3-4 months)",
        compact,
    ) is None


def test_sanitize_inverts_target_exceeds_estimate_for_internal_target():
    estimate = {
        "standard_deadline_fit": "EXCEEDS",
        "customer_deadline": "2 months",
        "duration_range": "3-4 months",
        "baseline_duration_range": "3-4 months",
    }
    inverted = (
        "The 2-month internal target exceeds an independent estimate of 3-4 months."
    )
    rewritten = sanitize_comparison_wording(
        inverted, estimate, COMMITMENT_INTERNAL_TARGET
    ).lower()
    _no_target_exceeds_estimate(rewritten)
    assert "independent estimate of 3-4 months" in rewritten
    assert "exceeds the stated internal target of 2 months" in rewritten
    assert "contractual" not in rewritten


def test_sanitize_fits_when_estimate_is_shorter_than_target():
    estimate = {
        "standard_deadline_fit": "FITS",
        "customer_deadline": "2 months",
        "duration_range": "4-6 weeks",
        "baseline_duration_range": "4-6 weeks",
    }
    inverted = (
        "The independent estimate of 4-6 weeks exceeds the 2-month internal target."
    )
    rewritten = sanitize_comparison_wording(
        inverted, estimate, COMMITMENT_INTERNAL_TARGET
    ).lower()
    assert "does not exceed the stated internal target of 2 months" in rewritten
    assert re.search(r"4-6 weeks exceeds", rewritten) is None


def test_executive_summary_verdict_review_and_proposal_agree_when_estimate_exceeds_target():
    request = FIELD_SERVICE_INTERNAL_REQUEST
    inverted = (
        "The 2-month internal target exceeds an independent estimate of 3-4 months."
    )
    estimate = {
        "effort_range": "40-80 person-days",
        "duration_range": "3-4 months",
        "baseline_duration_range": "3-4 months",
        "customer_deadline": "2 months",
        "confidence": "MEDIUM",
        "assumptions": [],
        "risks_affecting_estimate": [inverted],
        "standard_deadline_fit": "EXCEEDS",
    }
    facts = _extract_explicit_timeline_facts(request)
    state = _estimate_state(facts, "3-4 months")
    state["user_request"] = request
    state["estimate"] = estimate
    proposal = proposal_agent(state, ScriptedProvider(_proposal_payload(inverted)))["proposal"]
    sow = sow_agent(state, ScriptedProvider(_proposal_payload(inverted)))["sow"]
    review = delivery_review_agent(
        state,
        ScriptedProvider(
            {
                "status": "READY",
                "blocking_issues": [],
                "clarification_questions": [],
                "warnings": [inverted],
                "checks": [],
            }
        ),
    )["delivery_review"]
    payload = workflow_response(
        {
            "workflow_status": "COMPLETE",
            "user_request": request,
            "discovery": {
                "problem": "Coordinators assign field jobs.",
                "business_goal": "Dispatch work.",
                "constraints": facts,
                "unknowns": [],
            },
            "estimate": estimate,
            "proposal": proposal,
            "sow": sow,
            "delivery_review": review,
            "solution": {"delivery_risks": [inverted]},
            "blocking_questions": [],
            "non_blocking_questions": [],
        }
    )
    blobs = [
        payload["verdict"]["summary"],
        payload["assessment_text"],
        payload["assessment"]["deadline"]["gap"],
        proposal["executive_summary"],
        proposal["timeline"],
        sow["timeline"],
        " ".join(review["warnings"] + review["checks"]),
    ]
    joined = " ".join(blobs)
    _no_target_exceeds_estimate(joined)
    assert payload["verdict"]["code"] == "DEADLINE_AT_RISK"
    assert payload["estimate"]["standard_deadline_fit"] == "EXCEEDS"
    assert "stated internal target" in joined.lower()
    canonical = canonical_fit_comparison(estimate, COMMITMENT_INTERNAL_TARGET).lower()
    assert canonical.rstrip(".") in proposal["executive_summary"].lower()
    assert canonical.rstrip(".") in payload["verdict"]["summary"].lower()
    assert "contractual" not in payload["verdict"]["summary"].lower()
    assert "mandatory" not in " ".join(review["warnings"]).lower()


def test_artifacts_agree_when_independent_estimate_fits_internal_target():
    request = FIELD_SERVICE_INTERNAL_REQUEST
    inverted = (
        "The independent estimate of 4-6 weeks exceeds the 2-month internal target."
    )
    estimate = {
        "effort_range": "20-40 person-days",
        "duration_range": "4-6 weeks",
        "baseline_duration_range": "4-6 weeks",
        "customer_deadline": "2 months",
        "confidence": "MEDIUM",
        "assumptions": [],
        "risks_affecting_estimate": [inverted],
        "standard_deadline_fit": "FITS",
    }
    facts = _extract_explicit_timeline_facts(request)
    state = _estimate_state(facts, "4-6 weeks")
    state["user_request"] = request
    state["estimate"] = estimate
    proposal = proposal_agent(state, ScriptedProvider(_proposal_payload(inverted)))["proposal"]
    review = delivery_review_agent(
        state,
        ScriptedProvider(
            {
                "status": "READY",
                "blocking_issues": [],
                "clarification_questions": [],
                "warnings": [inverted],
                "checks": [],
            }
        ),
    )["delivery_review"]
    payload = workflow_response(
        {
            "workflow_status": "COMPLETE",
            "user_request": request,
            "discovery": {
                "problem": "Coordinators assign field jobs.",
                "business_goal": "Dispatch work.",
                "constraints": facts,
                "unknowns": [],
            },
            "estimate": estimate,
            "proposal": proposal,
            "delivery_review": review,
            "solution": {"delivery_risks": [inverted]},
            "blocking_questions": [],
            "non_blocking_questions": [],
        }
    )
    joined = " ".join(
        [
            payload["verdict"]["summary"],
            payload["assessment_text"],
            proposal["executive_summary"],
            " ".join(review["warnings"] + review["checks"]),
        ]
    ).lower()
    assert payload["verdict"]["code"] == "DEADLINE_FIT"
    assert "does not exceed the stated internal target" in joined
    assert re.search(r"4-6 weeks exceeds", joined) is None
    assert payload["estimate"]["standard_deadline_fit"] == "FITS"
