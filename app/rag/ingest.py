"""Ingest documents: chunk → Gemini embeddings → Neon pgvector.

Embeddings for corpus text are created only here, never on /analyze.
"""

from __future__ import annotations

import hashlib
import logging

from app.rag.chunk import chunk_document
from app.rag.config import collection_name, database_url, rag_enabled
from app.rag.store import (
    RAGStoreError,
    connect_for_read,
    document_content_hash,
    replace_document_chunks,
)

logger = logging.getLogger("app.rag.ingest")


class RAGIngestError(RuntimeError):
    """Raised when ingestion cannot run."""


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def ingest_document(
    document_id: str,
    title: str,
    source: str,
    content: str,
    *,
    embedding_provider=None,
) -> dict:
    if not rag_enabled():
        raise RAGIngestError("RAG_ENABLED is false; ingestion is disabled.")
    if not database_url():
        raise RAGIngestError("DATABASE_URL is required to ingest documents.")
    document_id = (document_id or "").strip()
    if not document_id:
        raise RAGIngestError("document_id is required.")
    content = content or ""
    if not content.strip():
        raise RAGIngestError("content is empty.")

    digest = _content_hash(content)
    conn = connect_for_read()
    try:
        existing = document_content_hash(conn, document_id)
    finally:
        conn.close()

    if existing == digest:
        logger.info("Skipping ingest for %s; content hash unchanged.", document_id)
        return {
            "document_id": document_id,
            "chunks": 0,
            "skipped": True,
            "reason": "unchanged",
        }

    pieces = chunk_document(
        content,
        document_id=document_id,
        title=title or document_id,
        source=source or "internal",
    )
    if not pieces:
        raise RAGIngestError("Chunking produced no chunks.")

    try:
        provider = embedding_provider
        if provider is None:
            from app.rag.embeddings import GeminiEmbeddingProvider

            provider = GeminiEmbeddingProvider()
        vectors = provider.embed_texts(
            [item["content"] for item in pieces],
            task_type="RETRIEVAL_DOCUMENT",
        )
    except RAGIngestError:
        raise
    except Exception as exc:
        logger.exception("Embedding failed during ingest of %s", document_id)
        raise RAGIngestError(f"Embedding failed: {exc}") from exc

    records = []
    for piece, vector in zip(pieces, vectors):
        records.append(
            {
                **piece,
                "embedding": vector,
                "content_hash": digest,
                "metadata": {
                    "collection": collection_name(),
                    "content_hash": digest,
                },
            }
        )

    try:
        stored = replace_document_chunks(records)
    except RAGStoreError as exc:
        logger.exception("Store failed during ingest of %s", document_id)
        raise RAGIngestError(str(exc)) from exc

    logger.info("Ingested %s (%s chunks, dim=%s).", document_id, stored, len(vectors[0]))
    return {
        "document_id": document_id,
        "chunks": stored,
        "skipped": False,
        "embedding_dimension": len(vectors[0]),
        "embedding_model": getattr(provider, "model", None),
    }
