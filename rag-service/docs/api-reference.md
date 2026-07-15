# RAG Service — REST Admin API Reference

> The REST API is the **admin interface** for document management and ingest.
> Agents should use the **MCP tools**, not this API directly.
> Base URL: `http://localhost:8100/api/v1`

---

## Authentication

If `RAG_API_KEY` is set in config, all requests must include:
```
X-API-Key: <your-api-key>
```
If `RAG_API_KEY` is empty (default), no authentication is required (loopback only).

---

## Health

### `GET /health`

Check service health.

**Response 200**:
```json
{
  "status": "ok",
  "version": "1.0.0",
  "components": {
    "vector_store": "ok",
    "bm25_index": "ok",
    "embedder": "ok",
    "database": "ok"
  }
}
```

---

## Collections

### `GET /collections`

List all collections.

**Response 200**:
```json
[
  {
    "id": "col_abc123",
    "name": "default",
    "document_count": 47,
    "chunk_count": 1203,
    "created_at": "2024-01-15T10:00:00Z",
    "updated_at": "2024-03-10T14:22:00Z",
    "embedding_model": "text-embedding-3-small",
    "embedding_dimensions": 1536
  }
]
```

### `POST /collections`

Create a new collection.

**Request body**:
```json
{
  "name": "project-alpha",
  "description": "Documents for Project Alpha",
  "embedding_model": "text-embedding-3-small"
}
```

**Response 201**:
```json
{
  "id": "col_xyz789",
  "name": "project-alpha",
  "document_count": 0,
  "chunk_count": 0,
  "created_at": "2024-03-15T09:00:00Z",
  "embedding_model": "text-embedding-3-small",
  "embedding_dimensions": 1536
}
```

### `GET /collections/{collection_id}`

Get collection details.

### `DELETE /collections/{collection_id}`

Delete a collection and all its documents, chunks, and vectors.

**Response 204**: No content.

---

## Documents

### `GET /documents`

List documents across all collections.

**Query parameters**:
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `collection_id` | string | — | Filter by collection |
| `status` | string | — | `pending`, `processing`, `success`, `error` |
| `source_type` | string | — | `pdf`, `docx`, `url`, `text`, `markdown` |
| `limit` | int | 20 | Max results |
| `offset` | int | 0 | Pagination offset |

**Response 200**:
```json
{
  "total": 47,
  "items": [
    {
      "id": "doc_abc123",
      "collection_id": "col_abc",
      "name": "auth-design.pdf",
      "source_type": "pdf",
      "source_url": null,
      "content_hash": "sha256:abc...",
      "status": "success",
      "chunk_count": 42,
      "token_count": 18420,
      "tags": ["architecture", "auth"],
      "metadata": {"title": "Auth Design", "author": "Alice", "page_count": 28},
      "created_at": "2024-03-10T09:00:00Z",
      "updated_at": "2024-03-10T09:05:00Z"
    }
  ]
}
```

### `GET /documents/{document_id}`

Get document details including all chunks.

**Response 200**:
```json
{
  "id": "doc_abc123",
  "collection_id": "col_abc",
  "name": "auth-design.pdf",
  "source_type": "pdf",
  "status": "success",
  "chunk_count": 42,
  "chunks": [
    {
      "id": "chunk_001",
      "chunk_index": 0,
      "text": "Authentication uses JWT tokens...",
      "start_char": 0,
      "end_char": 756,
      "token_count": 142
    }
  ],
  "metadata": {...},
  "tags": ["architecture"],
  "created_at": "2024-03-10T09:00:00Z"
}
```

### `DELETE /documents/{document_id}`

Delete a document and all its chunks from vector store, BM25 index, and metadata DB.

**Response 204**: No content.

### `POST /documents/{document_id}/retry`

Retry ingestion for a document with `status: "error"` or `status: "partial"`.

**Response 202**:
```json
{
  "document_id": "doc_abc123",
  "job_id": "job_xyz",
  "status": "queued"
}
```

---

## Ingest

### `POST /ingest/file`

Upload and ingest a file.

**Request**: `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | ✓ | The file to ingest (PDF, DOCX, MD, TXT, HTML) |
| `collection` | string | — | Collection name (default: `"default"`) |
| `tags` | string (JSON array) | — | e.g. `'["tag1","tag2"]'` |
| `chunk_size` | int | — | Default: 800 |
| `chunk_overlap` | int | — | Default: 150 |
| `chunker` | string | — | `"recursive"` \| `"sentence"` \| `"token"` |
| `enable_graph` | bool | — | Default: false |
| `force` | bool | — | Re-ingest even if content hash exists |

**Response 202** (async ingest):
```json
{
  "document_id": "doc_abc123",
  "job_id": "job_xyz789",
  "status": "processing",
  "collection": "default",
  "source_name": "auth-design.pdf",
  "source_type": "pdf"
}
```

**Response 200** (if already exists, no `force`):
```json
{
  "document_id": "doc_abc123",
  "status": "already_exists",
  "chunk_count": 42
}
```

### `POST /ingest/url`

Ingest a web URL.

**Request body**:
```json
{
  "url": "https://docs.example.com/intro",
  "collection": "default",
  "tags": ["docs", "intro"],
  "chunk_size": 800,
  "chunk_overlap": 150,
  "force": false
}
```

**Response 202**:
```json
{
  "document_id": "doc_xyz456",
  "job_id": "job_abc",
  "status": "processing",
  "source_url": "https://docs.example.com/intro",
  "source_type": "url"
}
```

### `POST /ingest/text`

Ingest raw text.

**Request body**:
```json
{
  "text": "Authentication uses JWT tokens...",
  "title": "Auth Notes",
  "collection": "default",
  "tags": ["notes"],
  "chunk_size": 800,
  "chunk_overlap": 150
}
```

**Response 201** (synchronous — text ingest is fast):
```json
{
  "document_id": "doc_def789",
  "status": "success",
  "chunk_count": 3,
  "collection": "default"
}
```

### `GET /ingest/jobs/{job_id}`

Poll the status of an async ingest job.

**Response 200**:
```json
{
  "job_id": "job_xyz789",
  "document_id": "doc_abc123",
  "status": "success",
  "progress": {
    "stage": "done",
    "chunks_processed": 42,
    "chunks_total": 42
  },
  "started_at": "2024-03-10T09:00:00Z",
  "completed_at": "2024-03-10T09:00:45Z",
  "errors": []
}
```

**Status values**:
| Status | Meaning |
|--------|---------|
| `queued` | Waiting in ingest queue |
| `processing` | Currently running (parse/chunk/embed) |
| `success` | All chunks indexed successfully |
| `partial` | Some chunks failed (see `errors[]`) |
| `error` | Complete failure |

---

## Retrieval (Admin/Debug)

### `POST /retrieve`

Direct retrieval endpoint for testing (not for agents — use MCP).

**Request body**:
```json
{
  "query": "how does authentication work",
  "collection": "default",
  "top_k": 5,
  "candidate_k": 50,
  "enable_graph": false,
  "filters": {
    "source_type": "pdf",
    "tags": ["architecture"]
  },
  "debug": true
}
```

**Response 200**:
```json
{
  "query": "how does authentication work",
  "results": [
    {
      "chunk_id": "chunk_abc",
      "document_id": "doc_abc123",
      "text": "Authentication uses JWT tokens...",
      "score": 0.0892,
      "rank": 1,
      "source_type": "pdf",
      "metadata": {"source_name": "auth-design.pdf", "chunk_index": 5}
    }
  ],
  "debug": {
    "bm25_candidates": 50,
    "semantic_candidates": 50,
    "rrf_k": 60,
    "embed_latency_ms": 87,
    "bm25_latency_ms": 3,
    "semantic_latency_ms": 14,
    "rrf_latency_ms": 0.4,
    "total_latency_ms": 105
  }
}
```

---

## Error Responses

All errors follow the same schema:

```json
{
  "error": {
    "code": "UNSUPPORTED_FORMAT",
    "message": "File type 'xlsx' is not supported",
    "detail": null
  }
}
```

| HTTP Status | Error Code | Meaning |
|-------------|------------|---------|
| 400 | `BAD_REQUEST` | Invalid request parameters |
| 400 | `UNSUPPORTED_FORMAT` | File type not supported |
| 404 | `NOT_FOUND` | Document/collection not found |
| 409 | `ALREADY_EXISTS` | Document with same hash already ingested |
| 422 | `PARSE_ERROR` | Could not parse document |
| 422 | `EMPTY_DOCUMENT` | Document yielded no text |
| 503 | `VECTOR_STORE_UNAVAILABLE` | Qdrant not reachable |
| 503 | `EMBEDDING_ERROR` | Embedding API failed after retries |
