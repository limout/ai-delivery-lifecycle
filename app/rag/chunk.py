"""Deterministic document chunking for RAG ingest."""

from __future__ import annotations

import re

TARGET_WORDS = 800
MAX_WORDS = 1000
OVERLAP_WORDS = 80
HEADING_RE = re.compile(r"(?=^#{1,3} )", re.MULTILINE)


def _words(text: str) -> list[str]:
    return text.split()


def _join(words: list[str]) -> str:
    return " ".join(words).strip()


def _window(words: list[str], target: int = TARGET_WORDS, overlap: int = OVERLAP_WORDS) -> list[str]:
    if not words:
        return []
    if len(words) <= MAX_WORDS:
        return [_join(words)]
    chunks: list[str] = []
    start = 0
    step = max(1, target - overlap)
    while start < len(words):
        end = min(len(words), start + target)
        chunks.append(_join(words[start:end]))
        if end >= len(words):
            break
        start += step
    return chunks


def _sections(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    parts = [part.strip() for part in HEADING_RE.split(stripped) if part.strip()]
    return parts or [stripped]


def chunk_document(
    content: str,
    *,
    document_id: str,
    title: str = "",
    source: str = "",
    target_words: int = TARGET_WORDS,
    overlap_words: int = OVERLAP_WORDS,
) -> list[dict]:
    """Split document text into overlapping word windows, preferring Markdown headings."""
    chunks: list[dict] = []
    index = 0
    for section in _sections(content or ""):
        for body in _window(_words(section), target=target_words, overlap=overlap_words):
            if not body:
                continue
            chunks.append(
                {
                    "document_id": document_id,
                    "title": title,
                    "source": source,
                    "chunk_index": index,
                    "content": body,
                }
            )
            index += 1
    return chunks
