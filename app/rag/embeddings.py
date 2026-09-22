"""Gemini embedding API wrapper. Not the LLM generate_json path."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.rag.config import embedding_dim, embedding_model, gemini_api_key


class EmbeddingError(RuntimeError):
    """Raised when the embedding API fails."""


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_text(self, text: str, *, task_type: str = "RETRIEVAL_QUERY") -> list[float]:
        raise NotImplementedError

    def embed_texts(
        self,
        texts: list[str],
        *,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> list[list[float]]:
        return [self.embed_text(item, task_type=task_type) for item in texts]


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Uses google.genai Client.models.embed_content (same SDK as GeminiProvider)."""

    def __init__(self, client=None, model: str | None = None):
        self.model = model or embedding_model()
        self.client = client
        if self.client is None:
            api_key = gemini_api_key()
            if not api_key:
                raise EmbeddingError(
                    "GEMINI_API_KEY is required to generate embeddings."
                )
            from google import genai

            self.client = genai.Client(api_key=api_key)

    def embed_text(self, text: str, *, task_type: str = "RETRIEVAL_QUERY") -> list[float]:
        vectors = self.embed_texts([text], task_type=task_type)
        if not vectors:
            raise EmbeddingError("Gemini embedding API returned no vectors.")
        return vectors[0]

    def embed_texts(
        self,
        texts: list[str],
        *,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> list[list[float]]:
        if not texts:
            return []
        from google.genai import types

        dim = embedding_dim()
        try:
            result = self.client.models.embed_content(
                model=self.model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=dim,
                ),
            )
        except Exception as exc:
            raise EmbeddingError(f"Gemini embedding API failed: {exc}") from exc

        embeddings = getattr(result, "embeddings", None) or []
        values: list[list[float]] = []
        for item in embeddings:
            raw = getattr(item, "values", None)
            if raw is None:
                raise EmbeddingError("Gemini embedding API returned an empty vector.")
            vector = [float(v) for v in raw]
            if len(vector) != dim:
                raise EmbeddingError(
                    f"Gemini embedding API returned {len(vector)} dimensions; "
                    f"RAG_EMBEDDING_DIM={dim}."
                )
            values.append(vector)
        if len(values) != len(texts):
            raise EmbeddingError(
                f"Gemini embedding API returned {len(values)} vectors for {len(texts)} texts."
            )
        return values
