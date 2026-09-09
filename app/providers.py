from abc import ABC, abstractmethod
import json
import os
import time

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import errors


load_dotenv()


class AIProviderError(RuntimeError):
    """Base exception for AI provider failures."""


class AIProviderQuotaError(AIProviderError):
    """Raised when the AI provider quota has been exceeded."""


class AIProvider(ABC):
    @abstractmethod
    def generate_json(self, prompt: str, schema: dict) -> dict:
        raise NotImplementedError


class GeminiProvider(AIProvider):
    def __init__(
        self,
        model: str = "gemini-3.6-flash",
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is not configured."
            )

        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def generate_json(self, prompt: str, schema: dict) -> dict:
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": schema,
                    },
                )

                try:
                    return json.loads(response.text)
                except json.JSONDecodeError as exc:
                    raise AIProviderError(
                        "AI provider returned invalid JSON."
                    ) from exc

            except errors.ServerError as exc:
                if attempt >= self.max_retries:
                    raise AIProviderError(
                        "AI provider is temporarily unavailable."
                    ) from exc
                time.sleep(self.retry_delay * (2**attempt))

            except errors.ClientError as exc:
                status_code = getattr(exc, "status_code", None)

                if status_code == 429:
                    raise AIProviderQuotaError(
                        "AI provider quota has been exceeded."
                    ) from exc

                raise AIProviderError(
                    f"AI provider request failed with status {status_code}."
                ) from exc


class OpenRouterProvider(AIProvider):
    """OpenRouter provider with strict JSON-schema output support."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int = 180,
    ):
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY environment variable is not configured."
            )

        self.api_key = api_key
        self.model = model or os.getenv(
            "OPENROUTER_MODEL",
            "openrouter/free",
        )
        self.base_url = (
            base_url or os.getenv(
                "OPENROUTER_BASE_URL",
                "https://openrouter.ai/api/v1",
            )
        ).rstrip("/")
        self.timeout = timeout

    def generate_json(self, prompt: str, schema: dict) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "delivery_lifecycle_output",
                    "strict": True,
                    "schema": schema,
                },
            },
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        site_url = os.getenv("OPENROUTER_SITE_URL")
        site_name = os.getenv("OPENROUTER_SITE_NAME", "AI Delivery Lifecycle")
        if site_url:
            headers["HTTP-Referer"] = site_url
        if site_name:
            headers["X-OpenRouter-Title"] = site_name

        started_at = time.perf_counter()
        print(
            f"[OPENROUTER] START model={self.model} "
            f"prompt_chars={len(prompt)}"
        )

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise AIProviderError(
                "Could not connect to OpenRouter."
            ) from exc

        elapsed = time.perf_counter() - started_at
        print(
            f"[OPENROUTER] HTTP DONE model={self.model} "
            f"elapsed={elapsed:.2f}s status={response.status_code}"
        )

        if response.status_code in (402, 429):
            raise AIProviderQuotaError(
                f"OpenRouter quota/rate limit reached (HTTP {response.status_code})."
            )

        if response.status_code != 200:
            raise AIProviderError(
                f"OpenRouter request failed with status "
                f"{response.status_code}: {response.text}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise AIProviderError(
                "OpenRouter returned an invalid HTTP response."
            ) from exc

        try:
            raw_text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(
                "OpenRouter returned an unexpected response format."
            ) from exc

        if not raw_text:
            raise AIProviderError("OpenRouter returned an empty response.")

        try:
            result = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise AIProviderError("OpenRouter returned invalid JSON.") from exc

        total_elapsed = time.perf_counter() - started_at
        usage = data.get("usage") or {}
        print(
            f"[OPENROUTER] COMPLETE model={self.model} "
            f"elapsed={total_elapsed:.2f}s "
            f"response_chars={len(raw_text)} "
            f"input_tokens={usage.get('prompt_tokens', '?')} "
            f"output_tokens={usage.get('completion_tokens', '?')}"
        )
        return result


class OllamaProvider(AIProvider):
    def __init__(
        self,
        model: str = "qwen3:8b",
        base_url: str = "http://localhost:11434",
        timeout: int = 180,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate_json(self, prompt: str, schema: dict) -> dict:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": schema,
            # Qwen3 enables reasoning by default. For structured agent output
            # we do not need hidden chain-of-thought; disabling it prevents
            # clarification re-runs from getting stuck in long reasoning.
            "think": False,
            "options": {"temperature": 0},
        }

        started_at = time.perf_counter()
        print(f"[OLLAMA] START model={self.model} prompt_chars={len(prompt)}")

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise AIProviderError(
                "Could not connect to Ollama. "
                "Make sure Ollama is running on localhost:11434."
            ) from exc

        if response.status_code != 200:
            raise AIProviderError(
                f"Ollama request failed with status "
                f"{response.status_code}: {response.text}"
            )

        elapsed = time.perf_counter() - started_at
        print(f"[OLLAMA] HTTP DONE model={self.model} elapsed={elapsed:.2f}s status={response.status_code}")

        try:
            data = response.json()
        except ValueError as exc:
            raise AIProviderError(
                "Ollama returned an invalid HTTP response."
            ) from exc

        raw_text = data.get("response")
        if not raw_text:
            raise AIProviderError("Ollama returned an empty response.")

        try:
            result = json.loads(raw_text)
            total_elapsed = time.perf_counter() - started_at
            print(f"[OLLAMA] COMPLETE model={self.model} elapsed={total_elapsed:.2f}s response_chars={len(raw_text)}")
            return result
        except json.JSONDecodeError as exc:
            raise AIProviderError("Ollama returned invalid JSON.") from exc


# FIX for app/providers.py
#
# Keep the existing GeminiProvider and OllamaProvider unchanged.
# Replace ONLY the existing MockProvider class with the class below.
#
# This preserves the current mock behavior while adding the new
# validation field: non_blocking_questions.

class MockProvider(AIProvider):
    """Deterministic provider used by automated tests."""

    def generate_json(self, prompt: str, schema: dict) -> dict:
        prompt_lower = prompt.lower()

        if "requirements definition" in prompt_lower:
            has_salesforce = "Salesforce" in prompt
            has_timeline = (
                "2 months" in prompt_lower
                or "two months" in prompt_lower
                or "target delivery timeline: 2 months" in prompt_lower
            )

            functional_requirements = [
                "The system should provide a self-service interface."
            ]

            if has_salesforce:
                functional_requirements.append(
                    "The portal must integrate with Salesforce."
                )

            open_questions = []
            if not has_timeline:
                open_questions.append(
                    "What is the target delivery timeline?"
                )

            return {
                "functional_requirements": functional_requirements,
                "non_functional_requirements": [
                    "The system should support appropriate enterprise security controls."
                ],
                "acceptance_criteria": [
                    "An authorized enterprise user can access the self-service interface."
                ],
                "open_questions": open_questions,
                "contradictions": [],
            }

        # IMPORTANT: this branch must return the validation schema.
        if "whether the project definition is" in prompt_lower:
            has_timeline = (
                "2 months" in prompt_lower
                or "two months" in prompt_lower
                or "target delivery timeline: 2 months" in prompt_lower
            )

            if has_timeline:
                return {
                    "status": "READY",
                    "reasons": [
                        "The available information is sufficient for preliminary solution shaping."
                    ],
                    "questions": [],
                    "non_blocking_questions": [
                        "Detailed feature and scale refinements can be clarified during solution and planning."
                    ],
                }

            return {
                "status": "NEEDS_INFO",
                "reasons": [
                    "The target delivery timeline is a blocking constraint for preliminary planning."
                ],
                "questions": [
                    "What is the target delivery timeline?"
                ],
                "non_blocking_questions": [],
            }

        if "discovery assessment" in prompt_lower:
            has_salesforce = "Salesforce" in prompt

            has_timeline = (
                "2 months" in prompt_lower
                or "two months" in prompt_lower
                or "target delivery timeline: 2 months" in prompt_lower
            )

            unknowns = []
            clarification_questions = []
            constraints = []

            if not has_timeline:
                unknowns.append("Target delivery timeline")
                clarification_questions.append(
                    "What is the target delivery timeline?"
                )
            else:
                constraints.append("Target delivery timeline: 2 months")

            existing_systems = []
            if has_salesforce:
                existing_systems.append("Salesforce")

            return {
                "problem": (
                    "Enterprise customers need a self-service way to interact with the company."
                ),
                "business_goal": (
                    "Improve customer self-service and reduce operational support effort."
                ),
                "users": ["Enterprise customers"],
                "stakeholders": [
                    "Customer Success",
                    "Account Management",
                    "Enterprise Client Administrators",
                ],
                "existing_systems": existing_systems,
                "constraints": constraints,
                "assumptions": [
                    "The solution will require enterprise authentication and access control."
                ],
                "unknowns": unknowns,
                "clarification_questions": clarification_questions,
            }

        # Preserve the existing generic fallback.
        return {
            "problem": "Customer needs a software solution.",
            "business_goal": "Solve the customer's business need.",
            "users": [],
            "stakeholders": [],
            "existing_systems": [],
            "constraints": [],
            "assumptions": [],
            "unknowns": ["Target delivery timeline"],
            "clarification_questions": [
                "What is the target delivery timeline?"
            ],
        }
