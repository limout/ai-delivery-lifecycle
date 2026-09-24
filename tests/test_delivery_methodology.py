from app.agents import (
    PLAN_SCHEMA,
    delivery_plan_without_methodology,
    delivery_planning_agent,
)
from app.providers import AIProvider


class ScriptedProvider(AIProvider):
    def __init__(self, payload: dict):
        self.payload = payload
        self.prompts = []

    def generate_json(self, prompt: str, schema: dict) -> dict:
        self.prompts.append(prompt)
        return dict(self.payload)


def _plan(**methodology):
    plan = {
        "delivery_phases": ["Foundation", "Build", "Launch"],
        "workstreams": ["Application"],
        "dependencies": ["Access to existing systems"],
        "milestones": ["Pilot ready"],
        "team_roles": ["Delivery lead"],
        "delivery_risks": ["External system availability"],
    }
    if methodology:
        plan["delivery_methodology"] = methodology
    return plan


def _state(*, rich: bool) -> dict:
    if rich:
        return {
            "user_request": (
                "Evolving requirements for incremental product delivery with regular "
                "stakeholder feedback and a prioritizable backlog."
            ),
            "discovery": {
                "problem": "Product scope is still evolving.",
                "business_goal": "Ship incremental releases.",
                "constraints": ["Regular stakeholder feedback is required."],
            },
            "requirements": {
                "functional_requirements": ["Maintain a prioritizable backlog"],
                "non_functional_requirements": [],
            },
            "solution": {
                "solution_summary": "Incremental delivery of the product.",
                "dependencies": ["Independent workstreams can proceed in parallel."],
            },
        }
    return {
        "user_request": "Build a portal.",
        "discovery": {"problem": "", "business_goal": "", "constraints": []},
        "requirements": {"functional_requirements": [], "non_functional_requirements": []},
        "solution": {"solution_summary": "", "dependencies": []},
    }


def test_plan_schema_delivery_methodology_is_optional():
    field = PLAN_SCHEMA["properties"]["delivery_methodology"]
    assert "delivery_methodology" not in PLAN_SCHEMA["required"]
    assert field["properties"]["recommended_methodology"]["enum"] == [
        "SCRUM",
        "KANBAN",
        "WATERFALL",
        "HYBRID",
    ]
    assert field["properties"]["confidence"]["enum"] == ["LOW", "MEDIUM", "HIGH"]
    for name in (
        "rationale",
        "cadence",
        "core_practices",
        "governance",
        "considered_alternatives",
        "unconfirmed_assumptions",
    ):
        assert name in field["properties"]


def test_valid_methodology_is_kept_when_evidence_supports_it():
    provider = ScriptedProvider(
        _plan(
            recommended_methodology="SCRUM",
            rationale=["Incremental product work with a backlog."],
            cadence="1-2 weeks",
            core_practices=["Sprint Review"],
            governance=["Inspect each increment"],
            considered_alternatives=["Kanban"],
            confidence="MEDIUM",
            unconfirmed_assumptions=[],
        )
    )
    result = delivery_planning_agent(_state(rich=True), provider)
    methodology = result["delivery_plan"]["delivery_methodology"]
    assert methodology["recommended_methodology"] == "SCRUM"
    assert methodology["confidence"] == "MEDIUM"
    assert "not a customer commitment" in " ".join(methodology["unconfirmed_assumptions"])


def test_thin_evidence_keeps_valid_recommendation_at_low_confidence():
    result = delivery_planning_agent(
        _state(rich=False),
        ScriptedProvider(
            _plan(
                recommended_methodology="SCRUM",
                rationale=["Limited evidence."],
                cadence="",
                core_practices=[],
                governance=[],
                considered_alternatives=[],
                confidence="HIGH",
                unconfirmed_assumptions=[],
            )
        ),
    )
    methodology = result["delivery_plan"]["delivery_methodology"]
    assert methodology["recommended_methodology"] == "SCRUM"
    assert methodology["confidence"] == "LOW"
    assert any("Unconfirmed:" in item for item in methodology["unconfirmed_assumptions"])


def test_missing_recommendation_is_not_defaulted_to_hybrid():
    result = delivery_planning_agent(
        _state(rich=False),
        ScriptedProvider(_plan()),
    )
    methodology = result["delivery_plan"]["delivery_methodology"]
    assert "recommended_methodology" not in methodology
    assert methodology["confidence"] == "LOW"
    assert methodology.get("recommended_methodology") != "HYBRID"


def test_first_release_and_integrations_keep_non_empty_methodology():
    state = {
        "user_request": "Build a customer portal.",
        "clarification_history": [
            {
                "question": "Who will use the first release, and what will they do in it?",
                "answer": "Enterprise customers can view account information and submit service requests.",
            },
            {
                "question": "Which systems must the first release integrate with?",
                "answer": "SAP S/4HANA is the source of truth; Stripe handles payments.",
            },
        ],
        "discovery": {
            "problem": "Customers need self-service.",
            "business_goal": "Reduce support effort.",
            "constraints": [],
            "existing_systems": ["SAP S/4HANA", "Stripe"],
        },
        "requirements": {
            "functional_requirements": ["View account information"],
            "non_functional_requirements": [],
        },
        "solution": {
            "solution_summary": "A portal connected to finance systems.",
            "integration_approach": ["SAP S/4HANA as source of truth", "Stripe for payments"],
            "dependencies": ["SAP S/4HANA", "Stripe"],
        },
    }
    result = delivery_planning_agent(
        state,
        ScriptedProvider(
            _plan(
                recommended_methodology="SCRUM",
                rationale=["First-release product work with system integrations."],
                cadence="1-2 weeks",
                core_practices=["Sprint Review"],
                governance=[],
                considered_alternatives=["Kanban"],
                confidence="HIGH",
                unconfirmed_assumptions=[],
            )
        ),
    )
    methodology = result["delivery_plan"]["delivery_methodology"]
    assert methodology["recommended_methodology"] == "SCRUM"
    assert methodology["recommended_methodology"] != "HYBRID"
    assert methodology["confidence"] == "LOW"
    notes = " ".join(methodology["unconfirmed_assumptions"])
    assert "incremental vs single-cutover release" not in notes
    assert "dependency structure" not in notes


def test_existing_delivery_plan_fields_remain_intact():
    payload = _plan(
        recommended_methodology="KANBAN",
        confidence="HIGH",
    )
    result = delivery_planning_agent(_state(rich=False), ScriptedProvider(payload))
    plan = result["delivery_plan"]
    for key in (
        "delivery_phases",
        "workstreams",
        "dependencies",
        "milestones",
        "team_roles",
        "delivery_risks",
    ):
        assert plan[key] == payload[key]
    assert set(PLAN_SCHEMA["required"]) == {
        "delivery_phases",
        "workstreams",
        "dependencies",
        "milestones",
        "team_roles",
        "delivery_risks",
    }


def test_stored_plan_keeps_methodology_and_downstream_copy_strips_it():
    result = delivery_planning_agent(
        _state(rich=True),
        ScriptedProvider(
            _plan(
                recommended_methodology="SCRUM",
                rationale=["Incremental product work with a backlog."],
                cadence="1-2 weeks",
                core_practices=["Sprint Review"],
                governance=["Inspect each increment"],
                considered_alternatives=["Kanban"],
                confidence="MEDIUM",
                unconfirmed_assumptions=[],
            )
        ),
    )
    plan = result["delivery_plan"]
    assert "delivery_methodology" in plan
    assert plan["delivery_methodology"]["recommended_methodology"] == "SCRUM"

    stripped = delivery_plan_without_methodology(plan)
    assert "delivery_methodology" not in stripped
    for key in (
        "delivery_phases",
        "workstreams",
        "dependencies",
        "milestones",
        "team_roles",
        "delivery_risks",
    ):
        assert stripped[key] == plan[key]
    assert plan["delivery_methodology"]["recommended_methodology"] == "SCRUM"
