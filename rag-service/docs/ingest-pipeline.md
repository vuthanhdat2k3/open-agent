# RAG Service — Ingest Pipeline

> Detailed design of the **Parse → Chunk → Embed → Store** pipeline.

---

## 1. Overview

The ingest pipeline transforms raw sources (files, URLs, text strings) into
searchable chunks stored in both the vector store and the BM25 index.

```
Source (file / url / text)
        │
        ▼
   ┌─────────┐
   │  Parser  │  ──► raw text + document metadata
   └────┬────┘
        │
        ▼
   ┌─────────┐
   │ Chunker  │  ──► List[TextChunk]  (text, start, end, metadata)
   └────┬────┘
        │
        ▼
   ┌─────────┐
   │ Embedder │  ──► List[float[]]  (one vector per chunk)
   └────┬────┘
        │
   ┌────┴──────────────────────────┐
   │                               │
   ▼                               ▼
Vector Store                   BM25 Index
(Qdrant)                       (rank_bm25)
   │                               │
   └──────────────┬────────────────┘
                  │
                  ▼
            SQLite metadata
         (Document + Chunk rows)
```

---

## 2. Parser

### 2.1 Parser ABC

```python
# rag_service/pipeline/parser/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ParseResult:
    text: str                        # full extracted text
    metadata: dict[str, Any] = field(default_factory=dict)
    # e.g. {"title": "...", "author": "...", "pages": 10}

class Parser(ABC):
    @abstractmethod
    async def parse(self, source: bytes | str, **kwargs) -> ParseResult:
        """Parse source into plain text + metadata."""
```

### 2.2 Parser Registry

```python
# rag_service/pipeline/parser/__init__.py
PARSER_REGISTRY: dict[str, type[Parser]] = {
    "pdf":      PDFParser,
    "docx":     DOCXParser,
    "md":       MarkdownParser,
    "markdown": MarkdownParser,
    "html":     HTMLParser,
    "htm":      HTMLParser,
    "txt":      PlainTextParser,
    "text":     PlainTextParser,
    "url":      URLParser,
}

def get_parser(source_type: str) -> Parser:
    cls = PARSER_REGISTRY.get(source_type.lower())
    if cls is None:
        raise UnsupportedFormatError(source_type)
    return cls()
```

### 2.3 PDFParser

**Library**: `pypdf2` (primary) with `pdfminer.six` fallback for scanned/complex PDFs.

```python
class PDFParser(Parser):
    async def parse(self, source: bytes, **kwargs) -> ParseResult:
        # 1. Try pypdf2 (fast, pure-python)
        # 2. If text extraction yields < 50 chars/page → fallback pdfminer
        # 3. Extract: title, author, creation_date from PDF metadata
        # 4. Return concatenated page texts with page number markers:
        #    "<!-- page 1 -->\n...\n<!-- page 2 -->\n..."
```

**Metadata extracted**: `title`, `author`, `creator`, `page_count`, `created_at`

### 2.4 DOCXParser

**Library**: `python-docx`

```python
class DOCXParser(Parser):
    async def parse(self, source: bytes, **kwargs) -> ParseResult:
        # Extract: paragraphs, tables (as markdown tables), headers
        # Preserve heading levels as markdown # / ## / ###
        # Tables → pipe-separated markdown
```

**Metadata extracted**: `title`, `author`, `created`, `modified`, `word_count`

### 2.5 MarkdownParser

Strips frontmatter (YAML between `---`), extracts it as metadata, returns body.

### 2.6 HTMLParser

```python
class HTMLParser(Parser):
    async def parse(self, source: bytes | str, **kwargs) -> ParseResult:
        # 1. BeautifulSoup: remove script/style/nav/footer
        # 2. markdownify: HTML → Markdown (preserves structure)
        # 3. Extract: <title>, <meta name="description">, <meta name="author">
```

### 2.7 URLParser

```python
class URLParser(Parser):
    async def parse(self, source: str, **kwargs) -> ParseResult:
        # 1. httpx.AsyncClient GET with browser-like headers
        # 2. Follow redirects (max 5)
        # 3. Detect content-type → delegate to HTMLParser / PDFParser / PlainTextParser
        # 4. Store URL as metadata["source_url"]
```

**Rate limiting**: respects `Crawl-Delay` from robots.txt (optional, configurable).

### 2.8 PlainTextParser

Trivial — returns source as-is. Detects encoding (`chardet`).

---

## 3. Chunker

### 3.1 Chunker ABC

```python
@dataclass
class TextChunk:
    chunk_id: str          # UUID
    text: str
    start_char: int        # offset in original document text
    end_char: int
    chunk_index: int       # sequential index within document
    metadata: dict         # inherited from document + chunk-specific

class Chunker(ABC):
    @abstractmethod
    def chunk(self, text: str, doc_metadata: dict, **kwargs) -> list[TextChunk]:
        ...
```

### 3.2 RecursiveCharacterChunker (default)

Splits on a priority-ordered list of separators until chunks fit within size limits.
Implements the same algorithm as LangChain's `RecursiveCharacterTextSplitter`.

```
Separators (tried in order):
  1. "\n\n"      (paragraph break)
  2. "\n"        (line break)
  3. ". "        (sentence end)
  4. ", "        (clause break)
  5. " "         (word break)
  6. ""          (character — last resort)
```

**Config parameters**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `chunk_size` | `800` | Max characters per chunk |
| `chunk_overlap` | `150` | Overlap between consecutive chunks |
| `separators` | see above | Override separator priority list |
| `keep_separator` | `true` | Append separator to chunk end |

**Why overlap?** Ensures context that spans chunk boundaries is not lost. A query
matching text that straddles two chunks will hit at least one of them.

### 3.3 SentenceChunker

Uses `nltk.sent_tokenize` (or `spacy` if installed) to split at sentence boundaries,
then aggregates sentences into chunks of approximately `chunk_size` tokens.

Best for: well-structured prose, legal documents, academic papers.

```python
class SentenceChunker(Chunker):
    def chunk(self, text, doc_metadata, chunk_size=600, chunk_overlap=1, **kwargs):
        # chunk_overlap here = number of overlapping sentences (not chars)
        sentences = nltk.sent_tokenize(text)
        # greedy pack sentences until chunk_size chars reached
        # slide window by (window_size - chunk_overlap) sentences
```

### 3.4 TokenChunker

Uses `tiktoken` to split on exact token counts. Useful when the embedding model has
a hard token limit (e.g., OpenAI `text-embedding-3-small` max 8191 tokens).

```python
class TokenChunker(Chunker):
    def chunk(self, text, doc_metadata, chunk_size=512, chunk_overlap=64, **kwargs):
        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(text)
        # slide window over token list
        # decode back to string for each window
```

### 3.5 Chunker Selection Logic

```python
# In IngestPipeline
def _select_chunker(source_type: str, options: IngestOptions) -> Chunker:
    if options.chunker:
        return get_chunker(options.chunker)  # explicit override
    # sensible defaults by source type:
    defaults = {
        "pdf":  "recursive",    # variable formatting
        "docx": "sentence",     # usually well-structured prose
        "md":   "recursive",    # header/paragraph structure
        "html": "recursive",
        "txt":  "sentence",
        "url":  "recursive",
    }
    return get_chunker(defaults.get(source_type, "recursive"))
```

---

## 4. Embedder

### 4.1 Embedder ABC

```python
class Embedder(ABC):
    model: str
    dimensions: int

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string (may use different prompt prefix)."""
```

### 4.2 OpenAIEmbedder

```python
class OpenAIEmbedder(Embedder):
    def __init__(self, model="text-embedding-3-small", dimensions=1536):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key,
                                  base_url=settings.openai_base_url)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Batch in groups of 100 (API limit)
        # Retry with exponential backoff on RateLimitError
        response = await self.client.embeddings.create(
            model=self.model, input=texts, dimensions=self.dimensions
        )
        return [d.embedding for d in response.data]
```

**Supported models**:
- `text-embedding-3-small` (1536 dims, default, cheapest)
- `text-embedding-3-large` (3072 dims, highest quality)
- `text-embedding-ada-002` (1536 dims, legacy)

### 4.3 OllamaEmbedder

```python
class OllamaEmbedder(Embedder):
    # Uses Ollama's /api/embeddings endpoint
    # model: "nomic-embed-text", "mxbai-embed-large", etc.
    # No batching limit (server-side sequential)
```

### 4.4 SentenceTransformerEmbedder

```python
class SentenceTransformerEmbedder(Embedder):
    # Local model via sentence-transformers library
    # Runs in a thread pool (CPU-bound)
    # model: "all-MiniLM-L6-v2", "BAAI/bge-m3", etc.
```

### 4.5 Batching Strategy

All embedders process in batches to respect API limits and optimize throughput:

```
chunks (N)
  │
  ▼ batch(size=100)
  [batch_0: chunks[0..99], batch_1: chunks[100..199], ...]
  │
  ▼ asyncio.gather(*[embed(batch) for batch in batches])
  │
  ▼ flatten → N vectors
```

---

## 5. IngestPipeline Orchestrator

```python
# rag_service/pipeline/ingest.py
class IngestPipeline:
    def __init__(
        self,
        parser: Parser,
        chunker: Chunker,
        embedder: Embedder,
        vector_store: VectorStore,
        bm25_index: BM25Index,
        graph_extractor: GraphExtractor | None = None,
    ):
        ...

    async def run(
        self,
        source: bytes | str,
        source_type: str,
        collection_id: str,
        document_id: str,
        metadata: dict,
        options: IngestOptions,
    ) -> IngestResult:
        # 1. Parse
        parse_result = await self.parser.parse(source)

        # 2. Chunk
        chunks = self.chunker.chunk(parse_result.text, {**parse_result.metadata, **metadata})

        # 3. Embed
        texts = [c.text for c in chunks]
        vectors = await self.embedder.embed(texts)

        # 4. Store in vector DB
        await self.vector_store.upsert(
            collection=collection_id,
            chunks=chunks,
            vectors=vectors,
        )

        # 5. Update BM25 index
        await self.bm25_index.add(collection_id, chunks)

        # 6. Optional: graph extraction
        if self.graph_extractor and options.enable_graph:
            relations = await self.graph_extractor.extract(parse_result.text)
            await self.graph_store.upsert(collection_id, relations)

        return IngestResult(
            document_id=document_id,
            chunk_count=len(chunks),
            status="success",
        )
```

---

## 6. IngestOptions Schema

```python
class IngestOptions(BaseModel):
    chunker: Literal["recursive", "sentence", "token"] | None = None
    chunk_size: int = 800
    chunk_overlap: int = 150
    enable_graph: bool = False
    tags: list[str] = []
    custom_metadata: dict = {}
```

---

## 7. Error Handling & Idempotency

### Idempotency
- Documents are identified by a **content hash** (SHA-256 of raw bytes/text).
- Re-ingesting the same file to the same collection is a no-op (returns existing
  `document_id` with `status: "already_exists"`).
- To force re-ingest, pass `force=true` in the request.

### Error States

| Stage | Error | Behavior |
|-------|-------|----------|
| Parse | Unsupported format | 400 Bad Request immediately |
| Parse | Corrupt / unreadable | 422 with `parse_error` detail |
| Chunk | Empty text after parse | 422 with `empty_document` detail |
| Embed | API rate limit | Retry 3× with backoff; 503 if all fail |
| Embed | Token limit exceeded | Auto-split chunk, re-embed |
| Vector store | Unavailable | 503, document marked `pending` |
| BM25 | Serialization error | Log + continue (non-fatal) |

### Partial failure recovery
If embedding/storage fails mid-batch, the pipeline records the failed chunk IDs
in the `Document.ingest_errors` column. A `POST /api/v1/documents/{id}/retry`
endpoint re-runs only the failed chunks.
