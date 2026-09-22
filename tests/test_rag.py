import hashlib

import pytest

from app.agents import DISCOVERY_SCHEMA, discovery_agent
from app.providers import MockProvider
from app.rag.chunk import chunk_document
from app.rag.embeddings import EmbeddingError, GeminiEmbeddingProvider
from app.rag.ingest import ingest_document
from app.rag.retrieve import (
    REFERENCE_HEADER,
    RetrievedChunk,
    format_reference_section,
    retrieve_relevant_context,
)


def test_chunking_produces_chunks_and_preserves_metadata():
    text = "## One\n" + ("alpha " * 900) + "\n## Two\n" + ("beta " * 50)
    chunks = chunk_document(
        text,
        document_id="guide",
        title="Delivery Guide",
        source="internal",
    )
    assert len(chunks) >= 2
    assert chunks[0]["document_id"] == "guide"
    assert chunks[0]["title"] == "Delivery Guide"
    assert chunks[0]["source"] == "internal"
    assert [item["chunk_index"] for item in chunks] == list(range(len(chunks)))
    assert all(item["content"] for item in chunks)


def test_chunking_is_deterministic():
    text = "# Title\n" + ("word " * 1200)
    first = chunk_document(text, document_id="a", title="T", source="s")
    second = chunk_document(text, document_id="a", title="T", source="s")
    assert first == second


class FakeEmbed:
    def __init__(self, dim: int = 8):
        self.dim = dim
        self.calls = []
        self.model = "fake-embed"

    def embed_text(self, text: str, *, task_type: str = "RETRIEVAL_QUERY"):
        self.calls.append(("one", task_type, text[:20]))
        return self.embed_texts([text], task_type=task_type)[0]

    def embed_texts(self, texts: list[str], *, task_type: str = "RETRIEVAL_DOCUMENT"):
        self.calls.append(("batch", task_type, len(texts)))
        return [[float((i + 1) % 5) for _ in range(self.dim)] for i, _ in enumerate(texts)]


class FakeClient:
    def __init__(self, dim: int | None = None):
        self.dim = dim
        self.models = self
        self.last_config = None

    def embed_content(self, model, contents, config=None):
        self.last_config = config
        texts = contents if isinstance(contents, list) else [contents]
        size = self.dim
        if size is None:
            size = getattr(config, "output_dimensionality", None) or 1536

        class Item:
            def __init__(self, values):
                self.values = values

        class Result:
            def __init__(self, embeddings):
                self.embeddings = embeddings

        return Result([Item([0.1] * size) for _ in texts])


def test_gemini_embedding_requests_configured_output_dimensionality(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("RAG_EMBEDDING_DIM", raising=False)
    client = FakeClient()
    provider = GeminiEmbeddingProvider(client=client, model="gemini-embedding-001")
    vector = provider.embed_text("hello", task_type="RETRIEVAL_QUERY")
    assert client.last_config.output_dimensionality == 1536
    assert len(vector) == 1536
    assert all(isinstance(x, float) for x in vector)


def test_gemini_embedding_honors_rag_embedding_dim(monkeypatch):
    monkeypatch.setenv("RAG_EMBEDDING_DIM", "768")
    client = FakeClient()
    provider = GeminiEmbeddingProvider(client=client, model="gemini-embedding-001")
    vector = provider.embed_text("hello")
    assert client.last_config.output_dimensionality == 768
    assert len(vector) == 768


def test_gemini_embedding_rejects_dimension_mismatch(monkeypatch):
    monkeypatch.setenv("RAG_EMBEDDING_DIM", "1536")
    provider = GeminiEmbeddingProvider(client=FakeClient(dim=8), model="gemini-embedding-001")
    with pytest.raises(EmbeddingError, match="1536"):
        provider.embed_text("hello")


def test_gemini_embedding_empty_response_errors():
    class Empty:
        models = None

        def __init__(self):
            self.models = self

        def embed_content(self, **kwargs):
            class Result:
                embeddings = []

            return Result()

    provider = GeminiEmbeddingProvider(client=Empty(), model="gemini-embedding-001")
    with pytest.raises(EmbeddingError):
        provider.embed_text("x")


def test_retrieve_disabled_makes_no_store_calls(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "false")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")

    def boom(*args, **kwargs):
        raise AssertionError("search must not run when RAG is disabled")

    monkeypatch.setattr("app.rag.store.search", boom)
    assert retrieve_relevant_context("portal estimate") == []


def test_retrieve_empty_knowledge_base(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.rag.store.search", lambda *args, **kwargs: [])
    chunks = retrieve_relevant_context("timeline", embedding_provider=FakeEmbed())
    assert chunks == []


def test_retrieve_success_topk_and_max_chars(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    rows = [
        {
            "document_id": "g",
            "title": "Delivery Guide",
            "source": "internal",
            "chunk_index": i,
            "content": "x" * 100,
            "metadata": {"k": "v"},
            "similarity": 0.9 - i * 0.01,
        }
        for i in range(8)
    ]
    monkeypatch.setattr("app.rag.store.search", lambda *args, **kwargs: rows[: kwargs.get("top_k", 5)])
    chunks = retrieve_relevant_context(
        "risks",
        top_k=3,
        max_characters=250,
        embedding_provider=FakeEmbed(),
    )
    assert len(chunks) == 2
    assert chunks[0].title == "Delivery Guide"
    assert chunks[0].metadata["k"] == "v"
    assert chunks[0].source == "internal"
    assert sum(len(c.content) for c in chunks) <= 250
    assert len(chunks) < 8


def test_format_reference_section_labels_not_customer_facts():
    text = format_reference_section(
        [
            RetrievedChunk(
                document_id="g",
                title="Delivery Guide",
                source="internal",
                chunk_index=0,
                content="Ask named users.",
                similarity=0.8,
            )
        ]
    )
    assert "REFERENCE EXCERPTS" in text
    assert "NOT customer-provided" in text
    assert "Ask named users." in text
    assert text.startswith(REFERENCE_HEADER.strip()[:20])


def test_ingest_skips_when_hash_unchanged(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    content = "Enough words to chunk."
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()

    class Conn:
        def close(self):
            return None

    monkeypatch.setattr("app.rag.ingest.connect_for_read", lambda: Conn())
    monkeypatch.setattr("app.rag.ingest.document_content_hash", lambda conn, doc: digest)
    called = []

    def replace(chunks):
        called.append(chunks)
        return len(chunks)

    monkeypatch.setattr("app.rag.ingest.replace_document_chunks", replace)
    result = ingest_document("guide", "T", "internal", content, embedding_provider=FakeEmbed())
    assert result["skipped"] is True
    assert called == []


def test_ingest_replaces_when_content_changes(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")

    class Conn:
        def close(self):
            return None

    monkeypatch.setattr("app.rag.ingest.connect_for_read", lambda: Conn())
    monkeypatch.setattr("app.rag.ingest.document_content_hash", lambda conn, doc: "old")
    stored = {}

    def replace(chunks):
        stored["n"] = len(chunks)
        stored["dim"] = len(chunks[0]["embedding"])
        return len(chunks)

    monkeypatch.setattr("app.rag.ingest.replace_document_chunks", replace)
    result = ingest_document(
        "guide",
        "T",
        "internal",
        "New content for the knowledge base.",
        embedding_provider=FakeEmbed(dim=8),
    )
    assert result["skipped"] is False
    assert result["chunks"] >= 1
    assert result["embedding_dimension"] == 8
    assert stored["n"] == result["chunks"]


def test_ingest_disabled(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "false")
    from app.rag.ingest import RAGIngestError

    with pytest.raises(RAGIngestError):
        ingest_document("x", "t", "s", "c")


class RecordingProvider(MockProvider):
    def __init__(self):
        self.prompts = []

    def generate_json(self, prompt: str, schema: dict) -> dict:
        self.prompts.append(prompt)
        assert schema is DISCOVERY_SCHEMA
        return super().generate_json(prompt, schema)


def test_discovery_unchanged_when_rag_disabled(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "false")
    provider = RecordingProvider()
    state = {"user_request": "We need a portal for enterprise customers."}
    discovery_agent(state, provider)
    prompt = provider.prompts[0]
    assert "REFERENCE EXCERPTS" not in prompt
    assert "internal delivery knowledge base" not in prompt
    assert "We need a portal for enterprise customers." in prompt


def test_discovery_appends_excerpts_when_rag_enabled(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "true")
    excerpt = format_reference_section(
        [
            RetrievedChunk(
                document_id="est",
                title="Estimation Guidelines",
                source="internal",
                chunk_index=0,
                content="Estimates are ranges, not commitments.",
                similarity=0.7,
            )
        ]
    )
    monkeypatch.setattr(
        "app.rag.retrieve.retrieve_relevant_context",
        lambda query: [
            RetrievedChunk(
                document_id="est",
                title="Estimation Guidelines",
                source="internal",
                chunk_index=0,
                content="Estimates are ranges, not commitments.",
                similarity=0.7,
            )
        ],
    )
    provider = RecordingProvider()
    discovery_agent({"user_request": "Estimate a warehouse."}, provider)
    prompt = provider.prompts[0]
    assert "REFERENCE EXCERPTS" in prompt
    assert "Estimates are ranges, not commitments." in prompt
    assert "NOT customer-provided" in prompt
    assert excerpt.split("\n")[0] in prompt


def test_rag_ingest_endpoint_disabled():
    from fastapi.testclient import TestClient
    from app.api import get_provider
    from app.main import app
    from app.providers import MockProvider

    app.dependency_overrides[get_provider] = MockProvider
    client = TestClient(app)
    response = client.post(
        "/rag/ingest",
        json={
            "document_id": "guide",
            "title": "Guide",
            "source": "internal",
            "content": "hello",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"] == "RAG_DISABLED"
