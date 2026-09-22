"""RAG configuration. Values are read at call time so tests can toggle env."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_COLLECTION = "delivery_knowledge"
DEFAULT_TOP_K = 5
DEFAULT_MAX_CHARS = 6000
DEFAULT_EMBEDDING_DIM = 1536

_TRUE = {"1", "true", "yes", "on"}


def rag_enabled() -> bool:
    return os.getenv("RAG_ENABLED", "false").strip().lower() in _TRUE


def database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def embedding_model() -> str:
    return os.getenv("GEMINI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip() or DEFAULT_EMBEDDING_MODEL


def embedding_dim() -> int:
    raw = os.getenv("RAG_EMBEDDING_DIM", str(DEFAULT_EMBEDDING_DIM)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_EMBEDDING_DIM
    return value if value >= 1 else DEFAULT_EMBEDDING_DIM


def collection_name() -> str:
    return os.getenv("RAG_COLLECTION", DEFAULT_COLLECTION).strip() or DEFAULT_COLLECTION


def top_k() -> int:
    raw = os.getenv("RAG_TOP_K", str(DEFAULT_TOP_K)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TOP_K
    return max(1, value)


def max_chars() -> int:
    raw = os.getenv("RAG_MAX_CHARS", str(DEFAULT_MAX_CHARS)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_CHARS
    return max(1, value)


def ingest_token() -> str:
    """Optional shared secret for POST /rag/ingest. Empty = unauthenticated demo endpoint."""
    return os.getenv("RAG_INGEST_TOKEN", "").strip()


def gemini_api_key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()
