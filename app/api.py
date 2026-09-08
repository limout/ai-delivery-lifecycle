import json
import os
import queue
import threading
import time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.graph import build_graph, build_optimization_graph
from app.providers import (
    AIProvider,
    AIProviderQuotaError,
    GeminiProvider,
    OllamaProvider,
    MockProvider,
)

router = APIRouter()


STAGE_LABELS = {
    "discovery": "Discovery",
    "requirements": "Requirements",
    "validation": "Validation",
    "clarification": "Clarification",
    "await_customer": "Waiting for customer",
    "solution": "Solution",
    "delivery_plan": "Delivery Plan",
    "estimate": "Estimate",
    "delivery_review": "Delivery Review",
    "proposal": "Proposal",
    "sow": "SOW",
    "blocked": "Blocked",
    "complete": "Complete",
    "ai_optimization": "AI Optimization",
    "optimization_complete": "Optimization Complete",
}


def _sse_event(event: str, payload: dict) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )


def _stream_workflow(
    request: str,
    clarification_answers: list[str] | None,
    clarification_history: list[dict] | None,
    iteration: int,
    provider: AIProvider,
):
    """Stream graph node progress and the final workflow response as SSE."""
    events: queue.Queue = queue.Queue()
    started_at = time.monotonic()

    def progress_callback(stage: str, status: str) -> None:
        elapsed = round(time.monotonic() - started_at, 1)
        events.put({
            "type": "stage",
            "stage": stage,
            "label": STAGE_LABELS.get(stage, stage.replace("_", " ").title()),
            "status": status,
            "elapsed": elapsed,
        })

    def worker() -> None:
        try:
            graph = build_graph(provider, progress_callback=progress_callback)
            state = {
                "user_request": request,
                "iteration": iteration,
                "workflow_status": "RUNNING",
                "awaiting_customer": False,
            }
            if clarification_answers:
                state["clarification_answers"] = clarification_answers
            if clarification_history:
                state["clarification_history"] = clarification_history

            result = graph.invoke(state)
            events.put({
                "type": "result",
                "data": workflow_response(result),
            })
        except AIProviderQuotaError as exc:
            events.put({
                "type": "error",
                "status_code": 503,
                "error": "AI_PROVIDER_QUOTA_EXCEEDED",
                "message": str(exc),
            })
        except Exception as exc:
            events.put({
                "type": "error",
                "status_code": 500,
                "error": "WORKFLOW_FAILED",
                "message": str(exc),
            })
        finally:
            events.put({"type": "done"})

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    yield _sse_event(
        "started",
        {
            "type": "started",
            "message": "Running delivery workflow",
        },
    )

    while True:
        try:
            item = events.get(timeout=10)
        except queue.Empty:
            yield _sse_event("ping", {"type": "ping"})
            continue

        item_type = item.get("type")
        if item_type == "stage":
            yield _sse_event("stage", item)
        elif item_type == "result":
            yield _sse_event("result", item["data"])
        elif item_type == "error":
            yield _sse_event("error", item)
        elif item_type == "done":
            yield _sse_event("done", {"type": "done"})
            break



def _stream_optimization(
    request: str,
    analysis: dict,
    provider: AIProvider,
):
    """Stream the explicit, user-triggered AI optimization graph."""
    events: queue.Queue = queue.Queue()
    started_at = time.monotonic()

    def progress_callback(stage: str, status: str) -> None:
        elapsed = round(time.monotonic() - started_at, 1)
        events.put({
            "type": "stage",
            "stage": stage,
            "label": STAGE_LABELS.get(stage, stage.replace("_", " ").title()),
            "status": status,
            "elapsed": elapsed,
        })

    def worker() -> None:
        try:
            graph = build_optimization_graph(
                provider,
                progress_callback=progress_callback,
            )
            state = dict(analysis or {})
            state["user_request"] = request
            state["workflow_status"] = "RUNNING"
            state["awaiting_customer"] = False
            result = graph.invoke(state)
            events.put({
                "type": "result",
                "data": workflow_response(result),
            })
        except AIProviderQuotaError as exc:
            events.put({
                "type": "error",
                "status_code": 503,
                "error": "AI_PROVIDER_QUOTA_EXCEEDED",
                "message": str(exc),
            })
        except Exception as exc:
            events.put({
                "type": "error",
                "status_code": 500,
                "error": "AI_OPTIMIZATION_FAILED",
                "message": str(exc),
            })
        finally:
            events.put({"type": "done"})

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    yield _sse_event(
        "started",
        {"type": "started", "message": "Running AI delivery optimization"},
    )

    while True:
        try:
            item = events.get(timeout=10)
        except queue.Empty:
            yield _sse_event("ping", {"type": "ping"})
            continue

        item_type = item.get("type")
        if item_type == "stage":
            yield _sse_event("stage", item)
        elif item_type == "result":
            yield _sse_event("result", item["data"])
        elif item_type == "error":
            yield _sse_event("error", item)
        elif item_type == "done":
            yield _sse_event("done", {"type": "done"})
            break


class AnalyzeRequest(BaseModel):
    user_request: str = Field(min_length=1)


class OptimizeRequest(BaseModel):
    user_request: str = Field(min_length=1)
    analysis: dict = Field(default_factory=dict)


class ClarificationAnswer(BaseModel):
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)


class ClarifyRequest(BaseModel):
    user_request: str = Field(min_length=1)
    answers: list[ClarificationAnswer] = Field(default_factory=list)
    # Backward-compatible form used by the existing UI/tests.
    clarification_answers: list[str] = Field(default_factory=list)
    # Cumulative history is sent back by the UI so clarification is a true
    # multi-iteration loop rather than a sequence of stateless re-runs.
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
    """Convert structured answers to the legacy string representation used by agents."""
    answers = [
        f"Customer clarification — Question: {item.question}\nAnswer: {item.answer}"
        for item in request.answers
        if item.answer.strip()
    ]
    answers.extend(
        answer for answer in request.clarification_answers if answer.strip()
    )
    return answers


def _merge_clarification_history(
    history: list[dict],
    request: ClarifyRequest,
) -> list[dict]:
    """Merge the previous history with newly submitted customer answers."""
    merged = list(history or [])

    answers = list(request.answers)
    if not answers and request.clarification_answers:
        answers = [
            ClarificationAnswer(
                question="Customer clarification",
                answer=item,
            )
            for item in request.clarification_answers
        ]

    existing = {
        (str(item.get("question") or "").strip(), str(item.get("answer") or "").strip())
        for item in merged
        if isinstance(item, dict)
    }

    for item in answers:
        question = item.question.strip()
        answer = item.answer.strip()
        if not answer:
            continue
        record = {"question": question, "answer": answer}
        key = (question, answer)
        if key not in existing:
            merged.append(record)
            existing.add(key)

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

    return graph.invoke(state)


def workflow_response(result: dict) -> dict:
    validation = result.get("validation", {})
    review = result.get("delivery_review") or {}
    status = result.get("workflow_status")

    if not status:
        if validation.get("status") == "NEEDS_INFO":
            status = "NEEDS_INFO"
        elif review.get("status") == "BLOCKED":
            status = "BLOCKED"
        elif result.get("sow"):
            status = "COMPLETE"
        else:
            status = validation.get("status", "UNKNOWN")

    clarification_questions = result.get("clarification_questions", [])
    if not clarification_questions:
        clarification_questions = validation.get("questions", [])
    if not clarification_questions:
        clarification_questions = review.get("clarification_questions", [])

    # Validation is the source of truth for structured blockers.  The graph
    # may keep these fields nested under `validation`, so normalize them at
    # the API boundary instead of silently returning empty arrays.
    blocking_questions = result.get("blocking_questions", [])
    if not blocking_questions:
        blocking_questions = validation.get("blocking_questions", [])

    non_blocking_questions = result.get("non_blocking_questions", [])
    if not non_blocking_questions:
        non_blocking_questions = validation.get("non_blocking_questions", [])

    # A workflow waiting for customer input must expose structured blockers.
    # Validation may represent blocking_questions as plain strings, while the
    # API contract exposes the richer clarification-question objects.
    if status == "NEEDS_INFO" and not blocking_questions:
        blocking_questions = list(clarification_questions)

    structured_blocking_questions = []
    clarification_by_question = {
        str(item.get("question", "")).strip().lower(): item
        for item in clarification_questions
        if isinstance(item, dict) and item.get("question")
    }

    for item in blocking_questions:
        if isinstance(item, dict):
            structured_blocking_questions.append(item)
            continue

        question = str(item).strip()
        if not question:
            continue

        existing = clarification_by_question.get(question.lower())
        if existing:
            structured_blocking_questions.append(existing)
        else:
            structured_blocking_questions.append({
                "question": question,
                "priority": "REQUIRED",
                "reason": "Customer input is required before the workflow can continue.",
                "blocks_workflow": True,
            })

    blocking_questions = structured_blocking_questions

    return {
        "status": status,
        "workflow_status": status,
        "current_stage": result.get("current_stage"),
        "awaiting_customer": result.get("awaiting_customer", False),
        "discovery": result.get("discovery"),
        "requirements": result.get("requirements"),
        "validation": validation,
        "clarification_questions": clarification_questions,
        "blocking_questions": blocking_questions,
        "non_blocking_questions": non_blocking_questions,
        "clarification_history": result.get("clarification_history", []),
        "iteration": result.get("iteration", 1),
        "solution": result.get("solution"),
        "delivery_plan": result.get("delivery_plan"),
        "estimate": result.get("estimate"),
        "ai_optimization": result.get("ai_optimization"),
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


@router.post("/analyze/stream")
def analyze_stream(
    request: AnalyzeRequest,
    provider: AIProvider = Depends(get_provider),
):
    return StreamingResponse(
        _stream_workflow(
            request=request.user_request,
            clarification_answers=None,
            clarification_history=None,
            iteration=1,
            provider=provider,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/optimize/stream")
def optimize_stream(
    request: OptimizeRequest,
    provider: AIProvider = Depends(get_provider),
):
    if not request.analysis.get("estimate"):
        return JSONResponse(
            status_code=422,
            content={
                "error": "ESTIMATE_REQUIRED",
                "message": "Run Analyze Request first so the standard estimate is available.",
            },
        )

    return StreamingResponse(
        _stream_optimization(
            request=request.user_request,
            analysis=request.analysis,
            provider=provider,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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


@router.post("/clarify/stream")
def clarify_stream(
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

    history = _merge_clarification_history(
        request.clarification_history,
        request,
    )

    return StreamingResponse(
        _stream_workflow(
            request=request.user_request,
            clarification_answers=answers,
            clarification_history=history,
            iteration=request.iteration + 1,
            provider=provider,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
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
        # Preserve the complete conversation of customer facts across every
        # clarification iteration. The next graph run receives both the new
        # answers and the cumulative history.
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

        result["clarification_history"] = history
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
