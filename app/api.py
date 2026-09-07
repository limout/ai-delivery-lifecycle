import os

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.graph import build_graph
from app.providers import (
    AIProvider,
    AIProviderQuotaError,
    GeminiProvider,
    OllamaProvider,
    MockProvider,
)

router = APIRouter()


class AnalyzeRequest(BaseModel):
    user_request: str = Field(min_length=1)


class ClarificationAnswer(BaseModel):
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)


class ClarifyRequest(BaseModel):
    user_request: str = Field(min_length=1)
    answers: list[ClarificationAnswer] = Field(default_factory=list)
    # Backward-compatible form used by earlier UI/tests.
    clarification_answers: list[str] = Field(default_factory=list)
    clarification_history: list[dict] = Field(default_factory=list)
    iteration: int = Field(default=1, ge=1)


def get_provider() -> AIProvider:
    provider_name = os.getenv("AI_PROVIDER", "gemini").lower()

    if provider_name == "mock":
        return MockProvider()
    if provider_name == "ollama":
        return OllamaProvider()
    if provider_name == "gemini":
        return GeminiProvider()

    raise RuntimeError(f"Unsupported AI_PROVIDER: {provider_name}")


def _answer_strings(request: ClarifyRequest) -> list[str]:
    if request.answers:
        return [
            f"Customer clarification — Question: {item.question}\nAnswer: {item.answer}"
            for item in request.answers
        ]
    return request.clarification_answers


def _merge_clarification_history(
    history: list[dict],
    request: ClarifyRequest,
) -> list[dict]:
    merged = list(history or [])
    answers = request.answers
    if not answers and request.clarification_answers:
        answers = [
            ClarificationAnswer(question="Customer clarification", answer=item)
            for item in request.clarification_answers
        ]

    for item in answers:
        merged.append({"question": item.question, "answer": item.answer})

    return merged


def run_workflow(
    request: str,
    clarification_answers: list[str] | None = None,
    clarification_history: list[dict] | None = None,
    iteration: int | None = None,
    provider: AIProvider | None = None,
) -> dict:
    graph = build_graph(provider)

    state = {
        "user_request": request,
        "iteration": iteration or 1,
        "workflow_status": "RUNNING",
        "awaiting_customer": False,
    }

    if clarification_answers:
        state["clarification_answers"] = clarification_answers
    if clarification_history:
        state["clarification_history"] = clarification_history

    result = graph.invoke(state)

    # LangGraph can preserve an execution-time RUNNING value in the shared
    # state if an older graph/runtime path does not overwrite it at the very
    # end. The presence of a completed SOW is authoritative for this MVP.
    if result.get("sow") and (result.get("delivery_review") or {}).get("status") == "READY":
        result["workflow_status"] = "COMPLETE"
        result["current_stage"] = "complete"
        result["awaiting_customer"] = False
    elif (result.get("delivery_review") or {}).get("status") == "BLOCKED":
        result["workflow_status"] = "BLOCKED"
        result["current_stage"] = "delivery_review"
        result["awaiting_customer"] = False

    return result


def workflow_response(result: dict) -> dict:
    validation = result.get("validation", {})
    review = result.get("delivery_review") or {}
    status = result.get("workflow_status")

    # Terminal artifacts outrank stale execution status.
    if result.get("sow") and review.get("status") == "READY":
        status = "COMPLETE"
    elif review.get("status") == "BLOCKED":
        status = "BLOCKED"
    elif not status:
        if validation.get("status") == "NEEDS_INFO":
            status = "NEEDS_INFO"
        else:
            status = validation.get("status", "UNKNOWN")

    current_stage = result.get("current_stage")
    if status == "COMPLETE":
        current_stage = "complete"
    elif status == "BLOCKED":
        current_stage = "delivery_review"

    clarification_questions = result.get("clarification_questions", [])
    if not clarification_questions:
        clarification_questions = validation.get("questions", [])
    if not clarification_questions:
        clarification_questions = review.get("clarification_questions", [])

    return {
        "status": status,
        "workflow_status": status,
        "current_stage": current_stage,
        "awaiting_customer": result.get("awaiting_customer", False),
        "discovery": result.get("discovery"),
        "requirements": result.get("requirements"),
        "validation": validation,
        "blocking_questions": result.get("blocking_questions", [])
        or validation.get("blocking_questions", []),
        "clarification_questions": clarification_questions,
        "clarification_history": result.get("clarification_history", []),
        "iteration": result.get("iteration", 1),
        "solution": result.get("solution"),
        "delivery_plan": result.get("delivery_plan"),
        "estimate": result.get("estimate"),
        "delivery_review": result.get("delivery_review"),
        "proposal": result.get("proposal"),
        "sow": result.get("sow"),
    }


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/config")
def config() -> dict:
    return {"ai_provider": os.getenv("AI_PROVIDER", "gemini").lower()}


@router.post("/analyze")
def analyze(
    request: AnalyzeRequest,
    provider: AIProvider = Depends(get_provider),
):
    try:
        result = run_workflow(
            request=request.user_request,
            iteration=1,
            provider=provider,
        )
        return workflow_response(result)
    except AIProviderQuotaError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "error": "AI_PROVIDER_QUOTA_EXCEEDED",
                "message": str(exc),
            },
        )


@router.post("/clarify")
def clarify(
    request: ClarifyRequest,
    provider: AIProvider = Depends(get_provider),
):
    answers = _answer_strings(request)
    if not answers:
        return JSONResponse(
            status_code=422,
            content={
                "error": "CLARIFICATION_ANSWERS_REQUIRED",
                "message": "Provide at least one customer clarification answer.",
            },
        )

    try:
        # This is the loop re-entry. The same graph is invoked with the
        # new customer facts, so Discovery/Requirements/Validation run
        # again and the conditional graph decides where to go next.
        history = _merge_clarification_history(
            request.clarification_history,
            request,
        )

        result = run_workflow(
            request=request.user_request,
            clarification_answers=answers,
            clarification_history=history,
            iteration=request.iteration + 1,
            provider=provider,
        )

        response = workflow_response(result)
        response["clarification_history"] = history
        return response
    except AIProviderQuotaError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "error": "AI_PROVIDER_QUOTA_EXCEEDED",
                "message": str(exc),
            },
        )
