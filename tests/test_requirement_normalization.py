"""Requirement normalization must not equate incomplete behavior signatures."""

from app.decisions import normalize_paraphrase_duplicates
from app.evidence import behavior_signatures


def test_empty_object_signatures_do_not_collapse_distinct_requirements():
    prevent = (
        "Prevent duplicate invoice creation or duplicate payment processing "
        "when payment events are retried."
    )
    confirm = "The system must send payment confirmation emails after successful payments."
    assert behavior_signatures(prevent) == frozenset({("pay", "")})
    assert behavior_signatures(confirm) == frozenset({("pay", "")})
    kept, findings = normalize_paraphrase_duplicates([prevent, confirm])
    assert prevent in kept
    assert confirm in kept
    assert not any(item["code"] == "PARAPHRASE_COLLAPSED" for item in findings)


def test_empty_object_equivalence_is_not_domain_specific():
    prevent = (
        "Prevent duplicate notice creation or duplicate notification processing "
        "when notification events are retried."
    )
    confirm = (
        "The system must send notification confirmation messages "
        "after successful notifications."
    )
    assert behavior_signatures(prevent) == behavior_signatures(confirm)
    assert ("notify", "") in behavior_signatures(prevent)
    kept, findings = normalize_paraphrase_duplicates([prevent, confirm])
    assert prevent in kept
    assert confirm in kept
    assert not any(item["code"] == "PARAPHRASE_COLLAPSED" for item in findings)


def test_unrecognized_statements_are_not_treated_as_equivalent():
    archive = "Archive closed warehouse bins at the end of the shift."
    reprint = "Reprint packing slips for the evening route."
    assert behavior_signatures(archive) == frozenset()
    assert behavior_signatures(reprint) == frozenset()
    kept, findings = normalize_paraphrase_duplicates([archive, reprint])
    assert kept == [archive, reprint]
    assert findings == []


def test_failed_payment_notification_and_retry_stay_independently_traceable():
    notify = "Notify customers when a payment fails."
    retry = "Provide a way for customers to retry payment upon failure."
    compound = (
        "The system must notify customers when a payment fails "
        "and provide a way to retry payment."
    )
    kept, findings = normalize_paraphrase_duplicates([notify, retry, compound])
    blob = " ".join(kept).lower()
    assert any("notify" in item.lower() and "retry" not in item.lower() for item in kept)
    assert any(item == retry or "retry" in item.lower() for item in kept)
    assert "notify" in blob and "retry" in blob
    assert not any(
        item["code"] == "PARAPHRASE_COLLAPSED" and "retry" in item.get("removed", "").lower()
        for item in findings
    )


def test_partially_recognized_compound_is_not_removed_for_one_covered_behavior():
    notify = "The system must notify crews when a route fails."
    compound = "Notify crews when a route fails and provide a way to retry the route."
    kept, findings = normalize_paraphrase_duplicates([notify, compound])
    blob = " ".join(kept).lower()
    assert "notify" in blob
    assert "retry" in blob
    assert compound in kept
    assert any(item["code"] == "AMBIGUOUS_OVERLAP" for item in findings)
    assert not any(item["code"] == "PARAPHRASE_COLLAPSED" for item in findings)


def test_migration_invalid_records_and_duplicates_stay_distinct():
    migrate = "Migrate existing membership records from a file."
    identify = "Identify invalid records and potential duplicates before importing."
    compound = (
        "The system must migrate existing membership records from a file, "
        "identifying invalid records and potential duplicates before importing."
    )
    kept, _findings = normalize_paraphrase_duplicates([migrate, identify, compound])
    blob = " ".join(kept).lower()
    assert "migrate" in blob
    assert "invalid" in blob
    assert "duplicate" in blob
    assert len(kept) >= 2
    assert identify in kept


def test_meaningful_signature_paraphrases_still_collapse():
    login = "The system shall allow customers to log in."
    auth = "Customer login and authentication workflows."
    kept, findings = normalize_paraphrase_duplicates([login, auth])
    assert len(kept) == 1
    assert findings[0]["code"] == "PARAPHRASE_COLLAPSED"
    assert ("authenticate", "") in behavior_signatures(kept[0])

    search = "The system shall allow members to search holdings."
    discovery = "Holding search and discovery workflows."
    kept, findings = normalize_paraphrase_duplicates([search, discovery])
    assert len(kept) == 1
    assert "search holdings" in kept[0].lower()
    assert findings[0]["code"] == "PARAPHRASE_COLLAPSED"
