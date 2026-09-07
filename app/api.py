from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.graph import build_graph
from app.providers import (
    AIProvider,
    AIProviderQuotaError,
    GeminiProvider,
)


app = FastAPI(
    title="AI Delivery Lifecycle",
    description="Agentic AI workflow for software delivery lifecycle.",
    version="0.1.0",
)


class AnalyzeRequest(BaseModel):
    user_request: str = Field(min_length=1)


class ClarifyRequest(BaseModel):
    user_request: str = Field(min_length=1)
    clarification_answers: list[str] = Field(default_factory=list)
    iteration: int = Field(default=1, ge=1)


def get_provider() -> AIProvider:
    return GeminiProvider()


def run_workflow(
    request: str,
    clarification_answers: list[str] | None = None,
    iteration: int | None = None,
    provider: AIProvider | None = None,
) -> dict:
    graph = build_graph(provider)

    state = {
        "user_request": request,
    }

    if clarification_answers:
        state["clarification_answers"] = clarification_answers

    if iteration is not None:
        state["iteration"] = iteration

    return graph.invoke(state)


def workflow_response(result: dict) -> dict:
    return {
        "status": result["validation"]["status"],
        "discovery": result["discovery"],
        "requirements": result["requirements"],
        "validation": result["validation"],
        "clarification_questions": result.get(
            "clarification_questions",
            [],
        ),
        "iteration": result.get("iteration"),
    }


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
    }


@app.post("/analyze")
def analyze(
    request: AnalyzeRequest,
    provider: AIProvider = Depends(get_provider),
):
    try:
        result = run_workflow(
            request=request.user_request,
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


@app.post("/clarify")
def clarify(
    request: ClarifyRequest,
    provider: AIProvider = Depends(get_provider),
):
    try:
        result = run_workflow(
            request=request.user_request,
            clarification_answers=request.clarification_answers,
            iteration=request.iteration,
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