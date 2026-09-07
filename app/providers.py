from abc import ABC, abstractmethod
import json
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors


load_dotenv()


class AIProviderError(RuntimeError):
    """Base exception for AI provider failures."""


class AIProviderQuotaError(AIProviderError):
    """Raised when the AI provider quota has been exceeded."""


class AIProvider(ABC):
    """
    Interface for an AI model provider.

    Agents depend on this interface instead of a specific LLM.
    """

    @abstractmethod
    def generate_json(self, prompt: str, schema: dict) -> dict:
        """
        Generate structured JSON from a prompt.
        """
        raise NotImplementedError


class GeminiProvider(AIProvider):
    """
    Gemini implementation of the AIProvider interface.
    """

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
        """
        Generate structured JSON.

        Temporary server failures are retried.
        Quota/rate-limit errors are surfaced immediately because
        retrying does not help when the project quota is exhausted.
        """

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


class MockProvider(AIProvider):
    """
    Deterministic provider used by automated tests.

    It does not call an external API.
    """

    def generate_json(self, prompt: str, schema: dict) -> dict:

        if "requirements definition" in prompt:
            return {
                "functional_requirements": [
                    "The system should provide a self-service interface.",
                ],
                "non_functional_requirements": [
                    "The system should support appropriate enterprise security controls."
                ],
                "acceptance_criteria": [
                    "An authorized enterprise user can access the self-service interface."
                ],
                "open_questions": [],
                "contradictions": [],
            }

        if "whether the project definition is" in prompt:
            return {
                "status": "NEEDS_INFO",
                "reasons": [
                    "The target delivery timeline is not known."
                ],
                "questions": [
                    "What is the target delivery timeline?"
                ],
            }

        return {
            "problem": "Customer needs a software solution.",
            "business_goal": "Solve the customer's business need.",
            "users": [],
            "stakeholders": [],
            "existing_systems": [],
            "constraints": [],
            "assumptions": [],
            "unknowns": [
                "Target delivery timeline",
            ],
            "clarification_questions": [
                "What is the target delivery timeline?",
            ],
        }