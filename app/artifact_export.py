"""Plain-text export for copy/print of individual delivery artifacts.

Formatting only. Does not change workflow, estimates, or gates.
"""

from __future__ import annotations


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _has_artifact(value) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    return any(
        item not in (None, "", [], {})
        for item in value.values()
    )


def _section(title: str, value) -> str:
    if isinstance(value, list):
        lines = [f"- {item}" for item in _as_list(value)]
        body = "\n".join(lines)
    else:
        body = str(value or "").strip()
    if not body:
        return ""
    return f"{title}\n{body}"


def _join(parts: list[str]) -> str:
    return "\n\n".join(part for part in parts if part).strip() + ("\n" if any(parts) else "")


def format_solution_text(solution: dict | None) -> str:
    if not _has_artifact(solution):
        return ""
    return _join(
        [
            "SOLUTION",
            _section("Summary", solution.get("solution_summary")),
            _section("Key capabilities", solution.get("key_capabilities")),
            _section("Integration approach", solution.get("integration_approach")),
            _section("Technical considerations", solution.get("technical_considerations")),
            _section("Delivery risks", solution.get("delivery_risks")),
            _section("Dependencies", solution.get("dependencies")),
            _section("Assumptions", solution.get("assumptions")),
        ]
    )


def format_delivery_plan_text(plan: dict | None) -> str:
    if not _has_artifact(plan):
        return ""
    return _join(
        [
            "DELIVERY PLAN",
            _section("Delivery phases", plan.get("delivery_phases")),
            _section("Workstreams", plan.get("workstreams")),
            _section("Dependencies", plan.get("dependencies")),
            _section("Milestones", plan.get("milestones")),
            _section("Team roles", plan.get("team_roles")),
            _section("Delivery risks", plan.get("delivery_risks")),
        ]
    )


def format_estimate_text(estimate: dict | None, disclaimer: str = "") -> str:
    if not _has_artifact(estimate):
        return ""
    duration = str(estimate.get("baseline_duration_range") or estimate.get("duration_range") or "").strip()
    if not duration:
        return ""
    parts = [
        "INDEPENDENT ESTIMATE",
        "Baseline human-led estimate. This is not the optional AI-assisted scenario.",
        _section("Duration", duration),
        _section("Effort", estimate.get("baseline_effort_range") or estimate.get("effort_range")),
        _section("Confidence", estimate.get("confidence")),
        _section("Requested deadline", estimate.get("customer_deadline")),
        _section("Customer estimate", estimate.get("customer_baseline_duration")),
        _section("Deadline fit", estimate.get("standard_deadline_fit")),
        _section("Assumptions", estimate.get("assumptions")),
        _section("Risks affecting the estimate", estimate.get("risks_affecting_estimate")),
        _section("Variance vs customer estimate", estimate.get("baseline_variance_explanation")),
    ]
    if disclaimer:
        parts.append(_section("Disclaimer", disclaimer))
    return _join(parts)


def format_ai_scenario_text(optimization: dict | None) -> str:
    if not _has_artifact(optimization):
        return ""
    duration = str(optimization.get("duration_range") or "").strip()
    if not duration:
        return ""
    return _join(
        [
            "OPTIONAL AI-ASSISTED SCENARIO",
            "Scenario analysis only. It does not replace the independent estimate and is not a guaranteed acceleration.",
            _section("AI-assisted duration", duration),
            _section("Independent baseline (unchanged)", optimization.get("standard_duration_range")),
            _section("AI effort", optimization.get("effort_range")),
            _section("Deadline", optimization.get("customer_deadline")),
            _section("Deadline feasibility", optimization.get("deadline_feasibility")),
            _section("Delivery gap", optimization.get("deadline_gap")),
            _section("Confidence", optimization.get("confidence")),
            _section("Team model", optimization.get("optimization_team_model")),
            _section("Summary", optimization.get("optimization_summary")),
            _section("Optimization levers", optimization.get("optimization_levers")),
            _section("Feasibility conditions", optimization.get("feasibility_conditions")),
            _section("Scope trade-offs", optimization.get("scope_tradeoffs")),
            _section("Recommendations", optimization.get("recommendations")),
        ]
    )


def format_proposal_text(proposal: dict | None) -> str:
    if not _has_artifact(proposal):
        return ""
    return _join(
        [
            "PROPOSAL",
            _section("Executive summary", proposal.get("executive_summary")),
            _section("Scope", proposal.get("scope")),
            _section("Delivery approach", proposal.get("delivery_approach")),
            _section("Timeline", proposal.get("timeline")),
            _section("Assumptions", proposal.get("assumptions")),
            _section("Risks", proposal.get("risks")),
            _section("Next steps", proposal.get("next_steps")),
        ]
    )


def format_sow_text(sow: dict | None) -> str:
    if not _has_artifact(sow):
        return ""
    return _join(
        [
            "STATEMENT OF WORK",
            _section("Objectives", sow.get("objectives")),
            _section("Deliverables", sow.get("deliverables")),
            _section("In scope", sow.get("in_scope")),
            _section("Out of scope", sow.get("out_of_scope")),
            _section("Dependencies", sow.get("dependencies")),
            _section("Acceptance", sow.get("acceptance")),
            _section("Timeline", sow.get("timeline")),
            _section("Assumptions", sow.get("assumptions")),
        ]
    )


def build_artifact_texts(payload: dict) -> dict[str, str]:
    """Return copy/print text only for artifacts that actually exist."""
    assessment = payload.get("assessment") or {}
    disclaimer = str(
        assessment.get("estimate_disclaimer") or assessment.get("disclaimer") or ""
    ).strip()
    texts = {
        "assessment": str(payload.get("assessment_text") or "").strip(),
        "solution": format_solution_text(payload.get("solution")),
        "delivery_plan": format_delivery_plan_text(payload.get("delivery_plan")),
        "estimate": format_estimate_text(payload.get("estimate"), disclaimer),
        "ai_optimization": format_ai_scenario_text(payload.get("ai_optimization")),
        "proposal": format_proposal_text(payload.get("proposal")),
        "sow": format_sow_text(payload.get("sow")),
    }
    return {key: value for key, value in texts.items() if value}
