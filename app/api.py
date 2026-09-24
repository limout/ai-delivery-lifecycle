import json
import os
import queue
import threading
import time
import hashlib
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.graph import build_graph, build_optimization_graph, build_gap_close_graph
from app.artifact_export import build_artifact_texts
from app.assessment import build_assessment, build_verdict, format_assessment_text, format_print_assessment
from app.evidence import is_numeric_duration
from app.gap_close import gap_closing_eligible
from app.llm_cost import calculate_llm_cost, log_llm_cost
from app.providers import (
    AIProvider,
    AIProviderQuotaError,
    GeminiProvider,
    OllamaProvider,
    MockProvider,
    llm_usage_record,
)
from app.resume import answers_require_upstream_regen
from app.runs import artifacts_from_payload, get_run, new_run_id, save_run

router = APIRouter()


RATE_LIMIT_TTL_SECONDS = 24 * 60 * 60


def _rate_limit_enabled() -> bool:
    """Enable the public daily limit only in the deployed environment."""
    environment = os.getenv("APP_ENV", "local").strip().lower()
    return environment not in {"local", "development", "dev", "test"}


def _whitelisted_ips() -> set[str]:
    """Return IPs that are never subject to the public rate limit."""
    raw = os.getenv("RATE_LIMIT_WHITELIST_IPS", "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _client_ip(request: Request) -> str:
    # Render sits behind a proxy. Use the forwarded client IP when present.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limit_key(scope: str, ip: str) -> str:
    digest = hashlib.sha256(ip.encode("utf-8")).hexdigest()
    return f"limout-ai:{scope}:{digest}"


_rate_limit_memory: dict[str, float] = {}


def _claim_daily_run(scope: str, ip: str) -> bool:
    """Allow one public run per IP every 24 hours.

    Local development and explicitly whitelisted IPs bypass the limiter.
    When Upstash is configured, the claim survives application restarts.
    """
    if not _rate_limit_enabled() or ip in _whitelisted_ips():
        return True

    key = _rate_limit_key(scope, ip)
    url = os.getenv("UPSTASH_REDIS_REST_URL")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN")

    if url and token:
        try:
            payload = json.dumps([
                "SET", key, "1", "EX", str(RATE_LIMIT_TTL_SECONDS), "NX"
            ]).encode("utf-8")
            request = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                result = json.loads(response.read().decode("utf-8"))
            return result.get("result") == "OK"
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            print(f"[RATE_LIMIT] Upstash unavailable: {exc}")

    now = time.time()
    last = _rate_limit_memory.get(key)
    if last is not None and now - last < RATE_LIMIT_TTL_SECONDS:
        return False
    _rate_limit_memory[key] = now
    return True


def _rate_limit_response(scope: str) -> JSONResponse:
    label = "analysis" if scope == "analyze" else "AI optimization"
    return JSONResponse(
        status_code=429,
        content={
            "error": "DAILY_RATE_LIMIT_EXCEEDED",
            "message": f"One {label} run per IP is allowed every 24 hours.",
            "retry_after_seconds": RATE_LIMIT_TTL_SECONDS,
        },
        headers={"Retry-After": str(RATE_LIMIT_TTL_SECONDS)},
    )


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
    "apply_clarification": "Apply clarification",
    "ai_optimization": "AI Optimization",
    "optimization_complete": "Optimization Complete",
    "deadline_gap_plan": "Deadline gap plan",
    "gap_close_complete": "Gap-close complete",
}


class _InstrumentedProvider:
    """Count LLM calls and collect provider-agnostic usage records."""

    def __init__(self, inner: AIProvider):
        self.inner = inner
        self.llm_calls = 0
        self.current_node: str | None = None
        self.llm_usage: list[dict] = []

    def generate_json(self, prompt: str, schema: dict) -> dict:
        self.llm_calls += 1
        required = list((schema or {}).get("required") or [])
        print(f"[WORKFLOW] llm_call count={self.llm_calls} schema={required[:6]}")
        started_at = time.perf_counter()
        result = self.inner.generate_json(prompt, schema)
        duration_ms = max(0, int(round((time.perf_counter() - started_at) * 1000)))
        self.llm_usage.append(self._usage_record(duration_ms))
        usage = self.llm_usage[-1]
        print(
            f"[USAGE] provider={usage.get('provider')} model={usage.get('model')} "
            f"node={usage.get('node')} input_tokens={usage.get('input_tokens')} "
            f"output_tokens={usage.get('output_tokens')} "
            f"total_tokens={usage.get('total_tokens')} "
            f"duration_ms={usage.get('duration_ms')}"
        )
        return result

    def _usage_record(self, duration_ms: int) -> dict:
        raw = getattr(self.inner, "last_usage", None)
        if isinstance(raw, dict):
            record = dict(raw)
            record["node"] = self.current_node
            if record.get("duration_ms") is None:
                record["duration_ms"] = duration_ms
            return record
        return llm_usage_record(
            provider=type(self.inner).__name__,
            model=getattr(self.inner, "model", None),
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            duration_ms=duration_ms,
            node=self.current_node,
        )


def _new_clarification_records(request: "ClarifyRequest") -> list[dict]:
    records = [
        {"question": item.question.strip(), "answer": item.answer.strip()}
        for item in request.answers
        if item.answer.strip()
    ]
    if not records:
        records = [
            {"question": "", "answer": item.strip()}
            for item in request.clarification_answers
            if item.strip()
        ]
    return records


def _initial_workflow_state(
    request: str,
    clarification_answers: list[str] | None,
    clarification_history: list[dict] | None,
    iteration: int,
    resume_after_clarification: bool = False,
    prior_state: dict | None = None,
    new_clarification_records: list[dict] | None = None,
) -> dict:
    state = {
        "user_request": request,
        "iteration": iteration,
        "workflow_status": "RUNNING",
        "awaiting_customer": False,
        "resume_after_clarification": resume_after_clarification,
        "regenerate_upstream": True,
        "skipped_nodes": [],
    }
    if clarification_answers:
        state["clarification_answers"] = clarification_answers
    if clarification_history:
        state["clarification_history"] = clarification_history
    if new_clarification_records:
        state["new_clarification_records"] = new_clarification_records

    if resume_after_clarification and prior_state:
        for key in ("discovery", "requirements"):
            if prior_state.get(key):
                state[key] = prior_state[key]
        if prior_state.get("clarification_history") and not clarification_history:
            state["clarification_history"] = prior_state["clarification_history"]

        regen = answers_require_upstream_regen(state)
        state["regenerate_upstream"] = regen
        if not regen and state.get("discovery") and state.get("requirements"):
            state["skipped_nodes"] = ["discovery", "requirements"]
        else:
            state["skipped_nodes"] = []

    return state


def _llm_cost_for_usage(usage: list[dict]) -> dict:
    cost = calculate_llm_cost(usage)
    log_llm_cost(cost)
    return cost


def _execution_payload(
    state: dict,
    nodes_executed: list[str],
    llm_calls: int,
    elapsed: float,
    mode: str,
    llm_usage: list[dict] | None = None,
) -> dict:
    skipped = list(state.get("skipped_nodes") or [])
    usage = list(llm_usage or [])
    payload = {
        "mode": mode,
        "nodes_executed": nodes_executed,
        "nodes_skipped": skipped,
        "llm_calls": llm_calls,
        "llm_calls_avoided": len(skipped),
        "elapsed_seconds": round(elapsed, 2),
        "regenerate_upstream": bool(state.get("regenerate_upstream", True)),
        "llm_usage": usage,
        "llm_cost": _llm_cost_for_usage(usage),
    }
    print(
        f"[WORKFLOW] mode={mode} nodes={nodes_executed} "
        f"skipped={skipped} llm_calls={llm_calls} "
        f"avoided={payload['llm_calls_avoided']} elapsed={payload['elapsed_seconds']}s"
    )
    return payload


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
    resume_after_clarification: bool = False,
    prior_state: dict | None = None,
    new_clarification_records: list[dict] | None = None,
    run_id: str | None = None,
):
    """Stream graph node progress and the final workflow response as SSE."""
    events: queue.Queue = queue.Queue()
    started_at = time.monotonic()
    nodes_executed: list[str] = []
    instrumented = _InstrumentedProvider(provider)

    def progress_callback(stage: str, status: str) -> None:
        elapsed = round(time.monotonic() - started_at, 1)
        if status == "running":
            instrumented.current_node = stage
            if stage not in nodes_executed:
                nodes_executed.append(stage)
        events.put({
            "type": "stage",
            "stage": stage,
            "label": STAGE_LABELS.get(stage, stage.replace("_", " ").title()),
            "status": status,
            "elapsed": elapsed,
        })

    def worker() -> None:
        try:
            graph = build_graph(instrumented, progress_callback=progress_callback)
            state = _initial_workflow_state(
                request=request,
                clarification_answers=clarification_answers,
                clarification_history=clarification_history,
                iteration=iteration,
                resume_after_clarification=resume_after_clarification,
                prior_state=prior_state,
                new_clarification_records=new_clarification_records,
            )
            result = graph.invoke(state)
            result["execution"] = _execution_payload(
                state,
                nodes_executed,
                instrumented.llm_calls,
                time.monotonic() - started_at,
                "clarify" if resume_after_clarification else "analyze",
                instrumented.llm_usage,
            )
            events.put({
                "type": "result",
                "data": workflow_response(result, run_id=run_id),
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
    instrumented = _InstrumentedProvider(provider)

    def progress_callback(stage: str, status: str) -> None:
        elapsed = round(time.monotonic() - started_at, 1)
        if status == "running":
            instrumented.current_node = stage
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
                instrumented,
                progress_callback=progress_callback,
            )
            state = dict(analysis or {})
            state["user_request"] = request
            state["workflow_status"] = "RUNNING"
            state["awaiting_customer"] = False
            result = graph.invoke(state)
            usage = list(instrumented.llm_usage)
            result["execution"] = {
                "mode": "optimize",
                "nodes_executed": ["ai_optimization", "optimization_complete"],
                "nodes_skipped": [],
                "llm_calls": instrumented.llm_calls,
                "llm_calls_avoided": 0,
                "elapsed_seconds": round(time.monotonic() - started_at, 2),
                "llm_usage": usage,
                "llm_cost": _llm_cost_for_usage(usage),
            }
            events.put({
                "type": "result",
                "data": workflow_response(result, run_id=analysis.get("run_id")),
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


def _stream_gap_close(
    request: str,
    analysis: dict,
    provider: AIProvider,
):
    """Stream the explicit, user-triggered hard-deadline gap-closing graph."""
    events: queue.Queue = queue.Queue()
    started_at = time.monotonic()
    instrumented = _InstrumentedProvider(provider)

    def progress_callback(stage: str, status: str) -> None:
        elapsed = round(time.monotonic() - started_at, 1)
        if status == "running":
            instrumented.current_node = stage
        events.put({
            "type": "stage",
            "stage": stage,
            "label": STAGE_LABELS.get(stage, stage.replace("_", " ").title()),
            "status": status,
            "elapsed": elapsed,
        })

    def worker() -> None:
        try:
            graph = build_gap_close_graph(
                instrumented,
                progress_callback=progress_callback,
            )
            state = dict(analysis or {})
            state["user_request"] = request
            state["workflow_status"] = "RUNNING"
            state["awaiting_customer"] = False
            result = graph.invoke(state)
            usage = list(instrumented.llm_usage)
            result["execution"] = {
                "mode": "gap_close",
                "nodes_executed": ["deadline_gap_plan", "gap_close_complete"],
                "nodes_skipped": [],
                "llm_calls": instrumented.llm_calls,
                "llm_calls_avoided": 0,
                "elapsed_seconds": round(time.monotonic() - started_at, 2),
                "llm_usage": usage,
                "llm_cost": _llm_cost_for_usage(usage),
            }
            events.put({
                "type": "result",
                "data": workflow_response(result, run_id=analysis.get("run_id")),
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
                "error": "GAP_CLOSE_FAILED",
                "message": str(exc),
            })
        finally:
            events.put({"type": "done"})

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    yield _sse_event(
        "started",
        {"type": "started", "message": "Analyzing how to achieve the customer deadline"},
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
    run_id: str | None = None
    prior_state: dict = Field(default_factory=dict)


class RagIngestRequest(BaseModel):
    """Admin/demo ingest body. Auth for this endpoint is a Phase 2 requirement.

    Optional protection: set RAG_INGEST_TOKEN and send header X-RAG-Ingest-Token.
    """

    document_id: str = Field(min_length=1)
    title: str = ""
    source: str = "internal"
    content: str = Field(min_length=1)


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


def _resolve_prior_state(request: ClarifyRequest) -> dict:
    stored = get_run(request.run_id)
    if stored:
        return stored
    return artifacts_from_payload(request.prior_state)


def run_workflow(
    request: str,
    clarification_answers: list[str] | None = None,
    clarification_history: list[dict] | None = None,
    iteration: int | None = None,
    provider: AIProvider | None = None,
    resume_after_clarification: bool = False,
    prior_state: dict | None = None,
    new_clarification_records: list[dict] | None = None,
) -> dict:
    started_at = time.monotonic()
    nodes_executed: list[str] = []
    inner = provider
    instrumented = _InstrumentedProvider(inner) if inner is not None else None

    def progress_callback(stage: str, status: str) -> None:
        if status == "running":
            if instrumented is not None:
                instrumented.current_node = stage
            if stage not in nodes_executed:
                nodes_executed.append(stage)

    graph = build_graph(
        instrumented if instrumented is not None else inner,
        progress_callback=progress_callback,
    )
    state = _initial_workflow_state(
        request=request,
        clarification_answers=clarification_answers,
        clarification_history=clarification_history,
        iteration=iteration or 1,
        resume_after_clarification=resume_after_clarification,
        prior_state=prior_state,
        new_clarification_records=new_clarification_records,
    )
    result = graph.invoke(state)
    llm_calls = instrumented.llm_calls if instrumented is not None else 0
    result["execution"] = _execution_payload(
        state,
        nodes_executed,
        llm_calls,
        time.monotonic() - started_at,
        "clarify" if resume_after_clarification else "analyze",
        instrumented.llm_usage if instrumented is not None else [],
    )
    return result


def _normalize_questions(items, required: bool = False) -> list[dict]:
    normalized = []
    seen: set[str] = set()
    for item in items or []:
        if isinstance(item, dict):
            question = str(item.get("question") or item.get("text") or "").strip()
            if not question or question.lower() in seen:
                continue
            blocks = bool(item.get("blocks_workflow", required))
            normalized.append({
                "question": question,
                "priority": str(item.get("priority") or ("REQUIRED" if blocks or required else "RECOMMENDED")).upper(),
                "reason": str(item.get("reason") or ""),
                "blocks_workflow": blocks or required,
            })
            seen.add(question.lower())
        else:
            question = str(item).strip()
            if not question or question.lower() in seen:
                continue
            normalized.append({
                "question": question,
                "priority": "REQUIRED" if required else "RECOMMENDED",
                "reason": "",
                "blocks_workflow": required,
            })
            seen.add(question.lower())
    return normalized


def workflow_response(result: dict, run_id: str | None = None) -> dict:
    validation = result.get("validation") or {}
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

    clarification_questions = _normalize_questions(
        result.get("clarification_questions"),
        required=True,
    )
    blocking_questions = [item for item in clarification_questions if item["blocks_workflow"]]
    if not blocking_questions:
        blocking_questions = _normalize_questions(
            result.get("blocking_questions") or validation.get("blocking_questions"),
            required=True,
        )
    if not clarification_questions:
        clarification_questions = list(blocking_questions)

    non_blocking_questions = _normalize_questions(
        result.get("non_blocking_questions") or validation.get("non_blocking_questions"),
        required=False,
    )
    blocking_text = {item["question"].lower() for item in blocking_questions}
    non_blocking_questions = [
        item for item in non_blocking_questions
        if item["question"].lower() not in blocking_text
    ]

    resolved_run_id = run_id or result.get("run_id") or new_run_id()
    save_run(resolved_run_id, result)

    payload = {
        "run_id": resolved_run_id,
        "status": status,
        "workflow_status": status,
        "current_stage": result.get("current_stage"),
        "awaiting_customer": result.get("awaiting_customer", False),
        "user_request": result.get("user_request"),
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
        "deadline_gap_plan": result.get("deadline_gap_plan"),
        "delivery_review": result.get("delivery_review"),
        "proposal": result.get("proposal"),
        "sow": result.get("sow"),
        "execution": result.get("execution"),
        "default_view": (
            "delivery_review"
            if status == "BLOCKED" or str(review.get("status") or "").upper() == "BLOCKED"
            else "assessment"
        ),
    }
    payload["verdict"] = build_verdict(payload)
    assessment = build_assessment(payload)
    payload["assessment"] = assessment
    payload["assessment_text"] = format_assessment_text(assessment)
    payload["print_assessment_text"] = format_print_assessment(assessment)
    if payload.get("deadline_gap_plan") and not gap_closing_eligible(payload):
        payload["deadline_gap_plan"] = None
    payload["gap_closing_available"] = gap_closing_eligible(payload)
    payload["artifact_texts"] = build_artifact_texts(payload)
    return payload


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _config_build() -> str:
    commit = os.getenv("RENDER_GIT_COMMIT", "").strip()
    return commit[:7]


@router.get("/config")
def config() -> dict:
    return {
        "ai_provider": os.getenv("AI_PROVIDER", "gemini").lower(),
        "build": _config_build(),
    }


@router.post("/rag/ingest")
def rag_ingest(request: RagIngestRequest, http_request: Request):
    """Load a document into the knowledge base. Admin/demo only (Phase 1).

    Authentication/authorization is a Phase 2 requirement. If RAG_INGEST_TOKEN
    is set, the request must include a matching X-RAG-Ingest-Token header.
    """
    from app.rag.config import ingest_token, rag_enabled
    from app.rag.ingest import RAGIngestError, ingest_document

    expected = ingest_token()
    if expected:
        provided = http_request.headers.get("x-rag-ingest-token", "")
        if provided != expected:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "RAG_INGEST_UNAUTHORIZED",
                    "message": "Invalid or missing X-RAG-Ingest-Token.",
                },
            )

    if not rag_enabled():
        return JSONResponse(
            status_code=400,
            content={
                "error": "RAG_DISABLED",
                "message": "Set RAG_ENABLED=true to ingest documents.",
            },
        )

    try:
        result = ingest_document(
            document_id=request.document_id,
            title=request.title or request.document_id,
            source=request.source or "internal",
            content=request.content,
        )
    except RAGIngestError as exc:
        return JSONResponse(
            status_code=503,
            content={"error": "RAG_INGEST_FAILED", "message": str(exc)},
        )
    return result


@router.post("/analyze/stream")
def analyze_stream(
    request: AnalyzeRequest,
    http_request: Request,
    provider: AIProvider = Depends(get_provider),
):
    if not _claim_daily_run("analyze", _client_ip(http_request)):
        return _rate_limit_response("analyze")

    run_id = new_run_id()
    return StreamingResponse(
        _stream_workflow(
            request=request.user_request,
            clarification_answers=None,
            clarification_history=None,
            iteration=1,
            provider=provider,
            run_id=run_id,
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
    http_request: Request,
    provider: AIProvider = Depends(get_provider),
):
    estimate = request.analysis.get("estimate") or {}
    duration = str(estimate.get("duration_range") or "")
    if not estimate:
        return JSONResponse(
            status_code=422,
            content={
                "error": "ESTIMATE_REQUIRED",
                "message": "Run Analyze Request first so the standard estimate is available.",
            },
        )
    if not is_numeric_duration(duration):
        return JSONResponse(
            status_code=422,
            content={
                "error": "ESTIMATE_NOT_READY",
                "message": "A numeric independent estimate is required before running the optional AI scenario.",
            },
        )

    if not _claim_daily_run("optimize", _client_ip(http_request)):
        return _rate_limit_response("optimize")

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


@router.post("/close-deadline-gap/stream")
def close_deadline_gap_stream(
    request: OptimizeRequest,
    http_request: Request,
    provider: AIProvider = Depends(get_provider),
):
    analysis = request.analysis or {}
    if not gap_closing_eligible({**analysis, "user_request": request.user_request}):
        return JSONResponse(
            status_code=422,
            content={
                "error": "GAP_CLOSING_NOT_APPLICABLE",
                "message": (
                    "How to achieve customer deadline is only available when a hard "
                    "customer deadline is still exceeded after the AI-assisted scenario."
                ),
            },
        )

    if not _claim_daily_run("gap_close", _client_ip(http_request)):
        return _rate_limit_response("gap_close")

    return StreamingResponse(
        _stream_gap_close(
            request=request.user_request,
            analysis=analysis,
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
    http_request: Request,
    provider: AIProvider = Depends(get_provider),
):
    if not _claim_daily_run("analyze", _client_ip(http_request)):
        return _rate_limit_response("analyze")

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
    prior = _resolve_prior_state(request)
    run_id = request.run_id or new_run_id()

    return StreamingResponse(
        _stream_workflow(
            request=request.user_request,
            clarification_answers=answers,
            clarification_history=history,
            iteration=request.iteration + 1,
            provider=provider,
            resume_after_clarification=True,
            prior_state=prior,
            new_clarification_records=_new_clarification_records(request),
            run_id=run_id,
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
        prior = _resolve_prior_state(request)

        result = run_workflow(
            request=request.user_request,
            clarification_answers=answers,
            clarification_history=history,
            iteration=request.iteration + 1,
            provider=provider,
            resume_after_clarification=True,
            prior_state=prior,
            new_clarification_records=_new_clarification_records(request),
        )

        result["clarification_history"] = history
        response = workflow_response(result, run_id=request.run_id)
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
