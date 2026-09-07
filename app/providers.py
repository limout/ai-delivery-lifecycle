from abc import ABC, abstractmethod
import json
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors


load_dotenv()


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
        Generate structured JSON with retry handling for
        temporary Gemini availability/rate-limit errors.
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
                    raise RuntimeError(
                        "AI provider returned invalid JSON."
                    ) from exc

            except errors.ServerError as exc:
                if attempt >= self.max_retries:
                    raise

                time.sleep(self.retry_delay * (2**attempt))

            except errors.ClientError as exc:
                status_code = getattr(exc, "status_code", None)

                if status_code != 429 or attempt >= self.max_retries:
                    raise

                time.sleep(self.retry_delay * (2**attempt))


class MockProvider(AIProvider):
    """
    Deterministic provider used by automated tests.

    It does not call an external API.
    """

    def generate_json(self, prompt: str, schema: dict) -> dict:
        return {
            "problem": "Customer needs a software solution.",
            "business_goal": "Solve the customer's business need.",
            "users": [],
            "stakeholders": [],
            "existing_systems": [],
            "constraints": [],
            "assumptions": [],
            "unknowns": [
                "Target users",
                "Business success criteria",
                "Budget",
                "Timeline",
                "Existing systems",
            ],
            "clarification_questions": [
                "Who are the target users?",
                "What business outcome should the solution achieve?",
                "What is the expected timeline?",
                "What budget constraints exist?",
                "What existing systems need to be integrated?",
            ],
        }