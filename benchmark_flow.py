import json
import time

from app.graph import build_graph
from app.providers import OllamaProvider


class CountingOllamaProvider(OllamaProvider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []

    @staticmethod
    def _classify_stage(prompt, schema):
        """Classify calls from their output schema, not incidental prompt words."""
        required = frozenset((schema or {}).get("required", []))

        if required == frozenset({
            "problem", "business_goal", "users", "stakeholders",
            "existing_systems", "scope", "constraints", "assumptions",
            "unknowns", "clarification_questions",
        }):
            return "discovery"

        if required == frozenset({
            "functional_requirements", "non_functional_requirements",
            "acceptance_criteria", "open_questions", "contradictions",
        }):
            prompt_lower = prompt.lower()
            if "rebuild the requirements artifact" in prompt_lower or "strict provenance rule" in prompt_lower:
                return "requirements_retry_grounding"
            return "requirements"

        if required == frozenset({
            "status", "reasons", "questions", "non_blocking_questions",
        }):
            return "validation"

        if required == frozenset({
            "solution_summary", "key_capabilities", "integration_approach",
            "technical_considerations", "delivery_risks", "dependencies",
            "assumptions",
        }):
            return "solution"

        if required == frozenset({
            "delivery_phases", "workstreams", "dependencies", "milestones",
            "team_roles", "delivery_risks",
        }):
            return "delivery_plan"

        if required == frozenset({
            "effort_range", "duration_range", "confidence", "assumptions",
            "risks_affecting_estimate",
        }):
            return "estimate"

        if required == frozenset({
            "status", "blocking_issues", "clarification_questions",
            "warnings", "checks",
        }):
            return "delivery_review"

        if required == frozenset({
            "executive_summary", "scope", "delivery_approach", "timeline",
            "assumptions", "risks", "next_steps",
        }):
            return "proposal"

        if required == frozenset({
            "objectives", "deliverables", "in_scope", "out_of_scope",
            "dependencies", "acceptance", "timeline", "assumptions",
        }):
            return "sow"

        return "unknown"

    def generate_json(self, prompt, schema):
        started = time.perf_counter()

        result = super().generate_json(prompt, schema)

        elapsed = time.perf_counter() - started
        stage = self._classify_stage(prompt, schema)

        self.calls.append(
            {
                "stage": stage,
                "elapsed": elapsed,
                "prompt_chars": len(prompt),
                "result": result,
            }
        )

        return result


def print_stage_output(call):
    print()
    print("=" * 80)
    print(f"STAGE: {call['stage']}")
    print(f"TIME: {call['elapsed']:.2f}s")
    print(f"PROMPT: {call['prompt_chars']} chars")
    print("-" * 80)

    try:
        print(json.dumps(call["result"], indent=2, ensure_ascii=False))
    except Exception:
        print(call["result"])

    print("=" * 80)


def run_case(name, user_request):
    print()
    print("#" * 100)
    print(f"# {name}")
    print("#" * 100)

    provider = CountingOllamaProvider()

    graph = build_graph(provider)

    initial_state = {
        "user_request": user_request,
    }

    started = time.perf_counter()

    result = graph.invoke(initial_state)

    total_elapsed = time.perf_counter() - started

    print()
    print("\nRESULT")
    print("-" * 80)

    print("workflow_status:", result.get("workflow_status"))
    print("current_stage:", result.get("current_stage"))
    print("awaiting_customer:", result.get("awaiting_customer"))

    validation = result.get("validation") or {}

    print()
    print("VALIDATION STATUS:", validation.get("status"))

    print()
    print("BLOCKING QUESTIONS:")
    for question in validation.get("blocking_questions", []):
        print("-", question)

    print()
    print("NON-BLOCKING QUESTIONS:")
    for question in validation.get("non_blocking_questions", []):
        print("-", question)

    print()
    print("ALL QUESTIONS:")
    for question in validation.get("questions", []):
        print("-", question)

    print()
    print("LLM CALLS")
    print("-" * 80)

    total_llm_time = 0.0

    for index, call in enumerate(provider.calls, 1):
        total_llm_time += call["elapsed"]
        print(
            f"{index}. {call['stage']} "
            f"{call['elapsed']:.2f}s "
            f"prompt={call['prompt_chars']} chars"
        )

    print()
    print(f"TOTAL LLM CALLS: {len(provider.calls)}")
    print(f"TOTAL LLM TIME: {total_llm_time:.2f}s")
    print(f"TOTAL FLOW TIME: {total_elapsed:.2f}s")

    print()
    print("DETAILED STAGE OUTPUTS")

    for call in provider.calls:
        print_stage_output(call)

    downstream_stages = {
        "solution",
        "delivery_plan",
        "estimate",
        "delivery_review",
        "proposal",
        "sow",
    }

    actual_stages = {call["stage"] for call in provider.calls}

    if validation.get("status") == "NEEDS_INFO":
        unexpected = actual_stages.intersection(downstream_stages)

        if unexpected:
            print()
            print(
                "GRAPH EFFICIENCY CHECK: FAIL — "
                f"downstream calls happened: {sorted(unexpected)}"
            )
        else:
            print()
            print(
                "GRAPH EFFICIENCY CHECK: PASS — "
                "workflow stopped before downstream LLM calls."
            )

    return result


CASE_A = """
We need a self-service portal for enterprise customers.

Customers should be able to manage their requests through the portal.
""".strip()


CASE_B = """
We need a self-service portal for enterprise customers.

Business goal:
Reduce manual support effort by allowing enterprise customers
to manage common requests themselves.

Users:
Enterprise customers.

Stakeholders:
Customer Success and Account Management.

Existing systems:
Salesforce.

Authentication:
Enterprise users should authenticate using Microsoft Entra ID.

Scope:
Customers can view their account information, submit service requests,
and track request status.

The portal should integrate with Salesforce as the source of truth
for customer and request data.

Target delivery timeline:
2 months.

Security:
The solution must use enterprise authentication and appropriate
access controls.
""".strip()


if __name__ == "__main__":
    run_case(
        "CASE A — INCOMPLETE REQUEST",
        CASE_A,
    )

    run_case(
        "CASE B — MORE COMPLETE REQUEST",
        CASE_B,
    )