"""Optional retrieval-augmented generation for discovery (Phase 1)."""

from app.rag.config import rag_enabled
from app.rag.retrieve import format_reference_section, retrieve_relevant_context

__all__ = [
    "rag_enabled",
    "retrieve_relevant_context",
    "format_reference_section",
]
