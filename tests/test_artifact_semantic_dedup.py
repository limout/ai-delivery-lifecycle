"""Final-artifact deduplication across unrelated domains.

The rules identify a behavior as a generic verb family plus its object.
They do not depend on a customer-portal vocabulary.
"""

from app.agents import apply_established_scope_carry, proposal_agent
from app.assessment import canonical_fit_comparison, strip_repeated_deadline_statements
from app.timeline import classify_date_commitment
from app.assessment import repair_generated_grammar
from app.decisions import apply_final_artifact_quality, normalize_paraphrase_duplicates
from app.evidence import behavior_signatures
from app.providers import AIProvider


class ScriptedProvider(AIProvider):
    def __init__(self, payload):
        self.payload = dict(payload)

    def generate_json(self, prompt, schema):
        return dict(self.payload)


def _signatures(items):
    found = set()
    for item in items:
        found |= behavior_signatures(item)
    return found


def test_exact_duplicates_collapse_to_one():
    kept, findings = normalize_paraphrase_duplicates(
        [
            "Dispatchers can assign jobs.",
            "Dispatchers can assign jobs.",
        ]
    )
    assert kept == ["Dispatchers can assign jobs."]
    assert findings[0]["code"] == "EXACT_DUPLICATE"


def test_paraphrased_duplicates_collapse_across_domains():
    cases = [
        (
            "portal",
            [
                "The system shall allow customers to log in.",
                "Customer login and authentication workflows.",
            ],
            "log in",
            "authentication workflows",
        ),
        (
            "library",
            [
                "The system shall allow members to search holdings.",
                "Holding search and discovery workflows.",
            ],
            "search holdings",
            "discovery workflows",
        ),
        (
            "clinic",
            [
                "The system shall allow patients to cancel appointments.",
                "Appointment cancellation workflows.",
            ],
            "cancel appointments",
            "cancellation workflows",
        ),
    ]
    for name, items, kept_fragment, removed_fragment in cases:
        kept, findings = normalize_paraphrase_duplicates(items)
        blob = " ".join(kept).lower()
        assert kept_fragment in blob, name
        assert removed_fragment not in blob, name
        assert len(kept) == 1, name
        assert findings[0]["code"] == "PARAPHRASE_COLLAPSED"
        assert findings[0]["kept"] == kept[0]
        assert _signatures(items) == _signatures(kept)


def test_overlapping_but_distinct_capabilities_stay_separate():
    cases = [
        [
            "The system shall allow customers to create service requests.",
            "The system shall allow customers to track service request status.",
        ],
        [
            "Members can search holdings.",
            "Members can place holds.",
        ],
        [
            "Dispatchers can assign jobs.",
            "Dispatchers can notify crews.",
        ],
    ]
    for items in cases:
        kept, findings = normalize_paraphrase_duplicates(items)
        assert kept == items
        assert not any(item["code"] == "PARAPHRASE_COLLAPSED" for item in findings)
        assert _signatures(items) == _signatures(kept)


def test_repeated_acceptance_criteria_collapse_without_dropping_distinct_outcomes():
    criteria = [
        "A customer can log in.",
        "A customer can create a service request.",
        "A customer can track a service request.",
        "A customer can update a profile.",
        "A customer can view account information.",
        "A customer can search prior requests.",
        "A customer can cancel a service request.",
        "The named system of record remains the source of truth.",
        "A customer can submit a payment for a completed request.",
        "Customer authentication succeeds.",
        "Login works for customers.",
        "Customers are able to create service requests.",
        "Creation of a service request is possible.",
        "Service request tracking is available.",
        "Updating a profile is supported.",
    ]
    kept, findings = normalize_paraphrase_duplicates(criteria)
    blob = " ".join(kept).lower()
    assert "can log in" in blob
    assert "can create a service request" in blob
    assert "can track a service request" in blob
    assert "update a profile" in blob
    assert "view account information" in blob
    assert "search prior requests" in blob
    assert "cancel a service request" in blob
    assert "source of truth" in blob
    assert "submit a payment" in blob
    assert "authentication succeeds" not in blob
    assert "login works" not in blob
    assert "creation of a service request" not in blob
    assert "tracking is available" not in blob
    assert "updating a profile is supported" not in blob
    assert len(kept) == 9
    assert {item["code"] for item in findings} == {"PARAPHRASE_COLLAPSED"}
    assert _signatures(criteria) <= _signatures(kept) | {("manage", "profile")}
    assert ("authenticate", "") in _signatures(kept)
    assert ("create", "service request") in _signatures(kept)
    assert ("track", "service request") in _signatures(kept)


def test_downstream_node_cannot_reintroduce_a_paraphrase():
    state = {
        "requirements": {
            "functional_requirements": [
                "The system shall allow members to search holdings.",
                "The system shall allow members to place holds.",
            ],
            "acceptance_criteria": ["A member can search holdings."],
        },
        "solution": {
            "key_capabilities": ["Holding search and discovery workflows."],
        },
        "sow": {
            "in_scope": [
                "The system shall allow members to search holdings.",
                "Holding search and discovery workflows.",
                "The system shall allow members to place holds.",
            ],
            "acceptance": [
                "A member can search holdings.",
                "Holding search succeeds for members.",
            ],
        },
    }
    sow = apply_established_scope_carry(state)["sow"]
    in_scope = " ".join(sow["in_scope"]).lower()
    acceptance = " ".join(sow["acceptance"]).lower()
    assert "search holdings" in in_scope
    assert "place holds" in in_scope
    assert "discovery workflows" not in in_scope
    assert "can search holdings" in acceptance
    assert "search succeeds" not in acceptance
    assert any(item["code"] == "PARAPHRASE_COLLAPSED" for item in sow["quality_findings"])


def test_cross_section_references_are_preserved():
    state = {
        "requirements": {
            "functional_requirements": [
                "The system shall allow patients to cancel appointments.",
            ],
            "acceptance_criteria": ["A patient can cancel an appointment."],
        },
        "sow": {
            "in_scope": ["The system shall allow patients to cancel appointments."],
            "acceptance": ["A patient can cancel an appointment."],
            "objectives": ["Reduce missed clinic appointments."],
        },
    }
    updated = apply_established_scope_carry(state)
    functional = " ".join(updated["requirements"]["functional_requirements"]).lower()
    acceptance = " ".join(updated["sow"]["acceptance"]).lower()
    objectives = " ".join(updated["sow"]["objectives"]).lower()
    assert "cancel appointments" in functional
    assert "cancel an appointment" in acceptance
    assert "missed clinic appointments" in objectives
    assert updated["sow"]["in_scope"] != updated["sow"]["acceptance"]


def test_ambiguous_compound_is_kept_and_reported():
    items = [
        "The system shall allow customers to create service requests.",
        "Creation and tracking of service requests.",
    ]
    kept, findings = normalize_paraphrase_duplicates(items)
    assert items[0] in kept
    assert items[1] not in kept
    assert findings[0]["code"] == "COMPOUND_SPLIT"
    assert ("track", "service request") in _signatures(kept)
    assert ("create", "service request") in _signatures(kept)


def test_observed_sow_drops_paraphrases_and_keeps_distinct_requirements():
    login = "The system shall allow customers to log in."
    create = "The system shall allow customers to create service requests."
    track = "The system shall allow customers to track service request status."
    profile = "The system shall allow customers to manage profiles."
    view = "The system shall allow customers to view account information."
    before_in_scope = [
        login,
        "Customer login and authentication workflows.",
        create,
        "Creation and tracking of service requests.",
        track,
        profile,
        "Customer profile management.",
        view,
    ]
    before_acceptance = [
        "A customer can log in.",
        "A customer can create a service request.",
        "A customer can track a service request.",
        "A customer can update a profile.",
        "A customer can view account information.",
        "A customer can search prior requests.",
        "A customer can cancel a service request.",
        "The named system of record remains the source of truth.",
        "A customer can submit a payment for a completed request.",
        "Customer authentication succeeds.",
        "Login works for customers.",
        "Customers are able to create service requests.",
        "Creation of a service request is possible.",
        "Service request tracking is available.",
        "Updating a profile is supported.",
    ]
    state = {
        "requirements": {
            "functional_requirements": [login, create, track, profile, view],
            "acceptance_criteria": before_acceptance[:9],
        },
        "solution": {
            "key_capabilities": [
                "Customer login and authentication workflows.",
                "Creation and tracking of service requests.",
                "Customer profile management.",
            ],
        },
        "proposal": {
            "scope": [
                login,
                "Customer login and authentication workflows.",
                create,
                track,
            ],
        },
        "sow": {
            "in_scope": list(before_in_scope),
            "acceptance": list(before_acceptance),
            "objectives": ["Give customers a self-service channel."],
        },
    }
    updated = apply_established_scope_carry(state)
    sow = updated["sow"]
    in_scope = sow["in_scope"]
    acceptance = sow["acceptance"]
    in_blob = " ".join(in_scope).lower()
    acceptance_blob = " ".join(acceptance).lower()

    assert "log in" in in_blob
    assert "authentication workflows" not in in_blob
    assert "create service requests" in in_blob
    assert "track service request status" in in_blob
    assert "creation and tracking" not in in_blob
    assert "manage profiles" in in_blob
    assert "profile management" not in in_blob
    assert "view account information" in in_blob
    assert "can log in" in acceptance_blob
    assert "authentication succeeds" not in acceptance_blob
    assert "login works" not in acceptance_blob
    assert "creation of a service request" not in acceptance_blob
    assert "tracking is available" not in acceptance_blob
    assert "updating a profile is supported" not in acceptance_blob
    assert "source of truth" in acceptance_blob
    assert "submit a payment" in acceptance_blob
    assert "search prior requests" in acceptance_blob
    assert "cancel a service request" in acceptance_blob
    assert len(acceptance) == 9
    assert _signatures(before_in_scope) <= _signatures(in_scope)
    assert ("create", "service request") in _signatures(in_scope)
    assert ("track", "service request") in _signatures(in_scope)
    assert ("authenticate", "") in _signatures(in_scope)
    proposal_scope = " ".join(updated["proposal"]["scope"]).lower()
    capabilities = " ".join(updated["solution"]["key_capabilities"]).lower()
    assert "authentication workflows" not in proposal_scope
    assert "authentication workflows" not in capabilities
    assert "log in" in proposal_scope
    assert "create service requests" in capabilities
    assert "track service request" in capabilities


def test_deadline_statement_stays_in_timeline_and_leaves_scope_lists():
    estimate = {
        "standard_deadline_fit": "EXCEEDS",
        "customer_deadline": "2 months",
        "duration_range": "3-4 months",
        "baseline_duration_range": "3-4 months",
    }
    request = "Build a dispatch board. Internal target of 2 months."
    canonical = canonical_fit_comparison(estimate, classify_date_commitment([request]))
    proposal = proposal_agent(
        {
            "user_request": request,
            "discovery": {"problem": "Dispatch", "constraints": ["Internal target of 2 months"]},
            "requirements": {"functional_requirements": ["Dispatchers can assign jobs."]},
            "solution": {"key_capabilities": ["Dispatchers can assign jobs."]},
            "delivery_plan": {},
            "estimate": estimate,
        },
        ScriptedProvider(
            {
                "executive_summary": "Dispatchers need a board.",
                "scope": ["Dispatchers can assign jobs.", canonical],
                "delivery_approach": ["Phased"],
                "timeline": canonical,
                "assumptions": [],
                "risks": [canonical],
                "next_steps": ["Review"],
            }
        ),
    )["proposal"]
    scope = " ".join(proposal["scope"]).lower()
    assert "assign jobs" in scope
    assert canonical.lower().rstrip(".") not in scope
    assert canonical.lower().rstrip(".") in proposal["timeline"].lower()
    assert canonical.lower().rstrip(".") in proposal["executive_summary"].lower()
    assert canonical.lower().rstrip(".") not in " ".join(proposal["risks"]).lower()
    stripped = strip_repeated_deadline_statements(
        {"in_scope": ["Assign jobs.", canonical], "timeline": canonical},
        canonical,
    )
    assert stripped["in_scope"] == ["Assign jobs."]
    assert stripped["timeline"] == canonical


def test_notification_paraphrase_collapses_and_tracking_is_kept():
    notify = "The system must allow customers to receive email notifications."
    nominal = "Email notifications triggered by system events"
    create = "The system must allow customers to create service requests."
    compound = "Service request creation and status tracking"
    pay = "Online payments processing via Stripe"
    integrate = "The system must integrate with Stripe for online payments."
    kept, findings = normalize_paraphrase_duplicates([notify, nominal, create, compound, pay, integrate])
    blob = " ".join(kept).lower()
    assert blob.count("email") == 1 or blob.count("notification") == 1
    assert nominal not in kept
    assert "create" in blob and "track" in blob
    assert compound not in kept
    assert any("pay" in item.lower() or "payment" in item.lower() for item in kept)
    assert any("integrat" in item.lower() for item in kept)
    assert findings
    again, again_findings = normalize_paraphrase_duplicates(kept)
    assert again == kept
    assert again_findings == []


def test_bare_technology_labels_are_absorbed_and_grammar_is_repaired():
    fuller = "The system must integrate with the ledger service for account records."
    kept, findings = normalize_paraphrase_duplicates(
        [
            "Ledger",
            fuller,
            "Order viewing retrieving historical records",
            "Given a member is enrolled, when a notice fires, then the member receives an notice.",
        ]
    )
    assert "Ledger" not in kept
    assert fuller in kept
    assert any(item["code"] == "LABEL_ABSORBED" for item in findings)
    rendered = " ".join(kept)
    assert "viewing retrieving" not in rendered
    assert "viewing and retrieving" in rendered
    assert "an notice" not in rendered
    assert "a notice" in rendered
    narrative = repair_generated_grammar(
        "The date is an internal target rather than stated internal target."
    )
    assert "rather than a stated internal target" in narrative
    assert repair_generated_grammar(narrative) == narrative


def test_unrelated_domain_keeps_distinct_behaviors_and_grades_the_final_artifact():
    schedule = "The system shall allow nurses to schedule clinic visits."
    cancel = "The system shall allow nurses to cancel clinic visits."
    compound = "Clinic visit scheduling and cancellation"
    notify = "The system must allow patients to receive visit notifications."
    nominal = "Visit notifications triggered by system events"
    device = "Infusion pump"
    integrate = "The system shall integrate with the infusion pump for visit records."
    kept, _findings = normalize_paraphrase_duplicates(
        [schedule, cancel, compound, notify, nominal, device, integrate]
    )
    blob = " ".join(kept).lower()
    assert "schedule" in blob and "cancel" in blob
    assert compound not in kept
    assert nominal not in kept
    assert device not in kept
    assert any("integrat" in item.lower() for item in kept)
    again, _again_findings = normalize_paraphrase_duplicates(kept)
    assert again == kept

    valid = {
        "delivery_review": {"status": "READY", "warnings": [], "blocking_issues": []},
        "proposal": {"scope": [schedule, cancel], "executive_summary": "Nurses schedule and cancel visits."},
        "artifact_texts": {"proposal": "stale"},
    }
    assert apply_final_artifact_quality(valid) == []
    assert valid["artifact_quality"] == "CLEAN"
    assert valid["delivery_review"]["status"] == "READY"
    defective = {
        "delivery_review": {"status": "READY", "warnings": [], "blocking_issues": []},
        "proposal": {
            "scope": [schedule],
            "executive_summary": "Visits are scheduled.The nurse confirms the change.",
        },
    }
    defects = apply_final_artifact_quality(defective)
    assert defective["artifact_quality"] == "DEFECTS"
    assert defective["delivery_review"]["status"] == "READY"
    assert defects
