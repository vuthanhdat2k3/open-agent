# RAG Service

> **Standalone Retrieval-Augmented Generation service** with hybrid BM25 + semantic
> search, Reciprocal Rank Fusion (RRF), and a standard **MCP server** interface.
> Inspired by [LightRAG](https://github.com/HKUDS/LightRAG).

---

## Overview

`rag-service` is a fully independent microservice. It does **not** import or depend
on `open-agent`. It exposes one interface: an **MCP server** (stdio or SSE transport)
that any MCP-capable client (including open-agent) can connect to.

```
┌─────────────────────────────────────────────────────────────┐
│                        rag-service                          │
│                                                             │
│  HTTP REST   ──►  Ingest Pipeline  ──►  Vector Store        │
│  (Admin API)      (parse→chunk→embed)   (Qdrant / Chroma)   │
│                                                             │
│  MCP Server  ──►  Retrieval Engine ──►  Hybrid BM25+Semantic│
│  (stdio/SSE)      (RRF re-ranking)      + Graph (optional)  │
└─────────────────────────────────────────────────────────────┘
         ▲                                           ▲
         │                                           │
   open-agent                               Direct API calls
   (MCP client)                             (admin tools)
```

---

## Key Features

| Feature | Details |
|---------|---------|
| **Ingest** | PDF, DOCX, Markdown, HTML, plain text, web URL |
| **Parse** | Unstructured / pypdf2 / markdownify |
| **Chunk** | Recursive character splitter, sentence-aware, token-aware |
| **Embed** | OpenAI `text-embedding-*` or local (Ollama / sentence-transformers) |
| **Store** | Qdrant (primary) — swappable to Chroma / pgvector |
| **BM25** | BM25Okapi on in-memory or Redis-backed inverted index |
| **Semantic** | Cosine similarity over embedding vectors |
| **Hybrid** | Reciprocal Rank Fusion (RRF, k=60) over BM25 + semantic lists |
| **Graph (opt.)** | Entity–relation graph (LightRAG-style) for cross-doc reasoning |
| **MCP** | Standard MCP server — stdio or SSE transport |

---

## Documentation Index

| Document | Description |
|----------|-------------|
| [architecture.md](./architecture.md) | System design, layers, data flows |
| [ingest-pipeline.md](./ingest-pipeline.md) | Parse → Chunk → Embed → Store |
| [retrieval.md](./retrieval.md) | BM25, semantic search, RRF, graph RAG |
| [mcp-server.md](./mcp-server.md) | MCP tool definitions, transport, config |
| [api-reference.md](./api-reference.md) | REST Admin API (ingest endpoints) |
| [database-schema.md](./database-schema.md) | All collections and metadata schemas |
| [configuration.md](./configuration.md) | All env vars and config options |
| [deployment.md](./deployment.md) | Docker, docker-compose, production notes |
| [development.md](./development.md) | Local dev setup, testing, contributing |

---

## Quick Start

```bash
# 1. Clone and setup
git clone <repo> rag-service
cd rag-service
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
# Edit .env: set OPENAI_API_KEY, QDRANT_URL, etc.

# 3. Start dependencies (Qdrant)
docker run -p 6333:6333 qdrant/qdrant

# 4. Run the service
python -m rag_service.main
# -> REST admin API on :8100
# -> MCP SSE server on :8101
```

### Connect from open-agent

In open-agent's MCP server settings, add:

```json
{
  "name": "rag-service",
  "transport": "sse",
  "url": "http://localhost:8101/sse"
}
```

Or use **stdio** transport (recommended for local use):

```json
{
  "name": "rag-service",
  "transport": "stdio",
  "command": "python",
  "args": ["-m", "rag_service.mcp_server"]
}
```

---

## License

MIT
