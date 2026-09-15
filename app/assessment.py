"""Deterministic verdict and one-page assessment from workflow state.

All content is derived from existing artifacts. Empty fields stay empty
rather than being filled with invented narrative.
"""

from __future__ import annotations

from app.evidence import (
    customer_authored_text,
    is_numeric_duration,
    material_evidence_gaps,
    statement_is_explicit,
)
from app.risks import normalize_delivery_risks
from app.timeline import deadline_source_texts, parse_requested_deadline

ESTIMATE_DISCLAIMER = (
    "Indicative estimate — based on the information provided, not a delivery "
    "commitment or quote. Use it to support a delivery decision, not as a "
    "contractual forecast."
)

ASSESSMENT_DISCLAIMER = (
    "This is an independent feasibility assessment based only on the information "
    "provided. It is not a delivery commitment, commercial quote, or statistically "
    "calibrated forecast."
)

STANDARD_DEADLINE_FIT_VALUES = ("FITS", "EXCEEDS", "NOT_DEMONSTRATED")


def standard_deadline_fit(estimate: dict | None) -> str:
    """Return the canonical standard-estimate deadline assessment."""
    if not isinstance(estimate, dict):
        return "NOT_DEMONSTRATED"
    fit = str(estimate.get("standard_deadline_fit") or "").strip().upper()
    if fit in STANDARD_DEADLINE_FIT_VALUES:
        return fit
    return "NOT_DEMONSTRATED"


def deadline_honesty_timeline(estimate: dict | None) -> str:
    """Build a proposal/SOW timeline that cannot imply a fake commitment."""
    estimate = estimate or {}
    fit = standard_deadline_fit(estimate)
    customer = str(estimate.get("customer_deadline") or "").strip() or "not provided"
    baseline = str(
        estimate.get("baseline_duration_range")
        or estimate.get("duration_range")
        or ""
    ).strip() or "not demonstrated"

    if estimate.get("not_yet_estimable") or not is_numeric_duration(baseline):
        return (
            f"Customer target: {customer}; independent indicative estimate: not yet estimable. "
            "Deadline assessment: NOT DEMONSTRATED. A numeric delivery range is not "
            "responsible until the missing material evidence is provided."
        )
    if fit == "FITS":
        return (
            f"Customer target: {customer}; independent indicative estimate: {baseline}. "
            "The independent estimate does not exceed the stated target. "
            "This remains an indicative assessment, not a delivery commitment."
        )
    if fit == "EXCEEDS":
        return (
            f"Customer target: {customer}; independent indicative estimate: {baseline}. "
            "Deadline assessment: EXCEEDS. The requested date is not supported by the "
            "independent estimate and must not be treated as a delivery commitment."
        )
    return (
        f"Customer target: {customer}; independent indicative estimate: {baseline}. "
        "Deadline assessment: NOT DEMONSTRATED. There is not enough evidence to treat "
        "the requested date as achievable."
    )


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _question_text(item) -> str:
    if isinstance(item, dict):
        return str(item.get("question") or item.get("text") or "").strip()
    return str(item or "").strip()


def _unique_texts(items, limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = _question_text(item) if not isinstance(item, str) else item.strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if limit is not None and len(result) >= limit:
            break
    return result


def build_verdict(result: dict) -> dict:
    """Derive the executive verdict from workflow status and deadline fit."""
    status = str(result.get("workflow_status") or result.get("status") or "").upper()
    review = result.get("delivery_review") or {}
    validation = result.get("validation") or {}
    estimate = result.get("estimate") or {}
    fit = standard_deadline_fit(estimate) if estimate else ""

    if status == "BLOCKED" or str(review.get("status") or "").upper() == "BLOCKED":
        code = "BLOCKED"
        label = "Blocked"
        summary = (
            "The delivery package did not pass the quality gate. Resolve the blocking "
            "issues before treating this as a feasible commitment."
        )
    elif (
        status == "NEEDS_INFO"
        or result.get("awaiting_customer")
        or str(validation.get("status") or "").upper() == "NEEDS_INFO"
    ):
        code = "NEEDS_INFORMATION"
        label = "Needs information"
        summary = (
            "There is not yet enough information for a responsible numeric estimate. "
            "Answer the required questions first. Independent estimate: not yet estimable."
        )
    elif estimate and fit == "EXCEEDS":
        code = "DEADLINE_AT_RISK"
        label = "Deadline at risk"
        summary = (
            "An independent estimate is available, but it exceeds the requested deadline. "
            "Do not treat the date as a commitment without scope, sequence, or capacity changes."
        )
    elif estimate and fit == "FITS":
        code = "DEADLINE_FIT"
        label = "Ready — deadline fit"
        summary = (
            "There is enough information for a preliminary assessment, and the independent "
            "estimate does not exceed the requested deadline. This is still indicative, not a quote."
        )
    elif estimate and fit == "NOT_DEMONSTRATED":
        code = "DEADLINE_UNCLEAR"
        label = "Deadline not demonstrated"
        summary = (
            "A preliminary assessment is available, but the requested deadline cannot be "
            "shown as achievable from the current evidence."
        )
    elif status in {"COMPLETE", "READY"}:
        code = "READY"
        label = "Assessment complete"
        summary = "A preliminary delivery assessment is available from the information provided."
    else:
        code = status or "UNKNOWN"
        label = (status or "Unknown").replace("_", " ").title()
        summary = "Review the artifacts below for the current assessment."

    return {
        "code": code,
        "label": label,
        "summary": summary,
        "workflow_status": status or "UNKNOWN",
        "standard_deadline_fit": fit or None,
    }


def _explicit_known_facts(result: dict) -> tuple[list[str], list[str]]:
    """Split discovery into customer-supported facts vs inferences."""
    discovery = result.get("discovery") or {}
    estimate = result.get("estimate") or {}
    source = customer_authored_text(result)
    known: list[str] = []
    inferred: list[str] = []

    request = str(result.get("user_request") or "").strip()
    if request:
        known.append(request if len(request) < 240 else request[:237] + "…")

    for item in _as_list(discovery.get("users"))[:4]:
        label = f"Users: {item}"
        if statement_is_explicit(item, source):
            known.append(label)
        else:
            inferred.append(f"Inferred user group not explicit in the request: {item}")

    for item in _as_list(discovery.get("existing_systems"))[:4]:
        label = f"System: {item}"
        if statement_is_explicit(item, source):
            known.append(label)
        else:
            inferred.append(f"Inferred system not explicit in the request: {item}")

    for item in _as_list(discovery.get("constraints"))[:4]:
        if statement_is_explicit(item, source) or item.lower().startswith("target delivery"):
            known.append(item)
        else:
            inferred.append(f"Unconfirmed constraint: {item}")

    deadline = str(estimate.get("customer_deadline") or "").strip()
    if deadline:
        known.append(f"Requested deadline: {deadline}")
    customer_est = str(estimate.get("customer_baseline_duration") or "").strip()
    if customer_est:
        known.append(f"Customer estimate: {customer_est}")

    return _unique_texts(known, limit=6), _unique_texts(inferred, limit=5)


def _recommended_next_steps(result: dict, verdict: dict, blocking, deadline: dict) -> list[str]:
    blocking_text = [_question_text(item) for item in _as_list(blocking)]
    requested = str(deadline.get("requested") or "").strip()
    independent = str(deadline.get("independent_estimate") or "").strip()
    gaps = material_evidence_gaps(result)
    steps: list[str] = []

    if verdict["code"] == "NEEDS_INFORMATION":
        primary = blocking_text[0] if blocking_text else (gaps[0].question if gaps else "")
        if requested and gaps and gaps[0].code == "first_release_scope":
            steps.append(
                f"Define the first-release scope and acceptance criteria before committing to the {requested} date."
            )
        elif requested and "migra" in (primary or "").lower():
            steps.append(
                f"Confirm whether the {requested} date requires the full migration, or whether a critical subset can be phased."
            )
        elif primary:
            steps.append(primary.rstrip("?") + ".")
        else:
            steps.append("Answer the required clarification questions before producing a numeric estimate.")
        if requested:
            steps.append(f"Keep the {requested} date visible, but do not treat it as demonstrated until the estimate is responsible.")
        if len(blocking_text) > 1:
            steps.append(blocking_text[1].rstrip("?") + ".")
        return steps[:3]

    if verdict["code"] == "BLOCKED":
        return ["Resolve the delivery-review blocking issues before issuing a proposal."]

    if verdict["code"] == "DEADLINE_AT_RISK":
        steps.append(
            f"Treat the requested date as at risk: independent estimate is {independent or 'longer'} vs requested {requested or 'date'}. "
            "Decide whether to reduce first-release scope, change sequencing, or move the date."
        )
        steps.append("If useful, run the optional AI-assisted scenario — it is not a guaranteed acceleration.")
        return steps[:3]

    if verdict["code"] == "DEADLINE_UNCLEAR":
        if not requested:
            steps.append("If a date matters to the decision, provide an explicit deadline so fit can be assessed against the independent estimate.")
        else:
            steps.append(
                f"The {requested} date cannot be demonstrated from the current independent estimate. Close the largest evidence gap before committing."
            )
        return steps[:3]

    steps.append("Review the independent estimate, risks, and proposal draft with the delivery owner.")
    if not (result.get("ai_optimization") or {}):
        steps.append(
            "Optionally run AI optimization as a separate scenario; it does not replace the independent estimate."
        )
    return steps[:3]


def build_assessment(result: dict) -> dict:
    """Build the structured one-page assessment from workflow artifacts only."""
    discovery = result.get("discovery") or {}
    requirements = result.get("requirements") or {}
    solution = result.get("solution") or {}
    plan = result.get("delivery_plan") or {}
    estimate = result.get("estimate") or {}
    optimization = result.get("ai_optimization") or {}
    validation = result.get("validation") or {}
    verdict = build_verdict(result)

    known, inferred = _explicit_known_facts(result)

    uncertain = _unique_texts(
        [
            *inferred,
            *_as_list(validation.get("missing_evidence")),
            *_as_list(discovery.get("unknowns")),
            *_as_list(requirements.get("open_questions")),
            *_as_list(validation.get("non_blocking_questions")),
        ],
        limit=6,
    )

    independent = str(
        estimate.get("baseline_duration_range") or estimate.get("duration_range") or ""
    ).strip()
    needs_info = verdict["code"] == "NEEDS_INFORMATION"
    if needs_info or estimate.get("not_yet_estimable") or not is_numeric_duration(independent):
        if needs_info or estimate.get("not_yet_estimable") or not independent:
            independent = "Not yet estimable"

    customer_deadline = str(estimate.get("customer_deadline") or "").strip()
    if not customer_deadline:
        requested = parse_requested_deadline(
            deadline_source_texts(
                user_request=str(result.get("user_request") or ""),
                discovery=discovery,
                clarification_history=result.get("clarification_history"),
                clarification_answers=result.get("clarification_answers"),
            )
        )
        if requested is not None:
            customer_deadline = requested.display

    fit = ""
    if estimate and not needs_info and is_numeric_duration(
        str(estimate.get("duration_range") or "")
    ):
        fit = standard_deadline_fit(estimate)
    elif customer_deadline and (needs_info or not is_numeric_duration(independent)):
        fit = "NOT_DEMONSTRATED"

    deadline = {
        "requested": customer_deadline,
        "independent_estimate": independent,
        "customer_estimate": str(estimate.get("customer_baseline_duration") or "").strip(),
        "fit": fit,
        "gap": (
            "Independent estimate exceeds the requested deadline."
            if verdict["code"] == "DEADLINE_AT_RISK"
            else (
                str(optimization.get("deadline_gap") or "")
                if str(optimization.get("deadline_gap") or "") not in {"", "0"}
                else ""
            )
        ),
        "effort": str(estimate.get("baseline_effort_range") or estimate.get("effort_range") or "").strip(),
        "confidence": str(estimate.get("confidence") or "").strip(),
    }

    evidence = ""
    if customer_deadline and is_numeric_duration(independent):
        evidence = f"Independent estimate is {independent} vs requested {customer_deadline}."
    risks = normalize_delivery_risks(
        [
            *_as_list(solution.get("delivery_risks")),
            *_as_list(plan.get("delivery_risks")),
            *_as_list(estimate.get("risks_affecting_estimate")),
        ],
        deadline_fit=fit,
        evidence=evidence,
        limit=5,
    )

    blocking = result.get("blocking_questions") or validation.get("blocking_questions") or []
    recommended = (
        result.get("non_blocking_questions")
        or validation.get("non_blocking_questions")
        or []
    )
    ask_next = _unique_texts([*_as_list(blocking), *_as_list(recommended)], limit=5)
    next_steps = _recommended_next_steps(result, verdict, blocking, deadline)

    why = _unique_texts(
        [
            verdict.get("summary") or "",
            *_as_list(validation.get("missing_evidence"))[:2],
            evidence,
        ],
        limit=3,
    )

    return {
        "title": "AI Delivery Assessment",
        "verdict": verdict,
        "request": str(result.get("user_request") or "").strip(),
        "problem": str(discovery.get("problem") or "").strip(),
        "business_goal": str(discovery.get("business_goal") or "").strip(),
        "deadline": deadline,
        "what_we_know": known,
        "what_is_uncertain": uncertain,
        "risks": risks,
        "why": why,
        "ask_next": ask_next,
        "delivery_options": {
            "standard": independent,
            "ai_assisted": str((optimization or {}).get("duration_range") or "").strip(),
            "ai_summary": str((optimization or {}).get("optimization_summary") or "").strip(),
            "ai_feasibility": str((optimization or {}).get("deadline_feasibility") or "").strip(),
            "ai_conditions": _as_list((optimization or {}).get("feasibility_conditions"))[:3],
        },
        "recommended_next_step": next_steps,
        "disclaimer": ASSESSMENT_DISCLAIMER,
        "estimate_disclaimer": ESTIMATE_DISCLAIMER,
    }


def format_assessment_text(assessment: dict) -> str:
    """Plain-text one-pager suitable for copy/paste."""
    verdict = assessment.get("verdict") or {}
    deadline = assessment.get("deadline") or {}
    options = assessment.get("delivery_options") or {}

    def section(title: str, lines: list[str]) -> str:
        body = "\n".join(f"- {line}" for line in lines if line) or "- None identified from the current artifacts."
        return f"{title}\n{body}"

    parts = [
        "AI DELIVERY ASSESSMENT",
        "",
        "REQUEST / PROJECT",
        assessment.get("problem") or assessment.get("request") or "Not provided",
    ]
    if assessment.get("business_goal"):
        parts.append(f"Business goal: {assessment['business_goal']}")
    parts.extend(
        [
            "",
            "EXECUTIVE VERDICT",
            f"{verdict.get('label') or 'Unknown'}",
            verdict.get("summary") or "",
            "",
            "DEADLINE",
            f"- Requested deadline: {deadline.get('requested') or 'Not provided'}",
            f"- Independent estimate: {deadline.get('independent_estimate') or 'Not yet produced'}",
            f"- Customer estimate: {deadline.get('customer_estimate') or 'Not provided'}",
            f"- Deadline fit: {deadline.get('fit') or 'Not assessed'}",
            f"- Gap: {deadline.get('gap') or 'None identified'}",
            "",
            section("WHAT WE KNOW", assessment.get("what_we_know") or []),
            "",
            section("WHAT IS STILL UNCERTAIN", assessment.get("what_is_uncertain") or []),
            "",
            section("TOP DELIVERY RISKS", assessment.get("risks") or []),
            "",
            section("WHAT WE WOULD ASK NEXT", assessment.get("ask_next") or []),
            "",
            "DELIVERY OPTIONS",
            f"- Standard approach: {options.get('standard') or 'Not yet produced'}",
            f"- Optional AI-assisted scenario: {options.get('ai_assisted') or 'Not run'}",
        ]
    )
    if options.get("ai_feasibility"):
        parts.append(
            f"- AI scenario feasibility: {options['ai_feasibility']} (optional, not guaranteed)"
        )
    parts.extend(
        [
            "",
            section("RECOMMENDED NEXT STEP", assessment.get("recommended_next_step") or []),
            "",
            "DISCLAIMER",
            assessment.get("disclaimer") or ASSESSMENT_DISCLAIMER,
        ]
    )
    return "\n".join(parts).strip() + "\n"


def format_print_assessment(assessment: dict) -> str:
    """Compact executive print/share text intended to fit one page."""
    verdict = assessment.get("verdict") or {}
    deadline = assessment.get("deadline") or {}
    options = assessment.get("delivery_options") or {}

    def bullets(items, empty="None identified"):
        lines = [f"- {item}" for item in (items or []) if item][:3]
        return "\n".join(lines) if lines else f"- {empty}"

    why = assessment.get("why") or []
    if not why:
        why = [verdict.get("summary") or ""][:1]

    parts = [
        "AI DELIVERY ASSESSMENT",
        "",
        "VERDICT",
        verdict.get("label") or "Unknown",
        "",
        "DEADLINE",
        f"- Requested deadline: {deadline.get('requested') or 'Not provided'}",
        f"- Independent estimate: {deadline.get('independent_estimate') or 'Not yet estimable'}",
        f"- Customer estimate: {deadline.get('customer_estimate') or 'Not provided'}",
        f"- Deadline fit: {deadline.get('fit') or 'Not assessed'}",
        "",
        "WHY",
        bullets(why),
        "",
        "TOP RISKS",
        bullets(assessment.get("risks"), "None identified"),
        "",
        "WHAT'S UNCERTAIN",
        bullets(assessment.get("what_is_uncertain"), "None identified"),
        "",
    ]
    if options.get("ai_assisted"):
        parts.extend(
            [
                "OPTIONAL AI-ASSISTED SCENARIO",
                f"- Duration: {options.get('ai_assisted')}",
                f"- Feasibility: {options.get('ai_feasibility') or 'Not assessed'} (not guaranteed)",
                "",
            ]
        )
    parts.extend(
        [
            "RECOMMENDED NEXT STEP",
            bullets(assessment.get("recommended_next_step"), "Review the assessment."),
            "",
            "DISCLAIMER",
            assessment.get("disclaimer") or ASSESSMENT_DISCLAIMER,
        ]
    )
    return "\n".join(parts).strip() + "\n"


def format_print_assessment_html(assessment: dict) -> str:
    """Compact HTML for browser print. Interactive UI is unchanged."""
    text = format_print_assessment(assessment)
    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f"<pre class=\"print-assessment\">{escaped}</pre>"
