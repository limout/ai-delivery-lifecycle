"""Regression coverage for production run 0330f96a-5703-4883-b776-95ee4b844e60.

The quoted strings are the values from that Render response. The full run
payload is not stored locally, so these tests use those values directly.
"""

from app.agents import _apply_deadline_honesty, apply_established_scope_carry
from app.api import workflow_response
from app.assessment import sanitize_comparison_wording
from app.decisions import apply_final_artifact_quality, normalize_paraphrase_duplicates
from app.timeline import COMMITMENT_INTERNAL_TARGET

CANONICAL = (
    "The independent estimate of 3.5-4.5 months exceeds the stated internal target of 2 months."
)
MALFORMED = (
    "The independent estimate of 3.5-4."
    "The independent estimate of 3.5-4.5 months exceeds the stated internal target of 2 months."
)
ESTIMATE = {
    "standard_deadline_fit": "EXCEEDS",
    "customer_deadline": "2 months",
    "duration_range": "3.5-4.5 months",
    "baseline_duration_range": "3.5-4.5 months",
}

EMAIL = "The system must send email notifications to customers."
EMAIL_PARAPHRASE = "Email notifications sent to customers"
LOGIN = "The system must allow customers to log in to the web application."
LOGIN_PROFILE = "Customer login and profile management functionality"
PROFILE = "The system must allow customers to manage profiles and preferences."
PAYMENTS = "Online payments processing via Stripe"
PAYMENTS_PARAPHRASE = "Allow customers to make online payments securely via Stripe"
SAP = "The system must integrate with SAP S/4HANA for customer master data."
SAP_SUMMARY = "SAP integration for customer master data"
STRIPE = "The system must integrate with Stripe for payment processing."
STRIPE_SUMMARY = "Stripe payment integration"
CREATE = "The system must allow customers to create service requests."
TRACK = "The system must allow customers to track service request status."
CREATE_AND_TRACK = "Creation and tracking of service requests."


def _production_scope():
    return [
        EMAIL,
        EMAIL_PARAPHRASE,
        LOGIN,
        PROFILE,
        LOGIN_PROFILE,
        PAYMENTS,
        PAYMENTS_PARAPHRASE,
        SAP,
        SAP_SUMMARY,
        STRIPE,
        STRIPE_SUMMARY,
        CREATE,
        TRACK,
        CREATE_AND_TRACK,
    ]


def test_production_scope_paraphrases_are_removed_and_create_track_stay():
    kept, findings = normalize_paraphrase_duplicates(_production_scope())
    blob = " ".join(kept)
    assert EMAIL in kept
    assert EMAIL_PARAPHRASE not in blob
    assert LOGIN in kept
    assert LOGIN_PROFILE not in blob
    assert PROFILE in kept
    assert PAYMENTS in kept
    assert PAYMENTS_PARAPHRASE not in blob
    assert SAP in kept
    assert SAP_SUMMARY not in blob
    assert STRIPE in kept
    assert STRIPE_SUMMARY not in blob
    assert CREATE in kept
    assert TRACK in kept
    assert CREATE_AND_TRACK not in blob
    assert any(item["code"] == "COMPOUND_REDUNDANT" and item["removed"] == CREATE_AND_TRACK for item in findings)
    assert any(item["code"] == "COMPOUND_REDUNDANT" and item["removed"] == LOGIN_PROFILE for item in findings)


def test_create_and_track_remain_distinct_when_both_are_present():
    kept, findings = normalize_paraphrase_duplicates([CREATE, TRACK])
    assert kept == [CREATE, TRACK]
    assert findings == []


def test_compound_is_removed_only_when_every_behavior_is_already_covered():
    partial, partial_findings = normalize_paraphrase_duplicates([CREATE, CREATE_AND_TRACK])
    assert partial == [CREATE, CREATE_AND_TRACK]
    assert partial_findings[0]["code"] == "AMBIGUOUS_OVERLAP"

    covered, covered_findings = normalize_paraphrase_duplicates([CREATE, TRACK, CREATE_AND_TRACK])
    assert CREATE in covered and TRACK in covered
    assert CREATE_AND_TRACK not in covered
    assert covered_findings[0]["code"] == "COMPOUND_REDUNDANT"

    login_only, login_findings = normalize_paraphrase_duplicates([LOGIN, LOGIN_PROFILE])
    assert LOGIN_PROFILE in login_only
    assert login_findings[0]["code"] == "AMBIGUOUS_OVERLAP"

    broader, broader_findings = normalize_paraphrase_duplicates([LOGIN, PROFILE, LOGIN_PROFILE])
    assert LOGIN in broader and PROFILE in broader
    assert LOGIN_PROFILE not in broader
    assert any(item["code"] == "COMPOUND_REDUNDANT" for item in broader_findings)


def test_carry_removes_production_paraphrases_from_each_scope_list():
    items = _production_scope()
    updated = apply_established_scope_carry(
        {
            "requirements": {"functional_requirements": [EMAIL, LOGIN, PROFILE, CREATE, TRACK, SAP, STRIPE]},
            "solution": {"key_capabilities": items, "integration_approach": [SAP, SAP_SUMMARY, STRIPE, STRIPE_SUMMARY]},
            "proposal": {"scope": items},
            "sow": {"in_scope": items, "acceptance": [EMAIL, EMAIL_PARAPHRASE, PAYMENTS, PAYMENTS_PARAPHRASE]},
        }
    )
    for artifact, field in (
        ("solution", "key_capabilities"),
        ("proposal", "scope"),
        ("sow", "in_scope"),
        ("sow", "acceptance"),
    ):
        blob = " ".join(updated[artifact][field])
        assert EMAIL_PARAPHRASE not in blob
        assert LOGIN_PROFILE not in blob
        assert PAYMENTS_PARAPHRASE not in blob
        assert SAP_SUMMARY not in blob
        assert STRIPE_SUMMARY not in blob
        assert CREATE_AND_TRACK not in blob
    capabilities = " ".join(updated["solution"]["key_capabilities"])
    assert CREATE in updated["solution"]["key_capabilities"]
    assert TRACK in updated["solution"]["key_capabilities"]
    assert "service request" in capabilities


def test_sanitize_repairs_decimal_splice_and_stays_stable():
    once = sanitize_comparison_wording(CANONICAL, ESTIMATE, COMMITMENT_INTERNAL_TARGET)
    twice = sanitize_comparison_wording(once, ESTIMATE, COMMITMENT_INTERNAL_TARGET)
    healed = sanitize_comparison_wording(MALFORMED, ESTIMATE, COMMITMENT_INTERNAL_TARGET)
    healed_again = sanitize_comparison_wording(healed, ESTIMATE, COMMITMENT_INTERNAL_TARGET)
    assert once == CANONICAL
    assert twice == CANONICAL
    assert healed == CANONICAL
    assert healed_again == CANONICAL
    assert "3.5-4.The" not in healed

    paragraph = CANONICAL + " Do not treat the date as a commitment."
    assert sanitize_comparison_wording(
        sanitize_comparison_wording(paragraph, ESTIMATE, COMMITMENT_INTERNAL_TARGET),
        ESTIMATE,
        COMMITMENT_INTERNAL_TARGET,
    ) == paragraph

    evidence = "Deadline compression. Evidence: " + MALFORMED
    repaired = sanitize_comparison_wording(evidence, ESTIMATE, COMMITMENT_INTERNAL_TARGET)
    assert repaired == "Deadline compression. Evidence: " + CANONICAL
    assert sanitize_comparison_wording(repaired, ESTIMATE, COMMITMENT_INTERNAL_TARGET) == repaired


def test_affected_artifact_fields_emit_the_estimate_sentence_once():
    request = (
        "Build a customer web application. "
        "The first release is an internal target of 2 months, not a contractual deadline."
    )
    payload = workflow_response(
        {
            "workflow_status": "COMPLETE",
            "user_request": request,
            "discovery": {
                "problem": "Customers need a web application.",
                "business_goal": "Accept requests online.",
                "constraints": ["The first release is an internal target of 2 months."],
                "unknowns": [],
            },
            "requirements": {"functional_requirements": [EMAIL, LOGIN, CREATE, TRACK]},
            "estimate": dict(ESTIMATE),
            "proposal": {
                "executive_summary": MALFORMED,
                "scope": [EMAIL, EMAIL_PARAPHRASE],
                "risks": ["Deadline compression. Evidence: " + MALFORMED],
            },
            "solution": {
                "key_capabilities": [EMAIL, EMAIL_PARAPHRASE, LOGIN, LOGIN_PROFILE, PROFILE],
                "delivery_risks": [MALFORMED],
            },
            "sow": {"in_scope": [CREATE, TRACK, CREATE_AND_TRACK], "acceptance": [EMAIL_PARAPHRASE, EMAIL]},
            "delivery_review": {"status": "READY", "warnings": [], "blocking_issues": [], "checks": []},
            "blocking_questions": [],
            "non_blocking_questions": [],
        }
    )
    fields = {
        "proposal.executive_summary": payload["proposal"]["executive_summary"],
        "proposal.risks": " ".join(payload["proposal"]["risks"]),
        "assessment.risks": " ".join(payload["assessment"]["risks"]),
        "assessment.why": " ".join(payload["assessment"]["why"]),
    }
    for name, text in fields.items():
        assert "3.5-4.The" not in text, name
        assert text.lower().count(CANONICAL.lower().rstrip(".")) == 1, name
    assert CREATE in payload["sow"]["in_scope"]
    assert TRACK in payload["sow"]["in_scope"]
    assert CREATE_AND_TRACK not in payload["sow"]["in_scope"]
    assert payload["artifact_quality"] == "CLEAN"
    assert payload["delivery_review"]["status"] == "READY"


def test_ready_result_surfaces_residual_artifact_defects():
    payload = {
        "delivery_review": {"status": "READY", "warnings": [], "blocking_issues": []},
        "proposal": {
            "executive_summary": MALFORMED,
            "scope": [EMAIL, EMAIL_PARAPHRASE, CREATE, TRACK],
        },
        "sow": {"in_scope": [CREATE, CREATE_AND_TRACK], "acceptance": [PAYMENTS, PAYMENTS_PARAPHRASE]},
    }
    defects = apply_final_artifact_quality(payload)
    assert payload["delivery_review"]["status"] == "READY"
    assert payload["artifact_quality"] == "DEFECTS"
    assert defects
    assert EMAIL_PARAPHRASE not in payload["proposal"]["scope"]
    assert PAYMENTS_PARAPHRASE not in payload["sow"]["acceptance"]
    assert CREATE_AND_TRACK in payload["sow"]["in_scope"]
    messages = " ".join(payload["delivery_review"]["warnings"])
    assert "proposal.executive_summary" in messages
    assert CREATE_AND_TRACK not in messages


# Run e2d40394-e8b6-46fc-b2d6-d5b4e98da568. The full payload is not stored locally.
ORDER = "The system shall display order history and details from SAP S/4HANA."
ORDER_DUPLICATE = (
    "Given a logged-in customer, when they navigate to the orders section, "
    "then order history and details from SAP S/4HANA are displayed."
)
CREATE_SHALL = "The system shall allow customers to create service requests."
CREATE_DUPLICATE = (
    "Given a logged-in customer, when they submit a service request, "
    "then the request is successfully created in the system."
)
CANCEL = "A customer can cancel a service request."
EMAIL_SHALL = "The system shall send email notifications to customers."
EMAIL_EVENTS = "Email notifications for system events"
SAP_REQUIREMENT = "The system shall integrate with SAP S/4HANA."
STRIPE_REQUIREMENT = "The system shall integrate with Stripe."
COMBINED_INTEGRATION = (
    "Integration with SAP S/4HANA and Stripe using available API access "
    "and technical documentation"
)
TRACK_SHALL = "The system shall allow customers to track service request status."
CREATE_TRACK = "Service request creation and tracking"
GLUED_SUMMARY = (
    "The engagement is estimated at 120 to 180 person-days."
    "The independent estimate of 3.5-4.5 months exceeds the stated internal target of 2 months."
)
GLUED_TIMELINE = (
    "Customer target: 2 months; independent indicative estimate: 3.5-4.5 months. "
    "Deadline assessment: EXCEEDS."
    "The independent estimate of 3.5-4.5 months exceeds the stated internal target of 2 months. "
    "The date must not be treated as a delivery commitment."
)


def _latest_scope():
    return [
        EMAIL_SHALL,
        EMAIL_EVENTS,
        SAP_REQUIREMENT,
        STRIPE_REQUIREMENT,
        COMBINED_INTEGRATION,
        CREATE_SHALL,
        TRACK_SHALL,
        CREATE_TRACK,
    ]


def test_latest_acceptance_and_scope_duplicates_are_removed():
    acceptance, acceptance_findings = normalize_paraphrase_duplicates(
        [ORDER, CREATE_SHALL, CANCEL, ORDER_DUPLICATE, CREATE_DUPLICATE]
    )
    assert acceptance == [ORDER, CREATE_SHALL, CANCEL]
    assert {item["removed"] for item in acceptance_findings} == {ORDER_DUPLICATE, CREATE_DUPLICATE}

    kept, findings = normalize_paraphrase_duplicates(_latest_scope())
    assert EMAIL_SHALL in kept and EMAIL_EVENTS not in kept
    assert SAP_REQUIREMENT in kept and STRIPE_REQUIREMENT in kept
    assert COMBINED_INTEGRATION not in kept
    assert CREATE_SHALL in kept and TRACK_SHALL in kept
    assert CREATE_TRACK not in kept
    assert any(item["code"] == "COMPOUND_REDUNDANT" and item["removed"] == CREATE_TRACK for item in findings)
    assert any(item["removed"] == COMBINED_INTEGRATION for item in findings)

    partial, partial_findings = normalize_paraphrase_duplicates([CREATE_SHALL, CREATE_TRACK])
    assert CREATE_SHALL in partial and CREATE_TRACK in partial
    assert partial_findings[0]["code"] == "AMBIGUOUS_OVERLAP"

    again, again_findings = normalize_paraphrase_duplicates(kept)
    assert again == kept
    assert again_findings == []


def test_estimate_sentences_stay_separated_and_are_not_repeated():
    composed = _apply_deadline_honesty(
        {
            "executive_summary": "The engagement is estimated at 120 to 180 person-days.",
            "timeline": "old timeline",
            "risks": [],
        },
        ESTIMATE,
        COMMITMENT_INTERNAL_TARGET,
    )
    summary = sanitize_comparison_wording(
        composed["executive_summary"], ESTIMATE, COMMITMENT_INTERNAL_TARGET
    )
    timeline = sanitize_comparison_wording(
        composed["timeline"], ESTIMATE, COMMITMENT_INTERNAL_TARGET
    )
    assert summary == (
        "The engagement is estimated at 120 to 180 person-days. " + CANONICAL
    )
    assert "EXCEEDS. The independent estimate" in timeline
    assert summary.lower().count(CANONICAL.lower().rstrip(".")) == 1
    assert timeline.lower().count(CANONICAL.lower().rstrip(".")) == 1
    assert sanitize_comparison_wording(summary, ESTIMATE, COMMITMENT_INTERNAL_TARGET) == summary
    assert sanitize_comparison_wording(timeline, ESTIMATE, COMMITMENT_INTERNAL_TARGET) == timeline
    healed = sanitize_comparison_wording(GLUED_SUMMARY, ESTIMATE, COMMITMENT_INTERNAL_TARGET)
    assert healed == summary
    assert "person-days.The" not in healed
    assert "EXCEEDS.The" not in sanitize_comparison_wording(
        GLUED_TIMELINE, ESTIMATE, COMMITMENT_INTERNAL_TARGET
    )


def test_latest_assembled_artifact_is_clean_only_after_the_fields_pass():
    request = (
        "Build a customer web application. "
        "The first release is an internal target of 2 months, not a contractual deadline."
    )
    dirty = {
        "delivery_review": {"status": "READY", "warnings": [], "blocking_issues": []},
        "proposal": {"executive_summary": GLUED_SUMMARY, "scope": _latest_scope()},
        "solution": {"key_capabilities": _latest_scope()},
        "sow": {
            "in_scope": _latest_scope(),
            "acceptance": [ORDER, CREATE_SHALL, CANCEL, ORDER_DUPLICATE, CREATE_DUPLICATE],
            "timeline": GLUED_TIMELINE,
        },
    }
    defects = apply_final_artifact_quality(dirty)
    assert ORDER_DUPLICATE not in dirty["sow"]["acceptance"]
    assert CREATE_DUPLICATE not in dirty["sow"]["acceptance"]
    assert CANCEL in dirty["sow"]["acceptance"]
    assert EMAIL_EVENTS not in dirty["proposal"]["scope"]
    assert COMBINED_INTEGRATION not in dirty["solution"]["key_capabilities"]
    assert CREATE_SHALL in dirty["sow"]["in_scope"] and TRACK_SHALL in dirty["sow"]["in_scope"]
    assert dirty["artifact_quality"] == "DEFECTS"
    assert any(item["field"] == "proposal.executive_summary" for item in defects)
    assert any(item["field"] == "sow.timeline" for item in defects)

    payload = workflow_response(
        {
            "workflow_status": "COMPLETE",
            "user_request": request,
            "discovery": {
                "problem": "Customers need order history and service requests.",
                "business_goal": "Serve customers online.",
                "constraints": ["The first release is an internal target of 2 months."],
                "unknowns": [],
            },
            "requirements": {
                "functional_requirements": [
                    EMAIL_SHALL,
                    SAP_REQUIREMENT,
                    STRIPE_REQUIREMENT,
                    CREATE_SHALL,
                    TRACK_SHALL,
                    ORDER,
                ],
                "acceptance_criteria": [ORDER, CREATE_SHALL, CANCEL],
            },
            "estimate": dict(ESTIMATE),
            "proposal": {
                "executive_summary": GLUED_SUMMARY,
                "scope": _latest_scope(),
                "timeline": GLUED_TIMELINE,
                "risks": [],
            },
            "solution": {"key_capabilities": _latest_scope(), "delivery_risks": []},
            "sow": {
                "in_scope": _latest_scope(),
                "acceptance": [ORDER, CREATE_SHALL, CANCEL, ORDER_DUPLICATE, CREATE_DUPLICATE],
                "timeline": GLUED_TIMELINE,
            },
            "delivery_review": {"status": "READY", "warnings": [], "blocking_issues": [], "checks": []},
            "blocking_questions": [],
            "non_blocking_questions": [],
        }
    )
    for artifact, field in (
        ("solution", "key_capabilities"),
        ("proposal", "scope"),
        ("sow", "in_scope"),
    ):
        blob = " ".join(payload[artifact][field])
        assert EMAIL_EVENTS not in blob
        assert COMBINED_INTEGRATION not in blob
        assert CREATE_TRACK not in blob
        assert CREATE_SHALL in payload[artifact][field]
        assert TRACK_SHALL in payload[artifact][field]
        assert SAP_REQUIREMENT in payload[artifact][field]
        assert STRIPE_REQUIREMENT in payload[artifact][field]
    acceptance = payload["sow"]["acceptance"]
    assert ORDER in acceptance and CREATE_SHALL in acceptance and CANCEL in acceptance
    assert ORDER_DUPLICATE not in acceptance and CREATE_DUPLICATE not in acceptance
    rendered = " ".join(
        [
            payload["proposal"]["executive_summary"],
            payload["proposal"]["timeline"],
            payload["sow"]["timeline"],
            payload["assessment_text"],
            payload["print_assessment_text"],
            *payload["artifact_texts"].values(),
        ]
    )
    assert "person-days.The" not in rendered
    assert "EXCEEDS.The" not in rendered
    assert "120 to 180 person-days. The independent estimate" in payload["proposal"]["executive_summary"]
    assert "EXCEEDS. The independent estimate" in payload["proposal"]["timeline"]
    assert "EXCEEDS. The independent estimate" in payload["sow"]["timeline"]
    assert payload["proposal"]["executive_summary"].lower().count(CANONICAL.lower().rstrip(".")) == 1
    assert payload["artifact_quality"] == "CLEAN"
