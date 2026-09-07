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
            "options": {"temperature": 0},
        }

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
            return json.loads(raw_text)
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
        properties = set(schema.get("properties", {}))

        if "clarification_questions" in properties and "business_goal" in properties:
            has_salesforce = "salesforce" in prompt_lower
            has_timeline = "2 months" in prompt_lower or "two months" in prompt_lower or "target delivery timeline: 2 months" in prompt_lower
            return {
                "problem": "Enterprise customers need a self-service way to interact with the company.",
                "business_goal": "Improve customer self-service and reduce operational support effort.",
                "users": ["Enterprise customers"],
                "stakeholders": ["Customer Success", "Account Management", "Enterprise Client Administrators"],
                "existing_systems": ["Salesforce"] if has_salesforce else [],
                "constraints": ["Target delivery timeline: 2 months"] if has_timeline else [],
                "assumptions": ["The solution will require enterprise authentication and access control."],
                "unknowns": [] if has_timeline else ["Target delivery timeline"],
                "clarification_questions": [] if has_timeline else ["What is the target delivery timeline?"],
            }

        if "functional_requirements" in properties:
            has_salesforce = "salesforce" in prompt_lower
            has_timeline = "2 months" in prompt_lower or "two months" in prompt_lower or "target delivery timeline: 2 months" in prompt_lower
            return {
                "functional_requirements": ["The system should provide a self-service interface."] + (["The portal must integrate with Salesforce."] if has_salesforce else []),
                "non_functional_requirements": ["The system should support appropriate enterprise security controls."],
                "acceptance_criteria": ["An authorized enterprise user can access the self-service interface."],
                "open_questions": [] if has_timeline else ["What is the target delivery timeline?"],
                "contradictions": [],
            }

        if "non_blocking_questions" in properties and "status" in properties:
            has_timeline = "2 months" in prompt_lower or "two months" in prompt_lower or "target delivery timeline: 2 months" in prompt_lower
            if has_timeline:
                return {
                    "status": "READY",
                    "reasons": ["The available information is sufficient for preliminary solution shaping."],
                    "questions": [],
                    "non_blocking_questions": ["Detailed feature and scale refinements can be clarified during solution and planning."],
                }
            return {
                "status": "NEEDS_INFO",
                "reasons": ["The target delivery timeline is a blocking constraint for preliminary planning."],
                "questions": ["What is the target delivery timeline?"],
                "non_blocking_questions": [],
            }

        if "solution_summary" in properties:
            return {
                "solution_summary": "A customer self-service portal with enterprise authentication and integration with existing systems.",
                "key_capabilities": ["Customer self-service access", "Account information access", "Support request submission and tracking", "Documentation access"],
                "integration_approach": ["Integrate with Salesforce where customer and support data is managed.", "Use enterprise identity integration for authentication."],
                "technical_considerations": ["Enterprise authentication and authorization", "Secure integration with existing systems", "Auditability and data protection"],
                "delivery_risks": ["Integration complexity may affect the two-month target."],
                "dependencies": ["Access to Salesforce integration capabilities", "Availability of enterprise identity configuration"],
                "assumptions": ["Detailed integration specifications will be confirmed during implementation planning."],
            }

        if "delivery_phases" in properties:
            return {
                "delivery_phases": ["Solution and technical design", "Portal implementation", "Integration and authentication", "Testing and readiness", "Launch"],
                "workstreams": ["Portal experience", "Salesforce integration", "Identity and access", "Documentation", "Testing and release"],
                "dependencies": ["Salesforce integration access", "Microsoft Entra ID configuration"],
                "milestones": ["Solution design complete", "Core portal complete", "Integrations validated", "Release readiness complete"],
                "team_roles": ["Delivery Lead", "Solution Architect", "Software Engineers", "QA Engineer"],
                "delivery_risks": ["Integration dependencies may affect schedule."],
            }

        if "effort_range" in properties:
            return {
                "effort_range": "Indicative: 10–16 person-weeks",
                "duration_range": "Indicative: 8–10 weeks",
                "confidence": "MEDIUM",
                "assumptions": ["Required Salesforce and identity access is available.", "Scope remains limited to identified capabilities."],
                "risks_affecting_estimate": ["Unknown integration complexity", "Security and compliance requirements", "Detailed scope refinement"],
            }

        if "executive_summary" in properties:
            return {
                "executive_summary": "Deliver an enterprise customer self-service portal that improves self-service while integrating with existing enterprise systems.",
                "scope": ["Customer self-service portal", "Account information access", "Support request submission and tracking", "Documentation access", "Enterprise authentication", "Salesforce integration"],
                "delivery_approach": ["Iterative delivery with early integration validation", "Progressive testing and release readiness"],
                "timeline": "Indicative target: approximately two months.",
                "assumptions": ["Integration access is available.", "Detailed requirements are refined during delivery."],
                "risks": ["Integration and security requirements may affect scope and schedule."],
                "next_steps": ["Confirm detailed scope", "Validate integration dependencies", "Agree delivery plan and commercial terms"],
            }

        if "deliverables" in properties and "in_scope" in properties:
            return {
                "objectives": ["Provide enterprise customers with a self-service portal and improve customer support efficiency."],
                "deliverables": ["Customer self-service portal", "Salesforce integration", "Enterprise authentication integration", "Support request workflow", "Documentation access", "Testing and release readiness"],
                "in_scope": ["Portal capabilities identified in the requirements", "Required Salesforce integration", "Enterprise authentication"],
                "out_of_scope": ["Features not identified in the confirmed scope", "Commercial or contractual terms"],
                "dependencies": ["Salesforce access and integration capabilities", "Microsoft Entra ID configuration", "Customer availability for clarification and validation"],
                "acceptance": ["Authorized enterprise users can access the portal.", "Supported customer self-service capabilities are available.", "Required integrations are validated."],
                "timeline": "Indicative target: approximately two months.",
                "assumptions": ["Timeline and estimate remain indicative until scope and dependencies are confirmed.", "No additional contractual terms are implied."],
            }

        return {key: ([] if value.get("type") == "array" else "") for key, value in schema.get("properties", {}).items()}
