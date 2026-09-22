# Phase 1 RAG

Retrieval-augmented generation for the Discovery agent only.

```
Documents (docs/rag/*.md)
    → chunking (app/rag/chunk.py)
    → Gemini embeddings API (embed_content, not generate_content)
    → Neon PostgreSQL + pgvector
    → cosine similarity search (top-k, max chars)
    → reference excerpts appended to the Discovery prompt
    → existing Gemini JSON generate_json call
    → unchanged DISCOVERY_SCHEMA
```

LangGraph is unchanged. RAG is not a graph node.

## Vocabulary

- **RAG** — retrieve relevant external text before the LLM generates.
- **Embeddings** — numeric vectors used for semantic similarity (not keyword match).
- **pgvector** — PostgreSQL extension that stores and searches those vectors.
- **LangGraph** — workflow/orchestration of Analyze → … → SOW. Not the retriever.
- **LLM** — reasoning/generation via `AIProvider.generate_json`.

Corpus embeddings are created **only at ingest**. `/analyze` embeds the query string once when `RAG_ENABLED=true`. Documents are never re-embedded on analyze.

Retrieved text is **reference only**. It is not customer evidence (`app/evidence.py` is unchanged).

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `RAG_ENABLED` | `false` | Master switch. Off: no DB, no embeddings, no retrieval. |
| `DATABASE_URL` | empty | Neon/Postgres connection string. |
| `GEMINI_API_KEY` | existing | Same key as the LLM provider. |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | Embedding model (not the chat model). |
| `RAG_EMBEDDING_DIM` | `1536` | Passed to Gemini as `output_dimensionality` (HNSW max is 2000). |
| `RAG_COLLECTION` | `delivery_knowledge` | Logical corpus name. |
| `RAG_TOP_K` | `5` | Max chunks returned. |
| `RAG_MAX_CHARS` | `6000` | Cap on concatenated excerpt characters. |
| `RAG_INGEST_TOKEN` | empty | If set, `POST /rag/ingest` requires header `X-RAG-Ingest-Token`. |

The table `rag_documents` is created on first ingest. Column type is `vector(N)` where `N` is the length of the embedding Gemini actually returned (requested via `RAG_EMBEDDING_DIM`, default 1536).

## Ingest (admin/demo)

`POST /rag/ingest` is an **unauthenticated demo endpoint** unless `RAG_INGEST_TOKEN` is set.

Auth for ingestion is a **Phase 2** requirement.

```
curl -s http://localhost:8000/rag/ingest ^
  -H "Content-Type: application/json" ^
  -d "{\"document_id\":\"delivery-guide\",\"title\":\"Delivery Guide\",\"source\":\"internal\",\"content\":\"...\"}"
```

Requires `RAG_ENABLED=true` and `DATABASE_URL`.

## Operate with RAG off

Leave `RAG_ENABLED` unset or `false`. The app starts without Postgres. Existing `/analyze` behavior is unchanged.
