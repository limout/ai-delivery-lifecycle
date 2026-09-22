"""PostgreSQL + pgvector storage. Connects only when RAG operations run."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from app.rag.config import collection_name, database_url

TABLE = "rag_documents"


class RAGStoreError(RuntimeError):
    """Raised when Neon/pgvector operations fail."""


def _connect(url: str | None = None):
    dsn = url if url is not None else database_url()
    if not dsn:
        raise RAGStoreError("DATABASE_URL is not configured.")
    try:
        import psycopg
        from pgvector.psycopg import register_vector
    except ImportError as exc:
        raise RAGStoreError(
            "psycopg and pgvector are required when RAG is enabled."
        ) from exc

    try:
        conn = psycopg.connect(dsn)
        register_vector(conn)
    except Exception as exc:
        raise RAGStoreError(f"Could not connect to PostgreSQL: {exc}") from exc
    return conn


def _existing_embedding_dim(conn) -> int | None:
    """Read the live column type, e.g. vector(1536), rather than assuming a size."""
    import re

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT format_type(a.atttypid, a.atttypmod)
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            WHERE c.relname = %s
              AND a.attname = 'embedding'
              AND a.attnum > 0
              AND NOT a.attisdropped
            """,
            (TABLE,),
        )
        row = cur.fetchone()
    if not row or not row[0]:
        return None
    match = re.search(r"vector\((\d+)\)", str(row[0]))
    if not match:
        return None
    return int(match.group(1))


def _table_exists(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_name = %s
            """,
            (TABLE,),
        )
        return cur.fetchone() is not None


def initialize(embedding_dim: int, url: str | None = None) -> int:
    """Create extension, table, and cosine index. Safe to run repeatedly.

    embedding_dim must come from an actual embedding vector length, not a guess.
    """
    if embedding_dim < 1:
        raise RAGStoreError("embedding_dim must be a positive integer from the embedding API.")

    conn = _connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.commit()

        existing = _existing_embedding_dim(conn) if _table_exists(conn) else None
        if existing is not None and existing != embedding_dim:
            raise RAGStoreError(
                f"rag_documents.embedding is vector({existing}) but the embedding "
                f"API returned {embedding_dim} dimensions. Recreate the table or "
                f"use the same GEMINI_EMBEDDING_MODEL."
            )

        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id UUID PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    collection TEXT NOT NULL,
                    title TEXT,
                    source TEXT,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    metadata JSONB,
                    embedding vector({embedding_dim}) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS rag_documents_document_id_idx
                ON {TABLE} (document_id)
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS rag_documents_collection_idx
                ON {TABLE} (collection)
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS rag_documents_embedding_cosine_idx
                ON {TABLE}
                USING hnsw (embedding vector_cosine_ops)
                """
            )
        conn.commit()
        return embedding_dim
    except RAGStoreError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise RAGStoreError(f"Failed to initialize rag_documents: {exc}") from exc
    finally:
        conn.close()


def document_content_hash(conn, document_id: str, collection: str | None = None) -> str | None:
    coll = collection or collection_name()
    if not _table_exists(conn):
        return None
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT content_hash
            FROM {TABLE}
            WHERE document_id = %s AND collection = %s
            LIMIT 1
            """,
            (document_id, coll),
        )
        row = cur.fetchone()
    return row[0] if row else None


def replace_document_chunks(
    chunks: list[dict[str, Any]],
    *,
    collection: str | None = None,
    url: str | None = None,
) -> int:
    if not chunks:
        return 0
    coll = collection or collection_name()
    dim = len(chunks[0]["embedding"])
    initialize(dim, url=url)

    conn = _connect(url)
    try:
        from pgvector import Vector

        document_id = chunks[0]["document_id"]
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {TABLE} WHERE document_id = %s AND collection = %s",
                (document_id, coll),
            )
            for chunk in chunks:
                embedding = chunk["embedding"]
                if len(embedding) != dim:
                    raise RAGStoreError("All chunk embeddings must share the same dimension.")
                cur.execute(
                    f"""
                    INSERT INTO {TABLE} (
                        id, document_id, collection, title, source, chunk_index,
                        content, content_hash, metadata, embedding
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    """,
                    (
                        str(uuid.uuid4()),
                        chunk["document_id"],
                        coll,
                        chunk.get("title") or "",
                        chunk.get("source") or "",
                        int(chunk["chunk_index"]),
                        chunk["content"],
                        chunk["content_hash"],
                        json.dumps(chunk.get("metadata") or {}),
                        Vector(embedding),
                    ),
                )
        conn.commit()
        return len(chunks)
    except RAGStoreError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise RAGStoreError(f"Failed to store RAG chunks: {exc}") from exc
    finally:
        conn.close()


def search(
    embedding: list[float],
    *,
    top_k: int = 5,
    collection: str | None = None,
    url: str | None = None,
) -> list[dict[str, Any]]:
    if not embedding:
        return []
    coll = collection or collection_name()
    conn = _connect(url)
    try:
        if not _table_exists(conn):
            return []
        existing = _existing_embedding_dim(conn)
        if existing is not None and existing != len(embedding):
            raise RAGStoreError(
                f"Query embedding has {len(embedding)} dimensions; "
                f"rag_documents.embedding is vector({existing})."
            )
        from pgvector import Vector

        vector = Vector(embedding)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT document_id, title, source, chunk_index, content, metadata,
                       1 - (embedding <=> %s) AS similarity
                FROM {TABLE}
                WHERE collection = %s
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                (vector, coll, vector, top_k),
            )
            rows = cur.fetchall()
        results = []
        for row in rows:
            metadata = row[5] or {}
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            results.append(
                {
                    "document_id": row[0],
                    "title": row[1] or "",
                    "source": row[2] or "",
                    "chunk_index": row[3],
                    "content": row[4],
                    "metadata": metadata,
                    "similarity": float(row[6]) if row[6] is not None else 0.0,
                }
            )
        return results
    except RAGStoreError:
        raise
    except Exception as exc:
        raise RAGStoreError(f"RAG similarity search failed: {exc}") from exc
    finally:
        conn.close()


def connect_for_read(url: str | None = None):
    """Open a connection for callers that need document_content_hash. Caller closes it."""
    return _connect(url)
