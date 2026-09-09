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


def _parse_json_text(raw_text: str, provider_name: str) -> dict:
    """
    Parse JSON returned by an AI provider.

    Some models/providers return valid JSON wrapped in markdown fences or
    followed by a small amount of extra text. Structured-output providers
    should normally return plain JSON, but accepting these harmless wrappers
    makes the integration more robust without weakening schema validation.
    """
    if not isinstance(raw_text, str):
        raise AIProviderError(
            f"{provider_name} returned an unexpected JSON value."
        )

    text = raw_text.strip()
    if not text:
        raise AIProviderError(f"{provider_name} returned an empty response.")

    # Remove the common markdown wrapper: ```json ... ```
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().lower().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # First try the ideal case: the whole response is JSON.
    try:
        result = json.loads(text)
        if not isinstance(result, dict):
            raise AIProviderError(
                f"{provider_name} returned JSON, but the root value is not an object."
            )
        return result
    except json.JSONDecodeError:
        pass

    # If the model added a short prefix/suffix, recover the first JSON object.
    # JSONDecoder.raw_decode ensures we parse one complete object rather than
    # guessing where the JSON ends.
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            result, _ = decoder.raw_decode(text[index:])
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            continue

    preview = text[:500].replace("\n", "\\n")
    raise AIProviderError(
        f"{provider_name} returned invalid JSON. "
        f"Response preview: {preview}"
    )


class AIProvider(ABC):
    @abstractmethod
    def generate_json(self, prompt: str, schema: dict) -> dict:
        raise NotImplementedError


class GeminiProvider(AIProvider):
    def __init__(
        self,
        model: str | None = None,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is not configured."
            )

        self.client = genai.Client(api_key=api_key)
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def generate_json(self, prompt: str, schema: dict) -> dict:
        started_at = time.perf_counter()
        print(
            f"[GEMINI] START model={self.model} "
            f"prompt_chars={len(prompt)} schema_keys={len(schema)}"
        )

        for attempt in range(self.max_retries + 1):
            try:
                print(
                    f"[GEMINI] REQUEST model={self.model} "
                    f"attempt={attempt + 1}/{self.max_retries + 1}"
                )

                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": schema,
                    },
                )

                elapsed = time.perf_counter() - started_at
                raw_text = response.text
                print(
                    f"[GEMINI] HTTP DONE model={self.model} "
                    f"elapsed={elapsed:.2f}s response_chars={len(raw_text or '')}"
                )

                return _parse_json_text(raw_text, "Gemini")

            except errors.ServerError as exc:
                status_code = getattr(exc, "status_code", None)
                print(
                    f"[GEMINI] SERVER ERROR type={type(exc).__name__} "
                    f"status={status_code} message={exc}"
                )

                if attempt >= self.max_retries:
                    raise AIProviderError(
                        "Gemini is temporarily unavailable. "
                        f"type={type(exc).__name__}, status={status_code}, "
                        f"message={exc}"
                    ) from exc

                time.sleep(self.retry_delay * (2**attempt))

            except errors.ClientError as exc:
                status_code = getattr(exc, "status_code", None)
                if status_code is None:
                    status_code = getattr(exc, "code", None)

                print(
                    f"[GEMINI] CLIENT ERROR type={type(exc).__name__} "
                    f"status={status_code} message={exc}"
                )

                if status_code == 429:
                    raise AIProviderQuotaError(
                        "Gemini quota/rate limit reached. "
                        f"message={exc}"
                    ) from exc

                raise AIProviderError(
                    "Gemini request failed. "
                    f"type={type(exc).__name__}, status={status_code}, "
                    f"message={exc}"
                ) from exc

            except AIProviderError:
                raise

            except Exception as exc:
                # Keep the real SDK/network exception visible. The previous
                # implementation converted some exceptions into the useless
                # "status None" message, which made diagnosis impossible.
                elapsed = time.perf_counter() - started_at
                status_code = getattr(exc, "status_code", None)
                if status_code is None:
                    status_code = getattr(exc, "code", None)

                print(
                    f"[GEMINI] UNEXPECTED ERROR model={self.model} "
                    f"elapsed={elapsed:.2f}s type={type(exc).__name__} "
                    f"status={status_code} message={exc!r}"
                )

                raise AIProviderError(
                    "Gemini request failed. "
                    f"type={type(exc).__name__}, status={status_code}, "
                    f"message={exc}"
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

        result = _parse_json_text(raw_text, "OpenRouter")

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
        model: str | None = None,
        base_url: str | None = None,
        timeout: int = 180,
    ):
        # Keep local Ollama as the default, while allowing the exact same
        # provider to talk to Ollama Cloud when OLLAMA_API_KEY is configured.
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen3:8b")
        self.base_url = (
            base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")
        self.api_key = os.getenv("OLLAMA_API_KEY")
        self.timeout = timeout
        self.is_cloud = self.base_url == "https://ollama.com"

    def generate_json(self, prompt: str, schema: dict) -> dict:
        # Ollama local supports structured outputs via `format=schema`.
        # Ollama Cloud is handled more conservatively: put the schema in the
        # prompt and do not send `format`, because Cloud may return natural
        # language/Markdown even when a schema is supplied.
        if self.is_cloud:
            schema_text = json.dumps(schema, ensure_ascii=False, indent=2)
            cloud_prompt = (
                "IMPORTANT OUTPUT RULES:\n"
                "Return ONLY one valid JSON object.\n"
                "Do not use Markdown.\n"
                "Do not use ```json fences.\n"
                "Do not write an explanation before or after the JSON.\n"
                "Do not return a table.\n"
                "Do not return a report or prose.\n"
                "The JSON object MUST conform to this JSON Schema:\n"
                f"{schema_text}\n\n"
                "TASK:\n"
                f"{prompt}"
            )
            payload = {
                "model": self.model,
                "prompt": cloud_prompt,
                "stream": False,
                "think": False,
                "options": {"temperature": 0},
            }
        else:
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

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        started_at = time.perf_counter()
        mode = "cloud" if self.is_cloud else "local"
        print(
            f"[OLLAMA] START mode={mode} model={self.model} "
            f"prompt_chars={len(prompt)}"
        )

        # Cloud can occasionally drop a connection between sequential agent
        # calls. This is especially relevant on the Free plan, where Ollama
        # allows only one concurrent request. Retry transient connection and
        # server failures, but do not retry authentication/quota errors.
        max_retries = 2 if self.is_cloud else 0
        retry_delays = (5, 10)

        response = None
        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    f"{self.base_url}/api/generate",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                if attempt < max_retries:
                    delay = retry_delays[attempt]
                    print(
                        f"[OLLAMA] RETRY {attempt + 1}/{max_retries} "
                        f"mode={mode} reason=connection_error wait={delay}s"
                    )
                    time.sleep(delay)
                    continue

                if self.is_cloud:
                    raise AIProviderError(
                        "Could not connect to Ollama Cloud after "
                        f"{max_retries + 1} attempts."
                    ) from exc

                raise AIProviderError(
                    "Could not connect to Ollama. "
                    "Make sure Ollama is running on localhost:11434."
                ) from exc

            # Retry only transient server-side failures. 4xx responses are
            # handled below because they usually indicate auth/quota/request
            # problems rather than a temporary connection issue.
            if response.status_code in (500, 502, 503, 504) and attempt < max_retries:
                delay = retry_delays[attempt]
                print(
                    f"[OLLAMA] RETRY {attempt + 1}/{max_retries} "
                    f"mode={mode} status={response.status_code} wait={delay}s"
                )
                time.sleep(delay)
                continue

            break

        if response.status_code in (401, 403):
            if self.is_cloud:
                raise AIProviderError(
                    "Ollama Cloud authentication failed. "
                    "Check OLLAMA_API_KEY."
                )

            raise AIProviderError(
                f"Ollama request failed with status "
                f"{response.status_code}: {response.text}"
            )

        if response.status_code in (402, 429):
            raise AIProviderQuotaError(
                f"Ollama quota/rate limit reached (HTTP {response.status_code})."
            )

        if response.status_code != 200:
            raise AIProviderError(
                f"Ollama request failed with status "
                f"{response.status_code}: {response.text}"
            )

        elapsed = time.perf_counter() - started_at
        print(
            f"[OLLAMA] HTTP DONE mode={mode} model={self.model} "
            f"elapsed={elapsed:.2f}s status={response.status_code}"
        )

        try:
            data = response.json()
        except ValueError as exc:
            raise AIProviderError(
                "Ollama returned an invalid HTTP response."
            ) from exc

        raw_text = data.get("response")
        if not raw_text:
            raise AIProviderError("Ollama returned an empty response.")

        result = _parse_json_text(raw_text, "Ollama")
        total_elapsed = time.perf_counter() - started_at
        print(
            f"[OLLAMA] COMPLETE mode={mode} model={self.model} "
            f"elapsed={total_elapsed:.2f}s response_chars={len(raw_text)}"
        )
        return result


# Mock provider used by automated tests.
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
