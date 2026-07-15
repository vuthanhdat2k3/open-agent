"""Backend factory — resolves configured backends with safe fallbacks.

The service is built so it **always boots**, even with zero external services.
Each builder tries the configured backend and, on any failure, transparently
falls back to a zero-dependency in-process implementation:

* vector store : Qdrant / Chroma  -> in-memory numpy
* embedder     : OpenAI / Ollama / sentence-transformers -> local hashing
* BM25         : Redis -> in-memory rank_bm25
* graph        : NetworkX / Neo4j -> disabled (None)

Swap to production backends via env vars (see ``configuration.md``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rag_service.config import settings
from rag_service.core.logging import logger
from rag_service.exceptions import UnsupportedFormatError
from rag_service.pipeline.base import Chunker, Embedder, Parser
from rag_service.retrieval.bm25.base import BM25Index
from rag_service.retrieval.bm25.memory import InMemoryBM25
from rag_service.retrieval.engine import HybridRetriever
from rag_service.retrieval.vector.base import VectorStore
from rag_service.retrieval.vector.memory import MemoryVectorStore


@dataclass
class RAGComponents:
    embedder: Embedder
    vector_store: VectorStore
    bm25_index: BM25Index
    retriever: HybridRetriever
    graph_retriever: Any | None = None
    _loaded: bool = field(default=False, repr=False)


# --------------------------------------------------------------------------- #
# Vector store
# --------------------------------------------------------------------------- #
def build_vector_store() -> VectorStore:
    kind = settings.vector_store
    if kind == "qdrant":
        try:
            from rag_service.retrieval.vector.qdrant import QdrantStore

            return QdrantStore()
        except Exception as exc:  # pragma: no cover - optional backend
            logger.warning("vector_store_qdrant_unavailable", error=str(exc))
    elif kind == "chroma":
        try:
            from rag_service.retrieval.vector.chroma import ChromaStore

            return ChromaStore()
        except Exception as exc:  # pragma: no cover - optional backend
            logger.warning("vector_store_chroma_unavailable", error=str(exc))
    return MemoryVectorStore()


# --------------------------------------------------------------------------- #
# Embedder
# --------------------------------------------------------------------------- #
import hashlib
import math

import numpy as np


class _FallbackEmbedder(Embedder):
    """Zero-dependency deterministic embedder (hashed bag-of-words, L2-normalized).

    Used only when no real embedding backend is available. Provides *lexical*
    similarity good enough for the in-memory demo; pair with OpenAI / a local
    model for true semantic quality. Always importable -> service never fails to boot.
    """

    model = "fallback-hash"
    dimensions = 512

    _STOP = set(
        "the a an and or of to in is are was were be been being for on at by with "
        "as it this that these those from we you they he she but not no yes if then "
        "so than into out up down over under again further once here there all any "
        "both each few more most other some such only own same can will just should now"
        .split()
    )

    def _vector(self, text: str) -> list[float]:
        vec = np.zeros(self.dimensions, dtype=np.float32)
        toks = [t for t in text.lower().split() if t and t not in self._STOP]
        if not toks:
            return vec.tolist()
        for tok in toks:
            h = int.from_bytes(
                hashlib.md5(tok.encode("utf-8", "ignore")).digest()[:8], "big"
            )
            idx = h % self.dimensions
            vec[idx] += 1.0
        norm = math.sqrt(float(np.dot(vec, vec))) or 1.0
        return (vec / norm).tolist()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


def _fallback_embedder() -> Embedder:
    return _FallbackEmbedder()


def build_embedder() -> Embedder:
    kind = settings.embedder
    if kind == "openai":
        # Without a usable key the OpenAI client constructs fine but fails at
        # request time (401). Detect that up front and fall back to the
        # zero-dependency embedder so the service always boots + serves.
        if not settings.openai_key_effective:
            logger.warning(
                "embedder_openai_no_key",
                detail="RAG_OPENAI_API_KEY/OPENAI_API_KEY not set; using fallback embedder",
            )
            return _fallback_embedder()
        try:
            from rag_service.pipeline.embedder.openai import OpenAIEmbedder

            e = OpenAIEmbedder()
            logger.info("embedder_openai_ready", model=e.model)
            return e
        except Exception as exc:
            logger.warning("embedder_openai_unavailable", error=str(exc))
    elif kind == "ollama":
        try:
            from rag_service.pipeline.embedder.ollama import OllamaEmbedder

            return OllamaEmbedder()
        except Exception as exc:
            logger.warning("embedder_ollama_unavailable", error=str(exc))
    elif kind == "sentence_transformers":
        try:
            from rag_service.pipeline.embedder.sentence_transformers import (
                SentenceTransformerEmbedder,
            )

            return SentenceTransformerEmbedder()
        except Exception as exc:
            logger.warning("embedder_st_unavailable", error=str(exc))
    elif kind == "simple":
        return _fallback_embedder()
    return _fallback_embedder()


# --------------------------------------------------------------------------- #
# BM25
# --------------------------------------------------------------------------- #
def build_bm25() -> BM25Index:
    kind = settings.bm25_backend
    if kind == "redis":
        try:
            from rag_service.retrieval.bm25.redis import RedisBM25

            return RedisBM25()
        except Exception as exc:  # pragma: no cover - optional backend
            logger.warning("bm25_redis_unavailable", error=str(exc))
    return InMemoryBM25()


# --------------------------------------------------------------------------- #
# Graph (optional)
# --------------------------------------------------------------------------- #
def build_graph_retriever() -> Any | None:
    if not settings.enable_graph:
        return None
    try:
        from rag_service.retrieval.graph.retriever import GraphRetriever

        return GraphRetriever()
    except Exception as exc:  # pragma: no cover - optional backend
        logger.warning("graph_unavailable", error=str(exc))
        return None


# --------------------------------------------------------------------------- #
# Parser / Chunker resolvers
# --------------------------------------------------------------------------- #
def resolve_parser(source_type: str) -> Parser:
    try:
        from rag_service.pipeline.parser import get_parser

        return get_parser(source_type)
    except UnsupportedFormatError:
        raise
    except Exception as exc:
        raise UnsupportedFormatError(source_type) from exc


def resolve_chunker(
    name: str | None, chunk_size: int, chunk_overlap: int
) -> Chunker:
    from rag_service.pipeline.chunker import get_chunker

    return get_chunker(name, chunk_size, chunk_overlap)


# --------------------------------------------------------------------------- #
# Top-level assembly
# --------------------------------------------------------------------------- #
def build_components() -> RAGComponents:
    embedder = build_embedder()
    vector_store = build_vector_store()
    bm25 = build_bm25()
    graph = build_graph_retriever()
    retriever = HybridRetriever(
        embedder=embedder,
        vector_store=vector_store,
        bm25_index=bm25,
        graph_retriever=graph,
    )
    return RAGComponents(
        embedder=embedder,
        vector_store=vector_store,
        bm25_index=bm25,
        retriever=retriever,
        graph_retriever=graph,
    )
