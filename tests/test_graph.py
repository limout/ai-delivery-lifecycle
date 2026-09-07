from app.graph import route_after_delivery_review, route_after_validation


def question(text, priority, blocks):
    return {
        "question": text,
        "priority": priority,
        "reason": "test reason",
        "blocks_workflow": blocks,
    }


def test_required_question_blocks_validation():
    state = {
        "validation": {
            "status": "NEEDS_INFO",
            "questions": [
                question("Who are the primary users?", "REQUIRED", True),
            ],
            "blocking_questions": [
                question("Who are the primary users?", "REQUIRED", True),
            ],
        }
    }

    assert route_after_validation(state) == "needs_info"


def test_recommended_question_does_not_block_validation():
    state = {
        "validation": {
            "status": "READY",
            "questions": [
                question("What is the expected user volume?", "RECOMMENDED", False),
            ],
            "blocking_questions": [],
        }
    }

    assert route_after_validation(state) == "ready"


def test_optional_question_does_not_block_validation():
    state = {
        "validation": {
            "status": "READY",
            "questions": [
                question("What branding should the portal use?", "OPTIONAL", False),
            ],
            "blocking_questions": [],
        }
    }

    assert route_after_validation(state) == "ready"


def test_required_and_non_blocking_questions_only_block_for_required():
    required = question("Which identity provider is required?", "REQUIRED", True)
    recommended = question("What is expected user volume?", "RECOMMENDED", False)
    optional = question("What branding is preferred?", "OPTIONAL", False)

    state = {
        "validation": {
            "status": "NEEDS_INFO",
            "questions": [required, recommended, optional],
            "blocking_questions": [required],
        }
    }

    assert route_after_validation(state) == "needs_info"


def test_needs_info_without_blocking_questions_does_not_stop_graph():
    state = {
        "validation": {
            "status": "NEEDS_INFO",
            "questions": [
                question("What support categories are preferred?", "RECOMMENDED", False),
            ],
            "blocking_questions": [],
        }
    }

    assert route_after_validation(state) == "ready"


def test_review_ready_continues():
    assert route_after_delivery_review({"delivery_review": {"status": "READY"}}) == "ready"


def test_review_blocked_stops():
    assert route_after_delivery_review({"delivery_review": {"status": "BLOCKED"}}) == "review_blocked"
