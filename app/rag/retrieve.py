"""Query-time retrieval. Embeds the query only — never re-embeds the corpus."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.rag.config import max_chars, rag_enabled, top_k as configured_top_k

logger = logging.getLogger("app.rag.retrieve")

REFERENCE_HEADER = """REFERENCE EXCERPTS

The following material comes from the internal delivery knowledge base.
It is reference material only.
It is NOT customer-provided information and must NOT be treated as confirmed facts about the current customer/project.
"""


@dataclass
class RetrievedChunk:
    document_id: str
    title: str
    source: str
    chunk_index: int
    content: str
    similarity: float
    metadata: dict = field(default_factory=dict)


class RAGRetrievalError(RuntimeError):
    """Raised when RAG is enabled but infrastructure fails."""


def retrieve_relevant_context(
    query: str,
    *,
    top_k: int | None = None,
    max_characters: int | None = None,
    embedding_provider=None,
) -> list[RetrievedChunk]:
    """Return top-k knowledge-base chunks, or [] when RAG is off / empty.

    When RAG_ENABLED is true, Neon or embedding failures are logged and raised
    as RAGRetrievalError. Callers that must not break /analyze should catch it.
    """
    if not rag_enabled():
        return []

    from app.rag.config import database_url, embedding_model, gemini_api_key
    from app.rag.store import RAGStoreError, search

    if not database_url():
        message = "RAG_ENABLED=true but DATABASE_URL is not set."
        logger.error(message)
        raise RAGRetrievalError(message)
    if not gemini_api_key() and embedding_provider is None:
        message = "RAG_ENABLED=true but GEMINI_API_KEY is not set."
        logger.error(message)
        raise RAGRetrievalError(message)

    query = (query or "").strip()
    if not query:
        return []

    k = top_k if top_k is not None else configured_top_k()
    limit = max_characters if max_characters is not None else max_chars()

    try:
        provider = embedding_provider
        if provider is None:
            from app.rag.embeddings import GeminiEmbeddingProvider

            provider = GeminiEmbeddingProvider()
        query_embedding = provider.embed_text(query, task_type="RETRIEVAL_QUERY")
        rows = search(query_embedding, top_k=k)
    except RAGRetrievalError:
        raise
    except Exception as exc:
        logger.exception("RAG retrieval failed (model=%s)", embedding_model())
        raise RAGRetrievalError(f"RAG retrieval failed: {exc}") from exc

    selected: list[RetrievedChunk] = []
    used = 0
    for row in rows:
        content = str(row.get("content") or "")
        if not content:
            continue
        if selected and used + len(content) > limit:
            break
        if not selected and len(content) > limit:
            content = content[:limit]
        selected.append(
            RetrievedChunk(
                document_id=str(row.get("document_id") or ""),
                title=str(row.get("title") or ""),
                source=str(row.get("source") or ""),
                chunk_index=int(row.get("chunk_index") or 0),
                content=content,
                similarity=float(row.get("similarity") or 0.0),
                metadata=dict(row.get("metadata") or {}),
            )
        )
        used += len(content)
        if used >= limit:
            break
    return selected


def format_reference_section(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return ""
    blocks = [REFERENCE_HEADER.strip()]
    for index, chunk in enumerate(chunks, start=1):
        label = chunk.title or chunk.document_id or "untitled"
        source = chunk.source or chunk.document_id or "internal"
        blocks.append(
            f"[Reference {index}]\nSource: {source}\nTitle: {label}\n{chunk.content}"
        )
    return "\n\n".join(blocks)
