# RAG Service — Database Schema

> Describes the **SQLite metadata database** (SQLAlchemy ORM), the **Qdrant vector
> store** payload schema, and the **BM25 index** persistence format.

---

## 1. SQLite Metadata Database

The metadata database tracks documents, chunks, collections, and ingest jobs.
It uses **SQLAlchemy 2.0 async** with **Alembic** for migrations.

Database file: configurable via `RAG_DB_URL` (default: `sqlite+aiosqlite:///./rag.db`)

---

### Table: `collections`

Represents a named namespace for documents.

```sql
CREATE TABLE collections (
    id          TEXT PRIMARY KEY,          -- UUID, e.g. "col_abc123"
    name        TEXT NOT NULL UNIQUE,      -- human-readable name, e.g. "default"
    description TEXT,
    embedding_model      TEXT NOT NULL DEFAULT 'text-embedding-3-small',
    embedding_dimensions INTEGER NOT NULL DEFAULT 1536,
    created_at  DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at  DATETIME NOT NULL DEFAULT (datetime('now'))
);
```

**ORM Model**:
```python
class Collection(Base):
    __tablename__ = "collections"
    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: f"col_{uuid4().hex[:8]}")
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    embedding_model: Mapped[str] = mapped_column(Text, default="text-embedding-3-small")
    embedding_dimensions: Mapped[int] = mapped_column(Integer, default=1536)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow,
                                                  onupdate=datetime.utcnow)
    documents: Mapped[list["Document"]] = relationship(back_populates="collection",
                                                        cascade="all, delete-orphan")
```

---

### Table: `documents`

Represents a source document (file, URL, or raw text).

```sql
CREATE TABLE documents (
    id            TEXT PRIMARY KEY,       -- UUID e.g. "doc_abc123"
    collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,          -- display name (filename or URL or title)
    source_type   TEXT NOT NULL,          -- 'pdf'|'docx'|'url'|'text'|'markdown'|'html'
    source_url    TEXT,                   -- original URL if source_type='url'
    content_hash  TEXT NOT NULL,          -- SHA-256 of raw bytes/text (for dedup)
    status        TEXT NOT NULL DEFAULT 'pending',
    -- 'pending'|'processing'|'success'|'partial'|'error'
    chunk_count   INTEGER NOT NULL DEFAULT 0,
    token_count   INTEGER NOT NULL DEFAULT 0,
    tags          TEXT NOT NULL DEFAULT '[]',   -- JSON array of strings
    doc_metadata  TEXT NOT NULL DEFAULT '{}',   -- JSON: title, author, page_count, etc.
    ingest_errors TEXT NOT NULL DEFAULT '[]',   -- JSON array of error objects
    created_at    DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at    DATETIME NOT NULL DEFAULT (datetime('now')),

    UNIQUE(collection_id, content_hash)
);

CREATE INDEX idx_documents_collection ON documents(collection_id);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_source_type ON documents(source_type);
```

**Status transitions**:
```
pending → processing → success
                    ↘ partial  (some chunks failed)
                    ↘ error    (complete failure)
partial/error → processing  (via retry)
```

---

### Table: `chunks`

Represents a text segment of a document.

```sql
CREATE TABLE chunks (
    id            TEXT PRIMARY KEY,       -- UUID e.g. "chunk_abc"
    document_id   TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    collection_id TEXT NOT NULL,          -- denormalized for fast filtering
    chunk_index   INTEGER NOT NULL,       -- 0-based sequence within document
    text          TEXT NOT NULL,          -- full chunk text
    start_char    INTEGER NOT NULL,       -- character offset in original text
    end_char      INTEGER NOT NULL,
    token_count   INTEGER NOT NULL DEFAULT 0,
    chunk_metadata TEXT NOT NULL DEFAULT '{}',  -- JSON: any chunk-specific metadata
    created_at    DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_chunks_document ON chunks(document_id);
CREATE INDEX idx_chunks_collection ON chunks(collection_id);
```

**Note**: The full chunk text is stored here (SQLite) AND in the Qdrant payload.
The SQLite copy serves as the authoritative source for metadata queries and
document reconstruction; Qdrant serves fast vector search + text retrieval.

---

### Table: `ingest_jobs`

Tracks async ingest job progress.

```sql
CREATE TABLE ingest_jobs (
    id            TEXT PRIMARY KEY,       -- UUID e.g. "job_xyz789"
    document_id   TEXT REFERENCES documents(id) ON DELETE SET NULL,
    collection_id TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'queued',
    -- 'queued'|'processing'|'success'|'partial'|'error'
    stage         TEXT,                   -- 'parsing'|'chunking'|'embedding'|'storing'|'done'
    chunks_total  INTEGER NOT NULL DEFAULT 0,
    chunks_done   INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at    DATETIME,
    completed_at  DATETIME,
    created_at    DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_jobs_status ON ingest_jobs(status);
CREATE INDEX idx_jobs_document ON ingest_jobs(document_id);
```

---

## 2. Qdrant Vector Store Schema

Each **RAG collection** maps to one **Qdrant collection** (same name).

### Collection Config

```python
VectorParams(
    size=1536,                # or 3072 for text-embedding-3-large
    distance=Distance.COSINE,
    on_disk=True,             # memory-mapped, suitable for large corpora
    hnsw_config=HnswConfigDiff(
        m=16,                 # HNSW graph connections per node
        ef_construct=100,     # construction search breadth
    )
)
```

### Point Payload Schema

Each point in Qdrant corresponds to one chunk:

```json
{
  "chunk_id":      "chunk_abc123",       // matches chunks.id in SQLite
  "document_id":   "doc_abc",
  "collection_id": "col_default",
  "text":          "Authentication uses JWT tokens...",
  "chunk_index":   5,
  "source_type":   "pdf",
  "source_name":   "auth-design.pdf",
  "source_url":    null,
  "tags":          ["architecture", "auth"],
  "token_count":   142,
  "created_at":    "2024-03-10T09:00:00Z",

  // Document-level metadata (flattened for filtering):
  "doc_title":     "Auth Design Document",
  "doc_author":    "Alice",
  "doc_page_count": 28,

  // Any custom_metadata from ingest options:
  "project":       "backend-v2"
}
```

### Payload Indexes (for filtered search)

```python
# Created automatically on collection initialization:
await client.create_payload_index(name, "document_id",   "keyword")
await client.create_payload_index(name, "source_type",   "keyword")
await client.create_payload_index(name, "tags",          "keyword")
await client.create_payload_index(name, "created_at",    "datetime")
await client.create_payload_index(name, "collection_id", "keyword")
```

### Filter Examples (Qdrant Filter API)

```python
# Filter by source type:
Filter(must=[FieldCondition(key="source_type", match=MatchValue(value="pdf"))])

# Filter by tags (any of):
Filter(should=[
    FieldCondition(key="tags", match=MatchValue(value="architecture")),
    FieldCondition(key="tags", match=MatchValue(value="auth")),
])

# Filter by date range:
Filter(must=[FieldCondition(
    key="created_at",
    range=DatetimeRange(gte="2024-01-01T00:00:00Z")
)])
```

---

## 3. BM25 Index Persistence Format

BM25 indexes are persisted as **pickle files** (one per collection) in the
directory specified by `RAG_BM25_PERSIST_DIR` (default: `./data/bm25/`).

### File naming
```
data/bm25/
  default.pkl
  project-alpha.pkl
  research-papers.pkl
```

### Pickle format

```python
{
    "chunk_ids": ["chunk_001", "chunk_002", ...],  # parallel to corpus
    "corpus": [
        ["authentication", "uses", "jwt", "tokens"],  # tokenized chunk 0
        ["the", "oauth", "flow", "begins"],            # tokenized chunk 1
        ...
    ],
    # Note: BM25Okapi model is NOT pickled — it's rebuilt from corpus on load
    # This avoids pickle compatibility issues across rank_bm25 versions
}
```

**On startup**, each collection's BM25 index is loaded from disk:
```python
async def startup_event():
    collections = await collection_repo.list_all()
    for col in collections:
        await bm25_index.load(col.name)
```

---

## 4. Graph Store Schema (optional)

When `RAG_ENABLE_GRAPH=true`, entity-relation data is stored in:

### NetworkX format (default)
Persisted as JSON (node-link format) at `data/graphs/{collection_id}.json`.

```json
{
  "nodes": [
    {
      "id": "entity_jwt",
      "name": "JWT",
      "type": "TECHNOLOGY",
      "description": "JSON Web Token standard for authentication",
      "chunk_ids": ["chunk_001", "chunk_005"]
    }
  ],
  "edges": [
    {
      "source": "entity_jwt",
      "target": "entity_oauth",
      "relation": "USED_BY",
      "weight": 0.9,
      "chunk_ids": ["chunk_001"]
    }
  ]
}
```

### Neo4j format (production)
Uses Cypher queries. Node labels: `:Entity`. Relationship types: dynamic from extraction.

```cypher
// Node example:
(:Entity {id: "entity_jwt", name: "JWT", type: "TECHNOLOGY",
          collection_id: "default", chunk_ids: ["chunk_001"]})

// Relation example:
(:Entity {name: "JWT"})-[:USED_BY {weight: 0.9}]->(:Entity {name: "OAuth"})
```

---

## 5. Alembic Migration Strategy

```
alembic/
  env.py
  versions/
    0001_initial_schema.py     -- creates collections, documents, chunks, ingest_jobs
    0002_add_token_count.py    -- adds token_count to documents
    ...
```

**Running migrations**:
```bash
# Apply all pending migrations
alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "add_graph_table"

# Rollback one step
alembic downgrade -1
```

Migrations run automatically on service startup (same pattern as open-agent's
`scripts/run.py`).
