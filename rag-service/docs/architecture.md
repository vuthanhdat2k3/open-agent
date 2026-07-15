# RAG Service — Architecture

> This document describes the overall system design, module boundaries, data flows,
> and design decisions for the standalone `rag-service`.

---

## 1. Design Principles

1. **Independence** — `rag-service` has zero imports from `open-agent`. It is a
   separate Python package in its own repository. The only coupling is via the MCP
   protocol at runtime.

2. **Pipeline-oriented** — The ingest path is a linear pipeline of composable stages
   (parse → chunk → embed → store). Each stage is a class implementing a single
   interface, making stages independently testable and swappable.

3. **Retrieval-first design** — Retrieval quality is the product's core value. Two
   complementary signals (BM25 keyword + dense semantic) are always computed and
   fused via RRF. No single-path fallback unless explicitly configured.

4. **LightRAG-inspired graph layer** — Optional entity/relation graph stored
   alongside the vector index for multi-hop and cross-document reasoning, following
   the design described in the [LightRAG paper](https://arxiv.org/abs/2410.05779).

5. **Standard MCP interface** — The public surface that clients consume is a
   standard MCP server. The REST API is an *admin* interface for ingest management
   and is never called by agents.

6. **Async everywhere** — All I/O (embedding API, vector DB, BM25 index, graph DB)
   is `asyncio`-native.

7. **Pluggable backends** — Embedding providers, vector stores, and BM25 backends
   are resolved via a registry. Switching from Qdrant → Chroma or OpenAI → Ollama
   is a one-line config change.

---

## 2. Repository Layout

```
rag-service/
├── README.md
├── pyproject.toml              # package definition, dependencies
├── .env.example
├── alembic/                    # migrations for SQLite metadata DB
├── docs/                       # this documentation
│   ├── README.md
│   ├── architecture.md
│   ├── ingest-pipeline.md
│   ├── retrieval.md
│   ├── mcp-server.md
│   ├── api-reference.md
│   ├── database-schema.md
│   ├── configuration.md
│   ├── deployment.md
│   └── development.md
├── rag_service/
│   ├── __init__.py
│   ├── main.py                 # entry point: starts REST + MCP servers
│   ├── config.py               # Settings (pydantic-settings)
│   ├── dependencies.py         # FastAPI DI: get_db, get_embedder, get_vector_store
│   │
│   ├── db/                     # SQLite metadata DB (SQLAlchemy async)
│   │   ├── base.py             # Base, engine, metadata
│   │   └── session.py          # get_db async generator
│   │
│   ├── models/                 # SQLAlchemy ORM
│   │   ├── document.py         # Document (source file / URL)
│   │   ├── chunk.py            # Chunk (text segment with metadata)
│   │   └── collection.py       # Collection (namespace for documents)
│   │
│   ├── schemas/                # Pydantic v2 (request/response)
│   │   ├── document.py
│   │   ├── chunk.py
│   │   ├── collection.py
│   │   └── retrieval.py
│   │
│   ├── repositories/           # data-access layer
│   │   ├── base.py
│   │   ├── document_repo.py
│   │   ├── chunk_repo.py
│   │   └── collection_repo.py
│   │
│   ├── pipeline/               # ingest pipeline stages
│   │   ├── __init__.py
│   │   ├── base.py             # Stage ABC
│   │   ├── parser/
│   │   │   ├── base.py         # Parser ABC
│   │   │   ├── pdf.py          # PDFParser (pypdf2 / pdfminer)
│   │   │   ├── docx.py         # DOCXParser (python-docx)
│   │   │   ├── markdown.py     # MarkdownParser
│   │   │   ├── html.py         # HTMLParser (markdownify)
│   │   │   ├── text.py         # PlainTextParser
│   │   │   └── url.py          # URLParser (httpx + html.py)
│   │   ├── chunker/
│   │   │   ├── base.py         # Chunker ABC
│   │   │   ├── recursive.py    # RecursiveCharacterChunker
│   │   │   ├── sentence.py     # SentenceChunker (nltk / spacy)
│   │   │   └── token.py        # TokenChunker (tiktoken)
│   │   ├── embedder/
│   │   │   ├── base.py         # Embedder ABC
│   │   │   ├── openai.py       # OpenAIEmbedder
│   │   │   ├── ollama.py       # OllamaEmbedder
│   │   │   └── sentence_transformers.py
│   │   └── ingest.py           # IngestPipeline orchestrator
│   │
│   ├── retrieval/              # retrieval engine
│   │   ├── __init__.py
│   │   ├── bm25/
│   │   │   ├── base.py         # BM25Index ABC
│   │   │   ├── memory.py       # InMemoryBM25 (rank_bm25)
│   │   │   └── redis.py        # RedisBM25 (Redis + pickle)
│   │   ├── vector/
│   │   │   ├── base.py         # VectorStore ABC
│   │   │   ├── qdrant.py       # QdrantStore
│   │   │   └── chroma.py       # ChromaStore
│   │   ├── graph/              # optional LightRAG-style graph
│   │   │   ├── extractor.py    # EntityRelationExtractor (LLM-based)
│   │   │   ├── store.py        # GraphStore (NetworkX / Neo4j)
│   │   │   └── retriever.py    # GraphRetriever
│   │   ├── rrf.py              # Reciprocal Rank Fusion
│   │   └── engine.py           # HybridRetriever (BM25 + semantic + RRF)
│   │
│   ├── services/               # business logic
│   │   ├── ingest_service.py
│   │   ├── retrieval_service.py
│   │   ├── collection_service.py
│   │   └── document_service.py
│   │
│   ├── api/                    # REST admin API (FastAPI)
│   │   └── v1/
│   │       ├── router.py
│   │       └── routes/
│   │           ├── ingest.py
│   │           ├── collections.py
│   │           ├── documents.py
│   │           └── health.py
│   │
│   └── mcp_server/             # MCP server
│       ├── __init__.py
│       ├── server.py           # FastMCP / mcp server instance
│       ├── tools/
│       │   ├── search.py       # rag_search tool
│       │   ├── ingest.py       # rag_ingest_url, rag_ingest_text tools
│       │   └── collections.py  # rag_list_collections tool
│       └── transport/
│           ├── stdio.py        # stdio transport entry point
│           └── sse.py          # SSE transport (Starlette mount)
│
├── tests/
│   ├── unit/
│   │   ├── pipeline/
│   │   └── retrieval/
│   └── integration/
└── scripts/
    ├── run.py                  # dev runner
    └── seed.py                 # seed sample documents
```

---

## 3. Module Boundaries

```
┌──────────────────────────────────────────────────────┐
│                    External Clients                   │
│    open-agent (MCP)     /     admin tools (REST)      │
└──────────────┬───────────────────────────┬───────────┘
               │ MCP protocol              │ HTTP/JSON
               ▼                           ▼
┌──────────────────────┐     ┌─────────────────────────┐
│    mcp_server/        │     │       api/v1/            │
│  (tool definitions)   │     │   (ingest endpoints)     │
└──────────┬───────────┘     └────────────┬────────────┘
           │                              │
           ▼                              ▼
┌──────────────────────────────────────────────────────┐
│                    services/                          │
│   retrieval_service    ingest_service   doc_service  │
└──────────┬──────────────────────┬───────────────────┘
           │                      │
    ┌──────▼──────┐        ┌──────▼──────┐
    │  retrieval/  │        │  pipeline/   │
    │  engine.py   │        │  ingest.py   │
    └──────┬──────┘        └──────┬──────┘
           │                      │
    ┌──────▼──────┐        ┌──────▼──────┐
    │  BM25 Index  │        │   Parser    │
    │  VectorStore │        │   Chunker   │
    │  GraphStore  │        │   Embedder  │
    └─────────────┘        └─────────────┘
           │                      │
           └──────────────────────┘
                      │
             ┌────────▼────────┐
             │  repositories/  │
             │  (SQLite meta)  │
             └─────────────────┘
```

---

## 4. Data Flows

### 4.1 Ingest Flow

```
Client POST /api/v1/ingest/file  (or  /url  or  /text)
  │
  ▼
IngestService.ingest(source, collection_id, options)
  │
  ├─► Parser.parse(source) ──────────────► raw text + metadata
  │       (pdf / docx / html / md / url)
  │
  ├─► Chunker.chunk(text, options) ──────► List[Chunk]
  │       (recursive / sentence / token)
  │
  ├─► Embedder.embed(chunks) ────────────► List[float[]] vectors
  │       (OpenAI / Ollama / local)
  │
  ├─► VectorStore.upsert(chunks+vectors) ─► stored in Qdrant
  │
  ├─► BM25Index.add(chunks) ─────────────► updated inverted index
  │
  ├─► [optional] GraphExtractor.extract() ► entity/relation graph
  │       → GraphStore.upsert()
  │
  └─► DocumentRepo.save(document+chunks) ─► SQLite metadata DB
```

### 4.2 Retrieval Flow (Hybrid RRF)

```
MCP call:  rag_search(query, collection, top_k, filters)
  │
  ▼
RetrievalService.search(query, options)
  │
  ├─► Embedder.embed([query]) ──────────────────► query vector
  │
  ├─► BM25Index.search(query_tokens) ──────────► [(chunk_id, bm25_score)]
  │       scored by BM25Okapi formula
  │
  ├─► VectorStore.search(query_vector) ─────────► [(chunk_id, cos_sim)]
  │       HNSW approximate nearest neighbour
  │
  ├─► [optional] GraphRetriever.search(query) ──► [(chunk_id, graph_score)]
  │       entity expansion + relation paths
  │
  ├─► RRF.fuse([bm25_results, semantic_results, ...], k=60)
  │       score_i = Σ  1 / (k + rank_i)
  │
  └─► Top-N chunks with metadata ───────────────► MCP response (JSON)
```

---

## 5. Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | Python ≥ 3.11 | Async, rich ML ecosystem |
| Web framework | FastAPI + Uvicorn | Consistent with open-agent |
| MCP SDK | `mcp` Python SDK (server mode) | Standard protocol |
| ORM | SQLAlchemy 2.0 async + Alembic | Metadata & document tracking |
| Vector store | Qdrant (primary) | HNSW, filtering, payload indexing |
| BM25 | `rank_bm25` | Pure-Python, no external deps |
| Embeddings | `openai` SDK | Default; swappable |
| PDF parsing | `pypdf2` + `pdfminer.six` | Layered fallback |
| DOCX parsing | `python-docx` | |
| HTML parsing | `httpx` + `markdownify` | |
| Graph (opt.) | `networkx` → Neo4j | LightRAG pattern |
| Config | `pydantic-settings` | |
| Task queue (opt.) | `arq` (Redis) or `asyncio.Queue` | Background ingest |

---

## 6. Cross-Cutting Concerns

### Collections (namespacing)
Every document belongs to a **collection** (e.g., `"default"`, `"project-x-docs"`).
BM25 and vector indexes are partitioned by collection. MCP tools accept an optional
`collection` parameter; defaults to `"default"`.

### Metadata filtering
Qdrant payload filters allow retrieval to be scoped by:
- `collection_id`
- `document_id`
- `source_type` (pdf, url, text, …)
- `created_at` range
- arbitrary `tags` set at ingest time

### Error handling
- **Parser errors**: unknown file type → `UnsupportedFormatError`; corrupt file →
  `ParseError`. Both are surfaced in the ingest response `status.errors[]`.
- **Embedding API errors**: retried with exponential backoff (3 attempts).
- **Vector store errors**: connection issues raise `VectorStoreUnavailableError`.
- **MCP tool errors**: all exceptions are caught; the MCP response `isError=true`
  with a descriptive message is returned (never raises unhandled).

### Authentication
- REST API: optional `RAG_API_KEY` header check. Disabled by default (local use).
- MCP server: no authentication at the MCP level; rely on transport security (e.g.,
  keep stdio local; put SSE behind a reverse proxy with auth).

### Observability
- Structured JSON logging via `structlog`.
- Optional Prometheus metrics at `/metrics` (ingest throughput, retrieval latency,
  embedding API calls).
