"""Putnam–Norden–Rayleigh (PNR) team-size heuristic.

T = C * E^0.33, N = E / T

E is total effort in person-months = person-days / 20.
C = 2.5 is the conventional (human) productivity factor from the
published methodology. This is a planning reference, not an AI-calibrated
curve and not a recommended team.
"""

from __future__ import annotations

import re

PNR_C = 2.5
PNR_EXPONENT = 0.33
PERSON_DAYS_PER_MONTH = 20.0
PNR_WEEKS_PER_MONTH = 4.0  # 20 working days / 5-day weeks
OVERSTAFF_RATIO = 1.3
UNDERSTAFF_RATIO = 0.7


def person_days_to_person_months(person_days: float) -> float:
    return float(person_days) / PERSON_DAYS_PER_MONTH


def weeks_to_months(weeks: float) -> float:
    return float(weeks) / PNR_WEEKS_PER_MONTH


def optimal_duration_months(effort_person_months: float, c: float = PNR_C) -> float:
    effort = max(float(effort_person_months), 1e-6)
    return float(c) * (effort ** PNR_EXPONENT)


def optimal_team_size(effort_person_months: float, c: float = PNR_C) -> float:
    duration = optimal_duration_months(effort_person_months, c=c)
    return effort_person_months / duration


def implied_team_size(effort_person_months: float, target_weeks: float) -> float | None:
    months = weeks_to_months(target_weeks)
    if months <= 1e-6:
        return None
    return effort_person_months / months


def midpoint_from_range(text: str) -> float | None:
    raw = str(text or "").lower().replace("–", "-").replace("—", "-")
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", raw)]
    if not numbers:
        return None
    if len(numbers) == 1:
        return numbers[0]
    return (min(numbers) + max(numbers)) / 2.0


def parse_effort_person_days(text: str) -> float | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    value = midpoint_from_range(raw)
    if value is None:
        return None
    lower = raw.lower()
    if re.search(r"person[- ]?hours?|\bhours?\b", lower) and "person-day" not in lower:
        return value / 8.0
    return value


def parse_team_profile(text: str) -> dict:
    """Extract engineering / QA / tech-lead FTE from free text when present."""
    raw = str(text or "")
    engineers = None
    qa = None
    tech_lead = None
    eng_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:fte\s+)?(?:software\s+)?(?:engineers?|developers?)\b",
        raw,
        flags=re.I,
    )
    if eng_match:
        engineers = float(eng_match.group(1))
    qa_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:fte\s+)?qa(?:\s+engineers?)?\b", raw, flags=re.I)
    if qa_match:
        qa = float(qa_match.group(1))
    lead_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:fte\s+)?(?:tech(?:nical)?\s*leads?|team\s*leads?)\b",
        raw,
        flags=re.I,
    )
    if lead_match:
        tech_lead = float(lead_match.group(1))
    total = sum(value for value in (engineers, qa, tech_lead) if value is not None)
    return {
        "engineers": engineers,
        "qa": qa,
        "tech_lead": tech_lead,
        "engineering_fte": engineers,
        "total_fte": total or None,
    }


def parse_headcount(text: str) -> float | None:
    profile = parse_team_profile(text)
    if profile.get("engineering_fte"):
        return profile["engineering_fte"]
    raw = str(text or "")
    match = re.search(
        r"\b(?:add(?:ing)?|increase(?: to)?|team of|headcount)\s+(\d+(?:\.\d+)?)",
        raw,
        flags=re.I,
    )
    if match:
        return float(match.group(1))
    return None


def staffing_stance(compared: float | None, n_opt: float | None) -> str:
    if not compared or not n_opt:
        return "unknown"
    if compared > n_opt * OVERSTAFF_RATIO:
        return "above"
    if compared < n_opt * UNDERSTAFF_RATIO:
        return "below"
    return "near"


def assess_staffing(
    effort_person_days: float | None,
    target_weeks: float | None,
    proposed_headcount: float | None = None,
    current_headcount: float | None = None,
) -> dict:
    """Conventional PNR reference vs deadline-implied capacity (gap-close only)."""
    if not effort_person_days or effort_person_days <= 0:
        return {
            "available": False,
            "overstaffed": False,
            "stance": "unknown",
            "direction": "unchanged",
            "c": PNR_C,
            "summary": "PNR team-size analysis is not available because effort is not numeric.",
        }
    effort_pm = person_days_to_person_months(effort_person_days)
    t_ref = optimal_duration_months(effort_pm)
    n_ref = optimal_team_size(effort_pm)
    n_implied = implied_team_size(effort_pm, target_weeks) if target_weeks else None
    compared = proposed_headcount if proposed_headcount is not None else current_headcount
    if compared is None:
        compared = n_implied
    stance = staffing_stance(compared, n_ref)
    direction = "unchanged"
    if current_headcount and proposed_headcount:
        if proposed_headcount > current_headcount + 0.2:
            direction = "increase"
        elif proposed_headcount < current_headcount - 0.2:
            direction = "decrease"
    specific_proposal = proposed_headcount is not None and (
        current_headcount is None or abs(proposed_headcount - current_headcount) > 0.2
    )
    overstaffed = (
        specific_proposal
        and direction != "decrease"
        and staffing_stance(proposed_headcount, n_ref) == "above"
    )

    parts = [
        f"AI-assisted effort ≈ {effort_person_days:.0f} person-days "
        f"({effort_pm:.1f} person-months; E = person-days / 20).",
    ]
    if target_weeks and n_implied is not None:
        parts.append(
            f"Deadline-implied average engineering capacity ≈ {n_implied:.2f} FTE "
            f"({target_weeks:.0f}-week target; E / target duration — not a PNR result)."
        )
    parts.append(
        f"Conventional PNR reference (C={PNR_C:g}): ≈ {n_ref:.1f} FTE / ~{t_ref:.1f} months. "
        "This is a conventional PNR reference / planning heuristic (C=2.5). "
        "It is not an AI-optimal team, not the recommended team, not proof that the "
        "current team is too large, and not an AI productivity model."
    )
    if current_headcount:
        parts.append(f"Current engineering team ≈ {current_headcount:.1f} FTE.")
    if proposed_headcount is not None and (
        current_headcount is None or abs(proposed_headcount - (current_headcount or 0)) > 0.05
    ):
        parts.append(f"Proposed engineering team ≈ {proposed_headcount:.1f} FTE.")
    parts.append(
        "PNR interpretation: the PNR reference indicates the conventional schedule/team-size "
        "trade-off for this effort. Achieving a hard deadline often requires schedule compression "
        "and/or additional effective capacity. Adding people does not reduce duration linearly "
        "because of coordination, task dependencies and ramp-up. The Delivery Lead decides "
        "which combination of scope, parallelization, simplification, capacity and already-achieved "
        "AI acceleration is acceptable."
    )
    if direction == "decrease":
        parts.append(
            "A lower conventional PNR reference than the current team is not a reason to reduce "
            "staffing. Shrinking the team does not close a remaining duration gap if work is "
            "capacity-bound."
        )
    elif overstaffed:
        parts.append(
            "This specific proposed staffing increase is well above the conventional PNR "
            "reference (C=2.5) for this effort, so extra headcount is unlikely to close the "
            "remaining gap linearly."
        )
    return {
        "available": True,
        "c": PNR_C,
        "effort_person_days": effort_person_days,
        "effort_person_months": round(effort_pm, 2),
        "target_weeks": target_weeks,
        "optimal_duration_months": round(t_ref, 2),
        "pnr_reference_duration_months": round(t_ref, 2),
        "pnr_optimal_team_size": round(n_ref, 2),
        "pnr_reference_team_size": round(n_ref, 2),
        "implied_team_size": None if n_implied is None else round(n_implied, 2),
        "current_team_size": current_headcount,
        "proposed_team_size": proposed_headcount,
        "stance": stance,
        "direction": direction,
        "overstaffed": overstaffed,
        "summary": " ".join(parts),
    }
