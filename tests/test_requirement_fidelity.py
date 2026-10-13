from app.agents import (
    _ground_requirements_to_discovery,
    _is_delivery_planning_constraint,
    requirements_agent,
)
from app.evidence import (
    outcome_is_covered,
    stated_request_outcomes,
    uncovered_request_outcomes,
)
from app.providers import AIProvider


CUSTOMER_SELF_SERVICE_REQUEST = """
We need to build a customer self-service web application.
Customers can log in and manage profiles, and create and track service requests.
SAP S/4HANA remains the source of truth. Stripe handles payments.
The Product Owner wants an internal target of 2 months.
Authentication protocol and API schemas are unspecified.
""".strip()

LIBRARY_REQUEST = """
Build a public library catalog so members can search holdings and place holds.
Pickup notice templates are unspecified.
""".strip()


class ScriptedJsonProvider(AIProvider):
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.prompts = []

    def generate_json(self, prompt: str, schema: dict) -> dict:
        self.prompts.append(prompt)
        if not self.payloads:
            raise AssertionError("unexpected extra generate_json call")
        return dict(self.payloads.pop(0))


def _discovery(**overrides):
    payload = {
        "problem": "Customers need a self-service channel.",
        "business_goal": "Reduce support effort.",
        "users": ["Customers"],
        "stakeholders": ["Product Owner"],
        "existing_systems": ["Existing systems of record"],
        "constraints": ["Internal target of 2 months"],
        "assumptions": [],
        "unknowns": ["Authentication protocol is unspecified"],
    }
    payload.update(overrides)
    return payload


def _requirements(**overrides):
    payload = {
        "functional_requirements": [],
        "non_functional_requirements": [],
        "acceptance_criteria": [],
        "open_questions": [],
        "contradictions": [],
    }
    payload.update(overrides)
    return payload


def test_self_service_request_keeps_login_and_create_distinct_from_profile_and_track():
    outcomes = stated_request_outcomes(CUSTOMER_SELF_SERVICE_REQUEST)
    blob = " ".join(outcomes)
    assert "authenticate" in outcomes
    assert any("manage" in item and "profile" in item for item in outcomes)
    assert any(item.startswith("create") and "service" in item for item in outcomes)
    assert any(item.startswith("track") and "service" in item for item in outcomes)
    assert "source of truth" in outcomes
    collapsed = _requirements(
        functional_requirements=[
            "Customers can manage profiles.",
            "Customers can track service requests.",
            "The portal must integrate with the finance system of record.",
        ],
        acceptance_criteria=[
            "A customer can update a profile.",
            "A customer can see service-request status.",
        ],
        non_functional_requirements=["The finance system remains the source of truth."],
    )
    missing = uncovered_request_outcomes(CUSTOMER_SELF_SERVICE_REQUEST, collapsed)
    assert any(item == "authenticate" or "log in" in item for item in missing)
    assert any(item.startswith("create") for item in missing)
    assert "source of truth" not in missing
    assert not any(item.startswith("track") for item in missing)
    assert not any("manage" in item for item in missing)


def test_acceptance_criteria_can_cover_a_preserved_outcome():
    requirements = _requirements(
        functional_requirements=["Customers can manage profiles."],
        acceptance_criteria=["A registered customer can log in before editing a profile."],
    )
    missing = uncovered_request_outcomes(CUSTOMER_SELF_SERVICE_REQUEST, requirements)
    assert "authenticate" not in missing
    assert not outcome_is_covered("create service requests", "Customers can track service requests.")


def test_unspecified_behavior_is_not_treated_as_covered():
    requirements = _requirements(
        functional_requirements=["Customers can log in and manage profiles."],
        acceptance_criteria=["A customer can authenticate and open a profile."],
        open_questions=["Authentication protocol and API schemas are unspecified."],
    )
    missing = uncovered_request_outcomes(CUSTOMER_SELF_SERVICE_REQUEST, requirements)
    assert any(item.startswith("create") for item in missing)
    assert "oauth" not in " ".join(requirements["functional_requirements"]).lower()


def test_internal_target_is_not_a_product_nfr():
    assert _is_delivery_planning_constraint(
        "The application must launch within the 2-month internal target."
    )
    assert not _is_delivery_planning_constraint(
        "Sensitive profile data must be encrypted in transit."
    )
    grounded = _ground_requirements_to_discovery(
        _discovery(),
        _requirements(
            functional_requirements=["Customers can log in."],
            non_functional_requirements=[
                "The application must launch within the 2-month internal target.",
                "Sensitive profile data must be encrypted in transit.",
            ],
            acceptance_criteria=["A customer can log in."],
        ),
    )
    nfr_text = " ".join(grounded["non_functional_requirements"]).lower()
    assert "internal target" not in nfr_text
    assert "encrypted" in nfr_text


def test_library_request_outcomes_are_domain_independent():
    outcomes = stated_request_outcomes(LIBRARY_REQUEST)
    assert any("search" in item and "holding" in item for item in outcomes)
    assert any("place" in item and "hold" in item for item in outcomes)
    assert "authenticate" not in outcomes
    missing = uncovered_request_outcomes(
        LIBRARY_REQUEST,
        _requirements(functional_requirements=["Members can search holdings."]),
    )
    assert any("place" in item and "hold" in item for item in missing)
    assert not any(item.startswith("search") for item in missing)


def test_requirements_prompt_uses_the_request_and_retries_missing_outcomes():
    collapsed = _requirements(
        functional_requirements=[
            "Customers can manage profiles.",
            "Customers can track service requests.",
        ],
        acceptance_criteria=["A customer can update a profile and see request status."],
        open_questions=["Authentication protocol is unspecified."],
    )
    repaired = _requirements(
        functional_requirements=[
            "Customers can log in.",
            "Customers can manage profiles.",
            "Customers can create service requests.",
            "Customers can track service requests.",
        ],
        non_functional_requirements=["The named system of record remains the source of truth."],
        acceptance_criteria=[
            "A customer can log in.",
            "A customer can update a profile.",
            "A customer can create a service request.",
            "A customer can track a service request.",
        ],
        open_questions=["Authentication protocol and API schemas are unspecified."],
    )
    provider = ScriptedJsonProvider([collapsed, repaired])
    result = requirements_agent(
        {
            "user_request": CUSTOMER_SELF_SERVICE_REQUEST,
            "discovery": _discovery(
                existing_systems=["SAP S/4HANA", "Stripe"],
                constraints=["Internal target of 2 months"],
            ),
        },
        provider,
    )
    assert len(provider.prompts) == 2
    first = provider.prompts[0]
    assert "Original customer request:" in first
    assert CUSTOMER_SELF_SERVICE_REQUEST in first
    assert "view versus update" in first
    assert "create versus track" in first
    assert "internal target date" in first.lower()
    assert "product non-functional requirement" in first.lower()
    assert "contractual commitment" in first.lower()
    rules = first.split("IMPORTANT RULES:", 1)[1]
    assert "SAP S/4HANA" not in rules
    assert "Stripe" not in rules
    assert "Service Requests" not in rules
    second = provider.prompts[1]
    assert "Missing stated outcomes:" in second
    assert "authenticate" in second.lower() or "log in" in second.lower()
    assert "create" in second.lower()
    requirements = result["requirements"]
    joined = " ".join(requirements["functional_requirements"]).lower()
    assert "log in" in joined
    assert "create" in joined
    assert "track" in joined
    assert "source of truth" in " ".join(requirements["non_functional_requirements"]).lower()
    ac = " ".join(requirements["acceptance_criteria"]).lower()
    assert "log in" in ac
    assert "create" in ac
    assert "unspecified" in " ".join(requirements["open_questions"]).lower()
    assert uncovered_request_outcomes(CUSTOMER_SELF_SERVICE_REQUEST, requirements) == ()
