# RAG Service

Standalone Retrieval-Augmented Generation microservice. It exposes **hybrid
BM25 + semantic retrieval** with Reciprocal Rank Fusion (RRF) through two
interfaces:

- a **standard MCP server** (stdio / SSE) — the primary interface used by agents
- a **REST admin API** (FastAPI, `/api/v1`) for operations/debugging

The service is **independent of `open-agent`** and couples only at runtime via
the MCP protocol. It is designed to **boot and serve real traffic with zero
external services**: when Qdrant / OpenAI / Chroma / Redis are not configured it
transparently falls back to in-process implementations (in-memory numpy vector
store, a local hashing embedder, in-memory `rank_bm25`).

## Quick start

```bash
pip install -e .
cp .env.example .env          # optional; sensible defaults are built in
python scripts/run.py         # REST on :8100, MCP-SSE on :8101
```

Or run the MCP server on stdio (the mode most MCP clients launch on demand):

```bash
python -m rag_service.mcp_server.transport.stdio
# or, after install:
rag-service-mcp
```

## What it does

- **Ingest** text, files (PDF/DOCX/MD/HTML/TXT) or URLs into a *collection*.
- **Parse → chunk → embed → index** with pluggable backends.
- **Hybrid retrieve** blending lexical (BM25) and dense (embeddings) signals via RRF.
- Optional **LightRAG-style graph** layer (entity/relation extraction + graph
  traversal) for relational recall.

## Configuration

All settings are environment variables prefixed `RAG_` (see `.env.example` and
`rag_service/config.py`). Key switches:

| Variable | Default | Purpose |
|----------|---------|---------|
| `RAG_EMBEDDER` | `openai` | `openai` / `ollama` / `sentence_transformers` / `simple` (offline hash) |
| `RAG_VECTOR_STORE` | `qdrant` | `qdrant` / `chroma` / `memory` |
| `RAG_BM25_BACKEND` | `memory` | `memory` / `redis` |
| `RAG_MCP_TRANSPORT` | `both` | `stdio` / `sse` / `both` |
| `RAG_ENABLE_GRAPH` | `false` | enable the optional graph layer |

## Architecture

See `docs/` for the full design (architecture, api-reference, configuration,
ingest-pipeline, retrieval, mcp-server, database-schema, deployment,
development).

## Tests

```bash
pytest
```
