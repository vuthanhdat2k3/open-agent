# RAG Service — Retrieval Engine

> Design of the **Hybrid BM25 + Semantic Search** retrieval system with
> **Reciprocal Rank Fusion (RRF)** and optional **LightRAG-style graph retrieval**.

---

## 1. Overview

The retrieval engine is the core value of the service. It combines two orthogonal
search signals and fuses them into a single ranked result list:

```
Query string
      │
      ├──────────────────────────────────────┐
      │                                      │
      ▼                                      ▼
BM25 Search                          Semantic Search
(keyword overlap,                    (dense embedding,
 TF-IDF style)                        cosine similarity)
      │                                      │
      │  [(chunk_id, bm25_score)]            │  [(chunk_id, cos_sim)]
      │                                      │
      └──────────────┬───────────────────────┘
                     │
                     ▼
              RRF Fusion (k=60)
              score = Σ 1/(k + rank_i)
                     │
                     ▼
          [Optional] Graph Expansion
                     │
                     ▼
           Top-N chunks + metadata
```

---

## 2. BM25 Search

### 2.1 Algorithm

BM25 (Best Match 25 / Okapi BM25) is a probabilistic retrieval model that scores
documents based on term frequency, inverse document frequency, and document length
normalization:

```
         N - df(t) + 0.5          tf(t,d) × (k1 + 1)
IDF(t) = log( ─────────────── )   TF(t,d) = ─────────────────────────
             df(t) + 0.5                    tf(t,d) + k1×(1-b+b×L/Lavg)

BM25(q,d) = Σ  IDF(t) × TF(t,d)
            t∈q
```

**Parameters** (BM25Okapi defaults):
- `k1 = 1.5` — term frequency saturation
- `b = 0.75` — document length normalization
- `epsilon = 0.25` — floor for IDF scores

### 2.2 BM25Index ABC

```python
# rag_service/retrieval/bm25/base.py
from abc import ABC, abstractmethod

class BM25Index(ABC):
    @abstractmethod
    async def add(self, collection_id: str, chunks: list[TextChunk]) -> None:
        """Add chunks to the index. Re-builds the model."""

    @abstractmethod
    async def remove(self, collection_id: str, chunk_ids: list[str]) -> None:
        """Remove chunks by ID. Re-builds the model."""

    @abstractmethod
    async def search(
        self, collection_id: str, query: str, top_k: int = 50
    ) -> list[tuple[str, float]]:
        """Return [(chunk_id, score)] sorted by score descending."""

    @abstractmethod
    async def save(self, collection_id: str) -> None:
        """Persist index state."""

    @abstractmethod
    async def load(self, collection_id: str) -> None:
        """Load persisted index state."""
```

### 2.3 InMemoryBM25

```python
# rag_service/retrieval/bm25/memory.py
import asyncio
from rank_bm25 import BM25Okapi
import pickle, pathlib

class InMemoryBM25(BM25Index):
    """
    Holds the BM25 index in memory.
    Persisted to disk as a pickle file on save().

    Layout:
      _indexes: dict[collection_id, {
          "model":    BM25Okapi,
          "chunk_ids": list[str],   # parallel to corpus rows
          "corpus":   list[list[str]],  # tokenized docs
      }]
    """

    def _tokenize(self, text: str) -> list[str]:
        # Lowercase, split on whitespace + punctuation
        # For multilingual: use simple whitespace split
        # Optional: integrate nltk stopwords removal
        return text.lower().split()

    async def add(self, collection_id, chunks):
        # Append new chunk tokens to corpus
        # Rebuild BM25Okapi model
        entry = self._indexes.setdefault(collection_id, {
            "chunk_ids": [], "corpus": []
        })
        for c in chunks:
            entry["chunk_ids"].append(c.chunk_id)
            entry["corpus"].append(self._tokenize(c.text))
        entry["model"] = BM25Okapi(entry["corpus"])

    async def search(self, collection_id, query, top_k=50):
        entry = self._indexes.get(collection_id)
        if not entry:
            return []
        tokens = self._tokenize(query)
        scores = entry["model"].get_scores(tokens)
        ranked = sorted(
            zip(entry["chunk_ids"], scores),
            key=lambda x: x[1], reverse=True
        )
        return ranked[:top_k]

    async def save(self, collection_id):
        path = settings.bm25_persist_dir / f"{collection_id}.pkl"
        with open(path, "wb") as f:
            pickle.dump(self._indexes[collection_id], f)

    async def load(self, collection_id):
        path = settings.bm25_persist_dir / f"{collection_id}.pkl"
        if path.exists():
            with open(path, "rb") as f:
                self._indexes[collection_id] = pickle.load(f)
```

### 2.4 RedisBM25

For multi-process or multi-instance deployments. Stores serialized BM25 model in
Redis with a collection-keyed hash. On search, deserializes into an in-memory model.

```python
class RedisBM25(BM25Index):
    # redis-py AsyncRedis client
    # Key schema: "bm25:{collection_id}:model" → pickle bytes
    #             "bm25:{collection_id}:ids"   → JSON list of chunk_ids
    # Note: model is rebuilt from corpus on load;
    #       Redis stores corpus + chunk_ids (not the BM25Okapi object directly)
```

### 2.5 Tokenization Notes

| Language | Tokenizer |
|----------|-----------|
| English | whitespace + punctuation strip |
| Vietnamese | `pyvi` or whitespace (Vietnamese is space-separated) |
| Chinese/Japanese | `jieba` / `fugashi` (optional dependency) |
| Multilingual | ICU word break (via `icu-tokenizer`, optional) |

The default tokenizer is **whitespace split** which works well for most Latin-script
and Vietnamese text. Set `RAG_BM25_TOKENIZER=pyvi` for Vietnamese-optimized results.

---

## 3. Semantic Search

### 3.1 VectorStore ABC

```python
# rag_service/retrieval/vector/base.py
from abc import ABC, abstractmethod

class VectorStore(ABC):
    @abstractmethod
    async def create_collection(self, name: str, dimensions: int) -> None: ...

    @abstractmethod
    async def upsert(
        self,
        collection: str,
        chunks: list[TextChunk],
        vectors: list[list[float]],
    ) -> None: ...

    @abstractmethod
    async def search(
        self,
        collection: str,
        query_vector: list[float],
        top_k: int = 50,
        filters: dict | None = None,
    ) -> list[tuple[str, float]]:
        """Return [(chunk_id, score)] sorted descending."""

    @abstractmethod
    async def delete(self, collection: str, chunk_ids: list[str]) -> None: ...

    @abstractmethod
    async def get_by_ids(
        self, collection: str, chunk_ids: list[str]
    ) -> list[TextChunk]: ...
```

### 3.2 QdrantStore (primary)

```python
# rag_service/retrieval/vector/qdrant.py
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
)

class QdrantStore(VectorStore):
    """
    Collection naming: Qdrant collection = "{rag_collection_id}"
    Point ID: UUID from TextChunk.chunk_id
    Payload stored per point:
      {
        "chunk_id":     str,
        "document_id":  str,
        "collection_id": str,
        "text":         str,        # full chunk text (for retrieval)
        "chunk_index":  int,
        "source_type":  str,
        "tags":         list[str],
        "created_at":   str (ISO),
        ... (all user metadata)
      }
    """

    async def create_collection(self, name, dimensions):
        await self.client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=dimensions,
                distance=Distance.COSINE,
                on_disk=True,          # memory-mapped for large collections
            ),
        )
        # Create payload indexes for fast filtering
        await self.client.create_payload_index(name, "document_id", "keyword")
        await self.client.create_payload_index(name, "tags", "keyword")
        await self.client.create_payload_index(name, "created_at", "datetime")

    async def search(self, collection, query_vector, top_k=50, filters=None):
        qdrant_filter = self._build_filter(filters) if filters else None
        results = await self.client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        )
        return [(r.payload["chunk_id"], r.score) for r in results]
```

### 3.3 ChromaStore (alternative)

Uses `chromadb` async client. Suitable for pure local use without Docker.

```python
class ChromaStore(VectorStore):
    # chroma collection per rag_collection_id
    # Metadata stored in Chroma's document metadata dict
    # Filtering via Chroma's $where syntax
```

---

## 4. Reciprocal Rank Fusion (RRF)

### 4.1 Algorithm

RRF combines multiple ranked lists into a single list without needing to normalize
scores across different systems.

```
For each item i across all ranked lists L₁, L₂, ..., Lₙ:

    RRF_score(i) = Σ   1 / (k + rank_L(i))
                  L∈lists

where:
  k    = 60  (smoothing constant, originally tuned on TREC data)
  rank = 1-based position in the ranked list (1 = best)
         If item not present in list L, it is skipped (contributes 0)
```

**Why k=60?** It de-emphasizes high-rank differences and gives good weight to
items appearing in the middle of lists. Empirically robust across many retrieval
tasks. The value 60 was established in Cormack et al. (2009).

### 4.2 Implementation

```python
# rag_service/retrieval/rrf.py

def reciprocal_rank_fusion(
    ranked_lists: list[list[tuple[str, float]]],
    k: int = 60,
    weights: list[float] | None = None,
) -> list[tuple[str, float]]:
    """
    Args:
        ranked_lists: Each list is [(chunk_id, score)] sorted descending.
                      Scores are ignored; only rank positions matter.
        k:            Smoothing constant (default 60).
        weights:      Optional per-list multipliers. If None, all lists
                      are weighted equally (weight=1.0).

    Returns:
        [(chunk_id, rrf_score)] sorted descending.
    """
    if weights is None:
        weights = [1.0] * len(ranked_lists)

    scores: dict[str, float] = {}

    for ranked_list, weight in zip(ranked_lists, weights):
        for rank, (chunk_id, _score) in enumerate(ranked_list, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (k + rank)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

### 4.3 Weighted RRF

By default, BM25 and semantic search are weighted equally (`[1.0, 1.0]`).
This can be tuned per-query or globally:

| Scenario | BM25 weight | Semantic weight |
|----------|-------------|-----------------|
| Default hybrid | 1.0 | 1.0 |
| Keyword-heavy query (code, names) | 1.5 | 0.5 |
| Conceptual query (meaning-based) | 0.5 | 1.5 |
| Auto-detect (future) | inferred from query classifier | |

Config: `RAG_RRF_BM25_WEIGHT`, `RAG_RRF_SEMANTIC_WEIGHT` (both default `1.0`).

---

## 5. HybridRetriever

```python
# rag_service/retrieval/engine.py

class HybridRetriever:
    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        bm25_index: BM25Index,
        graph_retriever: GraphRetriever | None = None,
        rrf_k: int = 60,
        bm25_weight: float = 1.0,
        semantic_weight: float = 1.0,
    ):
        ...

    async def search(
        self,
        query: str,
        collection_id: str,
        top_k: int = 10,
        candidate_k: int = 50,     # candidates per retriever before RRF
        filters: dict | None = None,
        enable_graph: bool = False,
    ) -> list[RetrievalResult]:
        """
        Full hybrid retrieval pipeline.
        candidate_k >> top_k to ensure good coverage before RRF.
        """
        # 1. Embed query
        query_vector = await self.embedder.embed_query(query)

        # 2. Run BM25 and semantic in parallel
        bm25_results, semantic_results = await asyncio.gather(
            self.bm25_index.search(collection_id, query, top_k=candidate_k),
            self.vector_store.search(collection_id, query_vector,
                                     top_k=candidate_k, filters=filters),
        )

        # 3. Optional: graph retrieval
        ranked_lists = [bm25_results, semantic_results]
        weights = [self.bm25_weight, self.semantic_weight]

        if enable_graph and self.graph_retriever:
            graph_results = await self.graph_retriever.search(
                query, collection_id, top_k=candidate_k
            )
            ranked_lists.append(graph_results)
            weights.append(1.0)

        # 4. RRF fusion
        fused = reciprocal_rank_fusion(ranked_lists, k=self.rrf_k, weights=weights)

        # 5. Fetch full chunk content for top-N
        top_ids = [chunk_id for chunk_id, _ in fused[:top_k]]
        chunks = await self.vector_store.get_by_ids(collection_id, top_ids)

        # 6. Build results with scores
        score_map = dict(fused)
        results = [
            RetrievalResult(
                chunk_id=c.chunk_id,
                text=c.text,
                score=score_map[c.chunk_id],
                metadata=c.metadata,
                document_id=c.metadata["document_id"],
                source_type=c.metadata.get("source_type", "unknown"),
            )
            for c in chunks
        ]
        return sorted(results, key=lambda r: r.score, reverse=True)
```

---

## 6. Graph Retrieval (LightRAG-style, optional)

### 6.1 Motivation

Pure vector/BM25 retrieval fails on **multi-hop** queries that require connecting
information across documents. The LightRAG approach builds a knowledge graph during
ingest and uses it during retrieval to expand context.

### 6.2 Entity & Relation Extraction

```python
# rag_service/retrieval/graph/extractor.py

class EntityRelationExtractor:
    """
    Uses an LLM to extract entities and relations from text.
    Prompt is adapted from LightRAG's extraction prompt.
    """

    EXTRACTION_PROMPT = """
    Given the following text, extract all entities (persons, organizations,
    concepts, locations, dates, technical terms) and the relations between them.

    Return JSON:
    {
      "entities": [{"id": "E1", "name": "...", "type": "...", "description": "..."}],
      "relations": [{"source": "E1", "target": "E2", "relation": "...", "weight": 1.0}]
    }

    Text:
    {text}
    """

    async def extract(self, text: str, chunk_id: str) -> GraphData:
        response = await self.llm_client.chat(
            [{"role": "user", "content": self.EXTRACTION_PROMPT.format(text=text)}],
            response_format={"type": "json_object"},
        )
        data = json.loads(response.content)
        return GraphData.from_dict(data, chunk_id=chunk_id)
```

### 6.3 GraphStore

```python
# rag_service/retrieval/graph/store.py

class NetworkXGraphStore(GraphStore):
    """
    In-memory graph using NetworkX DiGraph.
    Persisted to JSON/pickle on disk.
    Suitable for up to ~1M entities.
    """
    # Nodes: entity_id → {"name", "type", "description", "chunk_ids": [...]}
    # Edges: (source_id, target_id) → {"relation", "weight", "chunk_ids": [...]}

class Neo4jGraphStore(GraphStore):
    """
    Production-grade graph store using Neo4j.
    Enables Cypher queries for complex multi-hop traversal.
    """
```

### 6.4 Graph Retrieval Modes

Following LightRAG's retrieval modes:

| Mode | Description | Best for |
|------|-------------|----------|
| `local` | Find chunks directly containing query entities | Specific fact lookup |
| `global` | Traverse entity relations across chunks | Relationship questions |
| `hybrid` | local + global, RRF-fused | General knowledge queries |

```python
# rag_service/retrieval/graph/retriever.py

class GraphRetriever:
    async def search(
        self, query: str, collection_id: str,
        top_k: int = 20, mode: str = "hybrid"
    ) -> list[tuple[str, float]]:
        # 1. Extract query entities (fast NER or LLM)
        query_entities = await self._extract_query_entities(query)

        # 2. Local: find chunks containing those entities
        local_chunks = await self._local_search(query_entities, collection_id)

        # 3. Global: expand via entity relations (BFS depth 2)
        if mode in ("global", "hybrid"):
            related_entities = await self._expand_entities(query_entities, depth=2)
            global_chunks = await self._local_search(related_entities, collection_id)
        else:
            global_chunks = []

        # 4. Combine and score by entity match count + relation weight
        all_chunks = self._score_and_merge(local_chunks, global_chunks)
        return all_chunks[:top_k]
```

---

## 7. RetrievalResult Schema

```python
class RetrievalResult(BaseModel):
    chunk_id: str
    document_id: str
    text: str                  # the chunk content
    score: float               # RRF fusion score
    rank: int                  # 1-based position in final list
    source_type: str           # "pdf" | "docx" | "url" | "text" | ...
    metadata: dict             # full chunk metadata
    highlights: list[str] = [] # optional: matched terms (for BM25 path)
```

---

## 8. Query Preprocessing

Before passing the query to BM25 and the embedder:

```
1. Strip leading/trailing whitespace
2. Truncate to max 512 tokens (embedding model limit)
3. [Optional] Query expansion:
   - Synonym expansion via WordNet (English)
   - HyDE: embed a hypothetical answer document instead of the query
     (improves semantic recall for short queries)
```

HyDE (Hypothetical Document Embeddings) can be enabled via:
```
RAG_QUERY_HYDE=true
RAG_QUERY_HYDE_MODEL=gpt-4o-mini   # model to generate hypothetical doc
```

---

## 9. Performance Characteristics

| Operation | Typical latency | Notes |
|-----------|-----------------|-------|
| BM25 search (10K docs) | < 5ms | In-memory, no I/O |
| BM25 search (1M docs) | < 50ms | Still in-memory |
| Semantic search (Qdrant HNSW) | 5–20ms | Network + HNSW |
| RRF fusion (100 candidates) | < 1ms | Pure Python dict ops |
| Embedding (OpenAI API) | 50–200ms | Network-bound |
| **Total hybrid search** | **~100–300ms** | Dominated by embed call |
| Graph search (NetworkX) | 10–100ms | Depends on graph size |

**Caching**: Query embedding results are cached in-memory (LRU, 1000 entries) to
avoid redundant API calls for repeated queries.
