"""Hard-deadline gap-closing analysis.

Starts from the AI-assisted scenario. Does not mutate the baseline estimate.
"""

from __future__ import annotations

import re

from app.agents import _parse_max_weeks
from app.assessment import standard_deadline_fit
from app.pnr import (
    assess_staffing,
    parse_effort_person_days,
    parse_headcount,
    parse_team_profile,
)
from app.state import DeliveryState
from app.timeline import deadline_source_texts, parse_requested_deadline

HARD_DEADLINE_MARKERS = (
    "hard deadline",
    "fixed deadline",
    "deadline is fixed",
    "deadline is hard",
    "fixed at",
    "hard/fixed",
    "hard and fixed",
    "cannot move",
    "cannot slip",
    "immovable",
    "non-negotiable",
    "non negotiable",
    "must launch",
    "must go live",
    "date is fixed",
    "fixed date",
    "hard date",
    "deadline cannot",
    "customer deadline is fixed",
)

GAP_CLOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "ways_to_close_gap": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "category": {"type": "string"},
                    "description": {"type": "string"},
                    "estimated_impact": {"type": "string"},
                    "pnr_assessment": {"type": "string"},
                },
            },
        },
        "recommended_scenarios": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "target_duration": {"type": "string"},
                    "team": {"type": "string"},
                    "main_changes": {"type": "string"},
                    "confidence": {"type": "string"},
                    "notes": {"type": "string"},
                },
            },
        },
        "conditions": {"type": "array", "items": {"type": "string"}},
        "tradeoffs": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "summary",
        "ways_to_close_gap",
        "recommended_scenarios",
        "conditions",
        "tradeoffs",
        "risks",
    ],
}

_CLOUD_PRODUCTS = re.compile(
    r"\b(?:AWS\s+)?OpenSearch(?:\s+Serverless)?\b|"
    r"\bAmazon\s+OpenSearch(?:\s+Serverless)?\b|"
    r"\bAzure\s+Cognitive\s+Search\b|"
    r"\bGoogle\s+Vertex\s+AI\s+Search\b|"
    r"\bVertex\s+AI\s+Search\b",
    re.I,
)
_CLOUD_VENDORS = re.compile(
    r"\b(?:AWS|Amazon Web Services|Microsoft Azure|Google Cloud Platform|"
    r"Google Cloud|GCP|Azure)\b",
    re.I,
)
_MANAGED_SEARCH_PHRASE = (
    "a managed search/ingestion service compatible with the customer's cloud "
    "and security constraints (requires validation)"
)
_NAIVE_PNR_SENTENCE = re.compile(
    r"[^.]*\b(?:materially above the pnr-optimal|adding more developers is unlikely|"
    r"ai-optimal team|above optimal|therefore adding developers)\b[^.]*\.?",
    re.I,
)


def _customer_authored_blob(state: dict) -> str:
    estimate = state.get("estimate") or {}
    texts = deadline_source_texts(
        user_request=str(state.get("user_request") or ""),
        discovery=state.get("discovery") or {},
        clarification_history=state.get("clarification_history"),
        clarification_answers=state.get("clarification_answers"),
    )
    parts = list(texts or [])
    parts.append(str(estimate.get("customer_deadline") or ""))
    return " ".join(str(item) for item in parts if item).lower()


def is_hard_deadline(state: dict) -> bool:
    blob = _customer_authored_blob(state)
    return any(marker in blob for marker in HARD_DEADLINE_MARKERS)


def _deadline_weeks(state: dict) -> float | None:
    estimate = state.get("estimate") or {}
    stored = estimate.get("customer_deadline_weeks")
    if isinstance(stored, (int, float)):
        return float(stored)
    sources = deadline_source_texts(
        user_request=str(state.get("user_request") or ""),
        discovery=state.get("discovery") or {},
        clarification_history=state.get("clarification_history"),
        clarification_answers=state.get("clarification_answers"),
    )
    parsed = parse_requested_deadline(sources)
    if parsed is not None:
        return parsed.weeks
    display = str(estimate.get("customer_deadline") or "")
    return _parse_max_weeks(display)


def ai_scenario_exceeds_deadline(state: dict) -> bool:
    opt = state.get("ai_optimization") or {}
    if not isinstance(opt, dict) or not str(opt.get("duration_range") or "").strip():
        return False
    deadline_weeks = _deadline_weeks(state)
    if deadline_weeks is None:
        return False
    ai_max = _parse_max_weeks(opt.get("duration_range") or "")
    if ai_max is not None:
        return ai_max > deadline_weeks + 1e-6
    gap = str(opt.get("deadline_gap") or "").strip()
    feasibility = str(opt.get("deadline_feasibility") or "").upper()
    return feasibility == "NOT_DEMONSTRATED" and gap not in {"", "0"}


def gap_closing_eligible(state: dict | None) -> bool:
    if not isinstance(state, dict):
        return False
    estimate = state.get("estimate") or {}
    if standard_deadline_fit(estimate) != "EXCEEDS":
        return False
    if _deadline_weeks(state) is None:
        return False
    if not is_hard_deadline(state):
        return False
    return ai_scenario_exceeds_deadline(state)


def remaining_gap_text(state: dict) -> str:
    weeks = remaining_gap_weeks(state)
    if weeks is None:
        opt = state.get("ai_optimization") or {}
        return str(opt.get("deadline_gap") or "").strip()
    if weeks <= 1e-6:
        return "0"
    return f"approximately {weeks:.1f} weeks"


def remaining_gap_weeks(state: dict) -> float | None:
    deadline_weeks = _deadline_weeks(state)
    opt = state.get("ai_optimization") or {}
    ai_max = _parse_max_weeks(opt.get("duration_range") or "")
    if deadline_weeks is None or ai_max is None:
        return None
    gap = ai_max - deadline_weeks
    return gap if gap > 1e-6 else 0.0


def _as_list(value) -> list:
    if not isinstance(value, list):
        return []
    return [item for item in value if item]


def _clean_ways(value) -> list[dict]:
    ways = []
    for item in _as_list(value):
        if isinstance(item, str) and item.strip():
            ways.append({
                "title": item.strip(),
                "category": "",
                "description": item.strip(),
                "estimated_impact": "",
            })
            continue
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        if not title and not description:
            continue
        ways.append({
            "title": title or description,
            "category": str(item.get("category") or "").strip().lower(),
            "description": description or title,
            "estimated_impact": str(item.get("estimated_impact") or "").strip(),
        })
    return ways


def _clean_scenarios(value) -> list[dict]:
    scenarios = []
    for item in _as_list(value):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        scenarios.append({
            "name": name,
            "target_duration": str(item.get("target_duration") or "").strip(),
            "team": str(item.get("team") or "").strip(),
            "main_changes": str(item.get("main_changes") or "").strip(),
            "confidence": str(item.get("confidence") or "LOW").strip(),
            "notes": str(item.get("notes") or "").strip(),
        })
    return scenarios


def sanitize_cloud_assumptions(text: str) -> str:
    """Do not present invented cloud vendors as the architecture."""
    raw = str(text or "")
    if not raw:
        return raw
    out = _CLOUD_PRODUCTS.sub(_MANAGED_SEARCH_PHRASE, raw)
    out = _CLOUD_VENDORS.sub("the customer's cloud", out)
    out = re.sub(r"(?:the customer's cloud(?:\s*/\s*|,?\s+or\s+|,?\s+and\s+|,?\s+)){2,}", "the customer's cloud / ", out)
    return out


def _walk_sanitize(value):
    if isinstance(value, str):
        return sanitize_cloud_assumptions(value)
    if isinstance(value, list):
        return [_walk_sanitize(item) for item in value]
    if isinstance(value, dict):
        return {key: _walk_sanitize(item) for key, item in value.items()}
    return value


def _current_team_blob(state: dict) -> str:
    discovery = state.get("discovery") or {}
    plan = state.get("delivery_plan") or {}
    estimate = state.get("estimate") or {}
    opt = state.get("ai_optimization") or {}
    parts = [
        state.get("user_request"),
        discovery.get("constraints"),
        discovery.get("assumptions"),
        plan.get("team_roles"),
        estimate.get("assumptions"),
        opt.get("optimization_team_model"),
    ]
    chunks = []
    for part in parts:
        if isinstance(part, list):
            chunks.extend(str(item) for item in part)
        elif part:
            chunks.append(str(part))
    return " ".join(chunks)


_LEVER_CONCEPTS = (
    ("ai_coding", re.compile(r"\b(?:ai coding|boilerplate|code gen(?:eration)?|coding assistance|copilot)\b", re.I)),
    ("test_generation", re.compile(r"\b(?:test generation|generate tests|ai tests?)\b", re.I)),
    ("parallelization", re.compile(r"\bparallel", re.I)),
    ("scope_reduction", re.compile(
        r"\b(?:scope reduction|reduced scope|mvp|phase 2|defer(?:ral)?|analytics to phase)\b",
        re.I,
    )),
    ("platform_reuse", re.compile(
        r"\b(?:rbac|reuse of existing|internal platform reuse|already-built)\b",
        re.I,
    )),
    ("managed_search", re.compile(
        r"\b(?:managed search|ingestion service|opensearch|cognitive search|vertex ai search)\b",
        re.I,
    )),
)
_GENERIC_MATCH_TOKENS = {
    "the", "and", "with", "from", "that", "this", "for", "into", "using",
    "a", "an", "of", "to", "in", "on", "or", "by", "as", "service", "services",
    "evaluate", "evaluation", "option", "compatible", "customer", "cloud",
    "existing", "additional", "delivery", "scenario", "week", "weeks", "impact",
    "development", "platform", "internal", "assistance", "optional", "reduce",
    "elapsed", "time", "independent", "estimate", "approach", "constraints",
    "security", "validate", "assumed", "architecture", "work", "first",
}
_ACHIEVEMENT_SENTENCE = re.compile(
    r"[^.]*\b(?:meets?|achieves?|will meet|successfully (?:meet|deliver|achieve)|"
    r"closes the (?:remaining )?gap and meets)\b[^.]*\bdeadline[^.]*\.?",
    re.I,
)


def _applied_ai_levers(state: dict) -> list[str]:
    opt = state.get("ai_optimization") or {}
    levers = []
    for key in ("optimization_levers", "recommendations", "scope_tradeoffs"):
        value = opt.get(key)
        if isinstance(value, list):
            levers.extend(str(item).strip() for item in value if str(item).strip())
        elif value:
            levers.append(str(value).strip())
    summary = str(opt.get("optimization_summary") or "").strip()
    if summary:
        levers.append(summary)
    return levers


def _matching_ai_levers(state: dict) -> list[str]:
    """Levers that can prove a gap-close item was already in the AI scenario."""
    opt = state.get("ai_optimization") or {}
    levers = []
    for key in ("optimization_levers", "scope_tradeoffs"):
        value = opt.get(key)
        if isinstance(value, list):
            levers.extend(str(item).strip() for item in value if str(item).strip())
        elif value:
            levers.append(str(value).strip())
    return levers


def _normalize_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return {token for token in tokens if token not in _GENERIC_MATCH_TOKENS and len(token) > 2}


def _lever_concepts(text: str) -> set[str]:
    blob = str(text or "")
    return {name for name, pattern in _LEVER_CONCEPTS if pattern.search(blob)}


def _item_blob(item: dict) -> str:
    return " ".join([
        str(item.get("title") or ""),
        str(item.get("category") or ""),
        str(item.get("description") or ""),
        str(item.get("main_changes") or ""),
    ])


def _is_ai_double_count(item: dict, applied_levers: list[str] | None = None) -> bool:
    blob = _item_blob(item).lower()
    if "already applied" in blob or "already included" in blob or "no additional" in blob:
        return False
    if "additional intervention" in blob and "not listed in the ai-assisted" in blob:
        return False
    markers = (
        "optimize with ai",
        "ai-assisted development to reduce",
        "apply ai acceleration",
        "rerun ai optimization",
    )
    if any(marker in blob for marker in markers):
        return True
    applied = list(applied_levers or [])
    item_concepts = _lever_concepts(blob)
    applied_concepts = set()
    for lever in applied:
        applied_concepts |= _lever_concepts(lever)
    shared = item_concepts & applied_concepts
    if shared:
        return True
    if "managed_search" in item_concepts and "managed_search" not in applied_concepts:
        return False
    coding_markers = ("ai coding", "generate boilerplate", "test generation", "generate tests with ai")
    if any(marker in blob for marker in coding_markers) and (
        "ai_coding" in applied_concepts or "test_generation" in applied_concepts
        or any(marker in " ".join(applied).lower() for marker in coding_markers)
    ):
        return True
    if not applied:
        return False
    way_tokens = _normalize_tokens(blob)
    if not way_tokens:
        return False
    for lever in applied:
        lever_tokens = _normalize_tokens(lever)
        if len(lever_tokens) < 4:
            continue
        overlap = way_tokens & lever_tokens
        if len(overlap) >= max(4, int(0.7 * len(lever_tokens))):
            return True
    return False


def _relabel_duplicate_ai_lever(item: dict) -> dict:
    note = (
        "Already incorporated in the AI-assisted scenario — no additional time "
        "savings from repeating this lever."
    )
    item["already_incorporated"] = True
    item["estimated_impact"] = "no additional savings (already in AI-assisted scenario)"
    description = str(item.get("description") or "").strip()
    if note.lower() not in description.lower():
        item["description"] = f"{description} {note}".strip()
    return item


def _label_additional_intervention(item: dict) -> dict:
    item["already_incorporated"] = False
    flag = (
        "Additional intervention — not listed in the AI-assisted scenario. "
        "Impact is uncertain and not guaranteed."
    )
    description = str(item.get("description") or "").strip()
    if "additional intervention" not in description.lower():
        item["description"] = f"{description} {flag}".strip()
    impact = str(item.get("estimated_impact") or "").strip()
    if (
        impact
        and "no additional" not in impact.lower()
        and "uncertain" not in impact.lower()
        and re.search(r"\d", impact)
    ):
        item["estimated_impact"] = f"{impact} possible additional (uncertain, not guaranteed)"
    return item


def not_demonstrated_target_note(customer_deadline: str) -> str:
    raw = str(customer_deadline or "").strip()
    match = re.search(r"(\d+(?:\.\d+)?)(?:\s*[-–]\s*(\d+(?:\.\d+)?))?\s*weeks?", raw, flags=re.I)
    if match:
        span = match.group(1) if not match.group(2) else f"{match.group(1)}–{match.group(2)}"
        labeled = f"{span}-week hard deadline"
        achievable = f"{span} weeks"
    elif raw:
        labeled = raw if "deadline" in raw.lower() else f"{raw} hard deadline"
        achievable = raw
    else:
        labeled = "hard customer deadline"
        achievable = "the hard deadline"
    return (
        f"Targets the {labeled} conditionally, but the available evidence does not yet "
        f"demonstrate that {achievable} is achievable."
    )


def _rewrite_deadline_achievement_claims(text: str, note: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return raw
    rewritten = _ACHIEVEMENT_SENTENCE.sub(note, raw)
    return re.sub(r"\s{2,}", " ", rewritten).strip()


def _apply_deadline_honesty(scenarios: list[dict], summary: str, customer_deadline: str) -> str:
    note = not_demonstrated_target_note(customer_deadline)
    summary = _rewrite_deadline_achievement_claims(summary, note)
    if re.search(r"\bmeets?\b.+\bdeadline", summary, flags=re.I):
        summary = _rewrite_deadline_achievement_claims(summary, note)
    for scenario in scenarios:
        for key in ("name", "main_changes", "notes"):
            scenario[key] = _rewrite_deadline_achievement_claims(scenario.get(key) or "", note)
        name = scenario.get("name") or ""
        if re.search(r"\bmeets?\b", name, flags=re.I):
            scenario["name"] = re.sub(r"\b[Mm]eets?\b", "Targets", name, count=1)
        notes = scenario.get("notes") or ""
        if "does not yet demonstrate" not in notes.lower():
            scenario["notes"] = (notes + " " + note).strip()
    if "does not yet demonstrate" not in summary.lower():
        summary = (summary + " " + note).strip()
    return summary


def _parse_impact_weeks(text: str) -> tuple[float, float] | None:
    raw = str(text or "").lower().replace("–", "-").replace("—", "-")
    if "no additional" in raw or "already" in raw and "ai-assisted" in raw:
        return (0.0, 0.0)
    if "limited" in raw and not re.search(r"\d", raw):
        return None
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", raw)]
    if not numbers:
        return None
    if len(numbers) == 1:
        return (numbers[0], numbers[0])
    return (min(numbers), max(numbers))


def combined_impact_note(ways: list[dict], gap_weeks: float | None) -> str:
    ranges = []
    for way in ways:
        parsed = _parse_impact_weeks(way.get("estimated_impact") or "")
        if parsed is None:
            continue
        if parsed == (0.0, 0.0):
            continue
        ranges.append(parsed)
    if not ranges:
        if gap_weeks:
            return (
                f"Lever impacts overlap and are not additive. Combined additional closure "
                f"should be judged against the remaining ~{gap_weeks:.1f}-week gap, with uncertainty."
            )
        return "Lever impacts overlap and are not additive; do not sum individual week estimates."
    naive_low = sum(item[0] for item in ranges)
    naive_high = sum(item[1] for item in ranges)
    cap = gap_weeks if gap_weeks and gap_weeks > 0 else naive_high
    combined_low = min(naive_low * 0.6, cap)
    combined_high = min(naive_high, cap)
    if combined_low > combined_high:
        combined_low = combined_high
    return (
        f"Individual lever estimates would naively sum to about {naive_low:.1f}–{naive_high:.1f} weeks, "
        f"but these effects overlap (scope cuts, reuse, simplification and parallelization can hit the "
        f"same critical path). Combined additional closure is approximately "
        f"{combined_low:.1f}–{combined_high:.1f} weeks"
        + (f" against a remaining ~{gap_weeks:.1f}-week gap" if gap_weeks else "")
        + "; exact addition is not justified."
    )


def _proposed_engineering_fte(text: str, current: float | None) -> float | None:
    raw = str(text or "")
    lower = raw.lower()
    if re.search(r"\bexisting team\b|\bcurrent team\b|\bno (?:team )?change\b", lower):
        return current
    add_match = re.search(
        r"\badd(?:ing)?\s+(\d+(?:\.\d+)?)\s+(?:additional\s+)?(?:software\s+)?(?:engineers?|developers?)\b",
        raw,
        flags=re.I,
    )
    if add_match:
        added = float(add_match.group(1))
        if current:
            return current + added
        return added
    profile = parse_team_profile(raw)
    if profile.get("engineering_fte") is not None:
        return profile["engineering_fte"]
    return parse_headcount(raw)


def _strip_pnr_terminology(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return raw
    cleaned = _NAIVE_PNR_SENTENCE.sub("", raw)
    cleaned = re.sub(
        r"[^.]*\b(?:PNR|Putnam|Norden-Rayleigh|C\s*=\s*2\.5)\b[^.]*\.?",
        "",
        cleaned,
        flags=re.I,
    )
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _staffing_plain_note(assessment: dict) -> str:
    if not assessment or not assessment.get("available"):
        return ""
    parts = []
    if assessment.get("current_team_size") is not None:
        parts.append(f"Current engineering team ≈ {assessment['current_team_size']:.1f} FTE.")
    if (
        assessment.get("proposed_team_size") is not None
        and assessment.get("direction") in {"increase", "decrease"}
    ):
        parts.append(f"Proposed engineering team ≈ {assessment['proposed_team_size']:.1f} FTE.")
    if assessment.get("direction") == "decrease":
        parts.append(
            "Reducing the current team is not required to close the remaining duration gap "
            "if work is capacity-bound."
        )
    elif assessment.get("overstaffed"):
        parts.append(
            "Adding people does not reduce duration linearly because of coordination, "
            "task dependencies and ramp-up."
        )
    return " ".join(parts)


def _apply_staffing(
    ways: list[dict],
    scenarios: list[dict],
    effort_days: float | None,
    deadline_weeks: float | None,
    current_headcount: float | None,
) -> dict:
    plan_assessment = assess_staffing(
        effort_days,
        deadline_weeks,
        current_headcount=current_headcount,
        proposed_headcount=current_headcount,
    )
    for way in ways:
        category = way.get("category") or ""
        blob = f"{way.get('title')} {way.get('description')} {category}"
        if category not in {"team", "capacity"} and "team" not in blob.lower() and "engineer" not in blob.lower():
            continue
        proposed = _proposed_engineering_fte(blob, current_headcount)
        assessment = assess_staffing(
            effort_days,
            deadline_weeks,
            proposed_headcount=proposed,
            current_headcount=current_headcount,
        )
        if assessment.get("available"):
            plan_assessment = assessment
    for scenario in scenarios:
        blob = f"{scenario.get('name')} {scenario.get('team')} {scenario.get('main_changes')}"
        if "team" not in blob.lower() and "engineer" not in blob.lower() and "developer" not in blob.lower():
            continue
        proposed = _proposed_engineering_fte(blob, current_headcount)
        assessment = assess_staffing(
            effort_days,
            deadline_weeks,
            proposed_headcount=proposed,
            current_headcount=current_headcount,
        )
        notes = _strip_pnr_terminology(scenario.get("notes") or "")
        extra = _staffing_plain_note(assessment)
        scenario["notes"] = notes
        if extra and extra not in notes:
            scenario["notes"] = (notes + " " + extra).strip()
        if assessment.get("available"):
            plan_assessment = assessment
    return plan_assessment


def _capacity_note(assessment: dict) -> str:
    if not assessment or not assessment.get("available"):
        return ""
    bits = []
    if assessment.get("implied_team_size") is not None:
        target = assessment.get("target_weeks")
        target_bit = f" ({target:.0f}-week target)" if target else ""
        bits.append(
            f"Deadline-implied average engineering capacity ≈ "
            f"{assessment['implied_team_size']:.2f} FTE{target_bit}."
        )
    if assessment.get("current_team_size") is not None:
        bits.append(f"Current engineering team ≈ {assessment['current_team_size']:.1f} FTE.")
    if bits:
        bits.append(
            "Adding people does not reduce duration linearly because of coordination, "
            "task dependencies and ramp-up."
        )
    return " ".join(bits)


def build_deadline_gap_plan(raw: dict, state: dict) -> dict:
    """Normalize model output into a consistent gap-close plan."""
    estimate = state.get("estimate") or {}
    opt = state.get("ai_optimization") or {}
    deadline_weeks = _deadline_weeks(state)
    gap = remaining_gap_text(state)
    gap_weeks = remaining_gap_weeks(state)
    customer_deadline = str(estimate.get("customer_deadline") or opt.get("customer_deadline") or "").strip()
    ai_duration = str(opt.get("duration_range") or "").strip()
    ai_effort = str(opt.get("effort_range") or "").strip()
    baseline = str(estimate.get("duration_range") or "").strip()
    applied = _applied_ai_levers(state)
    matching = _matching_ai_levers(state)
    current_profile = parse_team_profile(_current_team_blob(state))
    current_eng = current_profile.get("engineering_fte")

    ways = []
    for item in _clean_ways((raw or {}).get("ways_to_close_gap")):
        if _is_ai_double_count(item, matching):
            ways.append(_relabel_duplicate_ai_lever(item))
        else:
            ways.append(_label_additional_intervention(item))
    scenarios = []
    for item in _clean_scenarios((raw or {}).get("recommended_scenarios")):
        if _is_ai_double_count(item, matching):
            item["main_changes"] = (
                str(item.get("main_changes") or "").strip()
                + " Already-applied AI-assisted levers are not counted again."
            ).strip()
        scenarios.append(item)

    effort_days = parse_effort_person_days(ai_effort)
    staffing = _apply_staffing(ways, scenarios, effort_days, deadline_weeks, current_eng)
    overlap_note = combined_impact_note(ways, gap_weeks)
    if scenarios:
        notes = scenarios[0].get("notes") or ""
        if "overlap" not in notes.lower() and overlap_note not in notes:
            scenarios[0]["notes"] = (notes + " " + overlap_note).strip()

    def clean_strings(value):
        if not isinstance(value, list):
            return []
        return [_strip_pnr_terminology(str(item).strip()) for item in value if str(item).strip()]

    starts_note = (
        "Starts from the AI-assisted scenario. Acceleration already in that scenario "
        "(for example AI coding, test generation, reuse or parallelization named there) "
        "is not counted again unless a distinct additional intervention is specified."
    )
    implied = staffing.get("implied_team_size") if staffing else None
    capacity = _capacity_note(staffing)
    result = {
        "title": "How to achieve customer deadline",
        "human_decision_note": (
            "AI proposal / scenario — not a commitment. The Delivery Lead reviews, "
            "edits and decides whether any scenario is acceptable before a potential commitment."
        ),
        "starts_from": "ai_assisted_scenario",
        "customer_deadline": customer_deadline,
        "ai_assisted_duration": ai_duration,
        "ai_assisted_effort": ai_effort,
        "baseline_duration": baseline,
        "remaining_gap": gap,
        "summary": _strip_pnr_terminology(str((raw or {}).get("summary") or "").strip()) or (
            "Delivery changes that could close the remaining gap after AI-assisted development. "
            "This does not replace the independent estimate and does not create a commitment."
        ),
        "already_applied_ai_levers": applied,
        "double_count_note": starts_note,
        "combined_impact_note": overlap_note,
        "deadline_implied_capacity": (
            f"Deadline-implied average engineering capacity ≈ {implied:.2f} FTE"
            if implied is not None
            else ""
        ),
        "capacity_note": capacity,
        "ways_to_close_gap": ways,
        "recommended_scenarios": scenarios,
        "conditions": clean_strings((raw or {}).get("conditions")),
        "tradeoffs": clean_strings((raw or {}).get("tradeoffs") or (raw or {}).get("trade_offs")),
        "risks": clean_strings((raw or {}).get("risks")),
    }
    result["summary"] = _apply_deadline_honesty(
        result["recommended_scenarios"],
        result["summary"],
        customer_deadline,
    )
    for item in result["ways_to_close_gap"]:
        item["title"] = _strip_pnr_terminology(item.get("title") or "")
        item["description"] = _strip_pnr_terminology(item.get("description") or "")
        item.pop("pnr_assessment", None)
        item.pop("pnr", None)
    for item in result["recommended_scenarios"]:
        item["name"] = _strip_pnr_terminology(item.get("name") or "")
        item["team"] = _strip_pnr_terminology(item.get("team") or "")
        item["main_changes"] = _strip_pnr_terminology(item.get("main_changes") or "")
        item["notes"] = _strip_pnr_terminology(item.get("notes") or "")
        item.pop("pnr", None)
    return _walk_sanitize(result)


def deadline_gap_plan_agent(state: DeliveryState, provider) -> dict:
    if not gap_closing_eligible(state):
        return {}

    estimate = state.get("estimate") or {}
    opt = state.get("ai_optimization") or {}
    deadline_weeks = _deadline_weeks(state)
    gap = remaining_gap_text(state)
    customer_deadline = str(estimate.get("customer_deadline") or opt.get("customer_deadline") or "").strip()
    ai_duration = str(opt.get("duration_range") or "").strip()
    ai_effort = str(opt.get("effort_range") or "").strip()
    baseline = str(estimate.get("duration_range") or "").strip()
    applied = _applied_ai_levers(state)
    applied_text = "\n".join(f"- {item}" for item in applied) or "- (none listed)"
    current_blob = _current_team_blob(state) or "(not specified)"
    current_profile = parse_team_profile(current_blob)
    current_eng = current_profile.get("engineering_fte")
    staffing = assess_staffing(
        parse_effort_person_days(ai_effort),
        deadline_weeks,
        current_headcount=current_eng,
        proposed_headcount=current_eng,
    )
    capacity_context = _capacity_note(staffing) or "(capacity not numeric)"

    prompt = f"""
You are a senior Delivery Lead advisor.

The Delivery Lead asked: HOW TO ACHIEVE A HARD CUSTOMER DEADLINE.

This is NOT another AI-development optimization. Do not rerun "Optimize with AI".
Start from the AI-assisted scenario, not from the baseline.

HARD CUSTOMER DEADLINE: {customer_deadline}
BASELINE INDEPENDENT ESTIMATE (do not change this): {baseline}
AI-ASSISTED SCENARIO (starting point): {ai_duration}
AI-ASSISTED EFFORT: {ai_effort}
REMAINING GAP: {gap}

ALREADY INCLUDED IN THE AI-ASSISTED SCENARIO (do not claim extra weeks for the same thing):
{applied_text}

CURRENT TEAM EVIDENCE (do not invent a different current team):
{current_blob}

CAPACITY CONTEXT:
{capacity_context}

SCOPE / REQUIREMENTS:
{(state.get("requirements") or {})}

SOLUTION:
{(state.get("solution") or {})}

DELIVERY PLAN:
{(state.get("delivery_plan") or {})}

Propose a CREDIBLE COMBINATION that could close approximately the remaining gap.
Team changes are only one optional lever, not the default. Consider:
- scope reduction / MVP / phase 2
- reuse of existing capabilities
- technical simplification
- parallelization of independent work
- AI-assisted development ONLY if it is a distinct extra intervention beyond the list above
- team composition/capacity, with numbers

Rules:
- Distinguish current team, deadline-implied capacity (effort / target duration), and any proposed team.
- Distinguish levers already incorporated in the AI-assisted scenario from genuinely additional interventions.
- Do not claim extra weeks for AI coding, test generation, parallelization, scope reduction, or internal platform reuse if those already appear in the AI-assisted scenario.
- A managed search/ingestion service is additional only if it was not listed in the AI-assisted levers. Label it additional, keep conditions explicit, and do not invent a guaranteed impact.
- A target of the customer deadline is a proposed/conditional target, not demonstrated feasibility.
- Never say the hard deadline is met, achieved, or demonstrated when the AI-assisted scenario still exceeds it.
- Use wording equivalent to: targets the deadline conditionally, but the available evidence does not yet demonstrate that it is achievable.
- Do NOT recommend reducing the current team merely because a theoretical reference team is smaller.
- If you recommend reducing or adding engineers, give a quantitative delivery reason.
- Do not assume adding people is the answer. Adding people does not reduce duration linearly.
- Do not mention PNR, Putnam, C=2.5, or an optimal team formula.
- Lever week estimates overlap; do not imply they sum to more than the remaining gap.
- Do not name AWS, Azure, GCP, OpenSearch, Vertex, or Cognitive Search unless the customer named them. If suggesting managed search/ingestion, say to evaluate a service compatible with the customer's cloud and security constraints (requires validation).
- Return 1-2 coherent recommended_scenarios (not a dump of every lever), with target_duration and confidence.
- Do not invent precision. Do not claim the deadline is achieved just because a scenario exists.
- Do not change the baseline estimate.

Return ways_to_close_gap with title, category (scope|parallelization|technical|team),
description, estimated_impact.
Return recommended_scenarios with name, target_duration, team, main_changes, confidence, notes.
"""

    raw = provider.generate_json(prompt=prompt, schema=GAP_CLOSE_SCHEMA)
    if not isinstance(raw, dict):
        raw = {}
    return {"deadline_gap_plan": build_deadline_gap_plan(raw, state)}
