# RAG Service — Configuration Reference

> All configuration is via **environment variables** loaded by `pydantic-settings`.
> Copy `.env.example` to `.env` and edit as needed.

---

## Settings Class

```python
# rag_service/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAG_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
    # ... all fields below
```

All env vars are prefixed with `RAG_` (e.g., `RAG_OPENAI_API_KEY`).
Exception: `OPENAI_API_KEY` is also accepted without prefix for convenience.

---

## Core Settings

| Env Var | Default | Description |
|---------|---------|-------------|
| `RAG_ENV` | `development` | `development` \| `production` |
| `RAG_LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `RAG_LOG_FORMAT` | `json` | `json` \| `console` |
| `RAG_API_KEY` | `""` | Admin REST API key. Empty = no auth (local only) |
| `RAG_CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |

---

## Server Settings

| Env Var | Default | Description |
|---------|---------|-------------|
| `RAG_REST_HOST` | `0.0.0.0` | REST admin API bind host |
| `RAG_REST_PORT` | `8100` | REST admin API port |
| `RAG_MCP_HOST` | `0.0.0.0` | MCP SSE server bind host |
| `RAG_MCP_PORT` | `8101` | MCP SSE server port |
| `RAG_MCP_TRANSPORT` | `both` | `stdio` \| `sse` \| `both` |
| `RAG_WORKERS` | `1` | Uvicorn worker count |

---

## Database Settings

| Env Var | Default | Description |
|---------|---------|-------------|
| `RAG_DB_URL` | `sqlite+aiosqlite:///./rag.db` | SQLAlchemy async DB URL |
| `RAG_DB_ECHO` | `false` | Log all SQL statements (debug) |
| `RAG_DATA_DIR` | `./data` | Root data directory |
| `RAG_BM25_PERSIST_DIR` | `./data/bm25` | BM25 index pickle files |
| `RAG_GRAPH_PERSIST_DIR` | `./data/graphs` | Graph store JSON files |

**Postgres example**:
```env
RAG_DB_URL=postgresql+asyncpg://user:pass@localhost:5432/ragdb
```

---

## Embedding Settings

| Env Var | Default | Description |
|---------|---------|-------------|
| `RAG_EMBEDDER` | `openai` | `openai` \| `ollama` \| `sentence_transformers` |
| `RAG_OPENAI_API_KEY` | — | OpenAI API key (also accepts `OPENAI_API_KEY`) |
| `RAG_OPENAI_BASE_URL` | `https://api.openai.com/v1` | Override for OpenAI-compatible endpoints |
| `RAG_OPENAI_EMBED_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `RAG_OPENAI_EMBED_DIMENSIONS` | `1536` | Embedding dimensions |
| `RAG_OPENAI_EMBED_BATCH_SIZE` | `100` | Chunks per API call |
| `RAG_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `RAG_OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Ollama model name |
| `RAG_ST_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers model name |
| `RAG_EMBED_RETRY_ATTEMPTS` | `3` | Retry count on API errors |
| `RAG_EMBED_RETRY_DELAY` | `1.0` | Initial retry delay (seconds, exponential) |

---

## Vector Store Settings

| Env Var | Default | Description |
|---------|---------|-------------|
| `RAG_VECTOR_STORE` | `qdrant` | `qdrant` \| `chroma` |
| `RAG_QDRANT_URL` | `http://localhost:6333` | Qdrant server URL |
| `RAG_QDRANT_API_KEY` | `""` | Qdrant Cloud API key |
| `RAG_QDRANT_TIMEOUT` | `30` | Request timeout (seconds) |
| `RAG_QDRANT_ON_DISK` | `true` | Store vectors on disk (memory-mapped) |
| `RAG_CHROMA_PATH` | `./data/chroma` | ChromaDB persist directory |
| `RAG_CHROMA_HOST` | — | Chroma server host (if using server mode) |
| `RAG_CHROMA_PORT` | `8000` | Chroma server port |

---

## BM25 Settings

| Env Var | Default | Description |
|---------|---------|-------------|
| `RAG_BM25_BACKEND` | `memory` | `memory` \| `redis` |
| `RAG_BM25_K1` | `1.5` | BM25 k1 parameter |
| `RAG_BM25_B` | `0.75` | BM25 b parameter |
| `RAG_BM25_EPSILON` | `0.25` | BM25 epsilon (IDF floor) |
| `RAG_BM25_TOKENIZER` | `whitespace` | `whitespace` \| `pyvi` \| `jieba` |
| `RAG_REDIS_URL` | `redis://localhost:6379` | Redis URL (for redis BM25 backend) |

---

## Retrieval Settings

| Env Var | Default | Description |
|---------|---------|-------------|
| `RAG_RRF_K` | `60` | RRF smoothing constant |
| `RAG_RRF_BM25_WEIGHT` | `1.0` | BM25 list weight in RRF |
| `RAG_RRF_SEMANTIC_WEIGHT` | `1.0` | Semantic list weight in RRF |
| `RAG_DEFAULT_TOP_K` | `5` | Default number of results |
| `RAG_DEFAULT_CANDIDATE_K` | `50` | Candidates per retriever before RRF |
| `RAG_QUERY_CACHE_SIZE` | `1000` | LRU cache size for query embeddings |
| `RAG_QUERY_HYDE` | `false` | Enable HyDE query expansion |
| `RAG_QUERY_HYDE_MODEL` | `gpt-4o-mini` | LLM for HyDE hypothetical doc generation |

---

## Graph Settings (optional)

| Env Var | Default | Description |
|---------|---------|-------------|
| `RAG_ENABLE_GRAPH` | `false` | Enable LightRAG-style graph extraction |
| `RAG_GRAPH_BACKEND` | `networkx` | `networkx` \| `neo4j` |
| `RAG_GRAPH_LLM_MODEL` | `gpt-4o-mini` | LLM for entity/relation extraction |
| `RAG_GRAPH_MAX_ENTITIES` | `50` | Max entities extracted per chunk |
| `RAG_NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI |
| `RAG_NEO4J_USER` | `neo4j` | Neo4j username |
| `RAG_NEO4J_PASSWORD` | — | Neo4j password |

---

## Chunking Defaults

| Env Var | Default | Description |
|---------|---------|-------------|
| `RAG_DEFAULT_CHUNK_SIZE` | `800` | Default max chars per chunk |
| `RAG_DEFAULT_CHUNK_OVERLAP` | `150` | Default overlap between chunks |
| `RAG_DEFAULT_CHUNKER` | `recursive` | Default chunker strategy |

---

## Task Queue Settings

| Env Var | Default | Description |
|---------|---------|-------------|
| `RAG_INGEST_ASYNC` | `true` | Process file/URL ingest asynchronously |
| `RAG_INGEST_QUEUE` | `memory` | `memory` \| `arq` (requires Redis) |
| `RAG_INGEST_WORKERS` | `2` | Concurrent ingest workers |
| `RAG_ARQ_REDIS_URL` | `redis://localhost:6379` | Redis for arq task queue |

---

## `.env.example`

```env
# Core
RAG_ENV=development
RAG_LOG_LEVEL=INFO
RAG_API_KEY=

# Server
RAG_REST_PORT=8100
RAG_MCP_PORT=8101
RAG_MCP_TRANSPORT=both

# Database
RAG_DB_URL=sqlite+aiosqlite:///./rag.db
RAG_DATA_DIR=./data

# Embeddings (choose one)
RAG_EMBEDDER=openai
OPENAI_API_KEY=sk-...
# RAG_OPENAI_BASE_URL=http://localhost:11434/v1   # for Ollama OpenAI-compat
RAG_OPENAI_EMBED_MODEL=text-embedding-3-small

# Vector store
RAG_VECTOR_STORE=qdrant
RAG_QDRANT_URL=http://localhost:6333
# RAG_QDRANT_API_KEY=                             # for Qdrant Cloud

# BM25
RAG_BM25_BACKEND=memory
RAG_BM25_TOKENIZER=whitespace

# Retrieval
RAG_RRF_K=60
RAG_DEFAULT_TOP_K=5
RAG_DEFAULT_CANDIDATE_K=50

# Graph (optional — disabled by default)
RAG_ENABLE_GRAPH=false
# RAG_GRAPH_LLM_MODEL=gpt-4o-mini
```
