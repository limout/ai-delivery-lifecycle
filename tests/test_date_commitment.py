from app.agents import (
    _deterministic_delivery_gate,
    _extract_explicit_timeline_facts,
    _rewrite_commitment_overclaim,
    delivery_review_agent,
)
from app.timeline import (
    COMMITMENT_ASPIRATIONAL,
    COMMITMENT_CONTRACTUAL,
    COMMITMENT_INTERNAL_TARGET,
    COMMITMENT_UNSPECIFIED,
    classify_date_commitment,
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
