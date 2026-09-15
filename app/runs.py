"""Short-lived in-memory run store for concierge-beta clarification resume.

Not a database. Runs expire after 24 hours so a clarify request can reuse
Discovery/Requirements without repeating those LLM calls.
"""

from __future__ import annotations

import copy
import threading
import time
import uuid

TTL_SECONDS = 24 * 60 * 60
_LOCK = threading.Lock()
_RUNS: dict[str, dict] = {}

ARTIFACT_KEYS = (
    "user_request",
    "discovery",
    "requirements",
    "validation",
    "solution",
    "delivery_plan",
    "estimate",
    "ai_optimization",
    "delivery_review",
    "proposal",
    "sow",
    "clarification_history",
    "clarification_questions",
    "blocking_questions",
    "non_blocking_questions",
    "iteration",
    "workflow_status",
    "current_stage",
)


def new_run_id() -> str:
    return str(uuid.uuid4())


def save_run(run_id: str, state: dict) -> None:
    if not run_id:
        return
    snapshot = {key: copy.deepcopy(state.get(key)) for key in ARTIFACT_KEYS if key in state}
    with _LOCK:
        _gc_locked()
        _RUNS[run_id] = {"saved_at": time.time(), "state": snapshot}


def get_run(run_id: str | None) -> dict | None:
    if not run_id:
        return None
    with _LOCK:
        _gc_locked()
        item = _RUNS.get(run_id)
        if not item:
            return None
        return copy.deepcopy(item["state"])


def artifacts_from_payload(payload: dict | None) -> dict:
    """Accept a previous workflow_response as resume input."""
    if not isinstance(payload, dict):
        return {}
    return {
        key: copy.deepcopy(payload[key])
        for key in ARTIFACT_KEYS
        if payload.get(key) not in (None, [], {})
    }


def _gc_locked() -> None:
    now = time.time()
    expired = [
        key for key, item in _RUNS.items()
        if now - item.get("saved_at", 0) > TTL_SECONDS
    ]
    for key in expired:
        _RUNS.pop(key, None)
