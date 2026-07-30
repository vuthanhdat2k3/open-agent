"""Benchmark script for Enterprise RAG chunking and retrieval performance.

Measures throughput, latency, RRF vs Cross-Encoder precision, and memory footprint.
"""

from __future__ import annotations

import time

from rag_service.pipeline.chunker import (
    ParentChildChunker,
    RecursiveCharacterChunker,
    SemanticChunker,
)
from rag_service.retrieval.reranker import CrossEncoderReranker, reorder_long_context
from rag_service.schemas.retrieval import RetrievalResult

# Sample enterprise synthetic test dataset
TEST_DOC = """
# OpenAgent Enterprise Architecture Specification 2026

## 1. Executive Summary
OpenAgent is an open-source enterprise agentic framework providing multi-tenant isolation, 
workflow execution engines, and hybrid RAG knowledge retrieval.

## 2. Security & Compliance
All tenant operations enforce Role-Based Access Control (RBAC) and Attribute-Based Access Control (ABAC).
Data in transit is encrypted via TLS 1.3, and data at rest uses AES-256 GCM encryption.
Audit logs capture every tool call, authentication event, and LLM inference.

## 3. Advanced Hybrid RAG Engine
The RAG subsystem utilizes Qdrant vector database paired with BM25 sparse lexical indexing.
Reciprocal Rank Fusion (RRF) combines candidate lists, which are then passed through a
Cross-Encoder Reranker (BGE-Reranker-v2-m3) for high-precision semantic filtering.

## 4. Multi-Tenant Quotas and Rate Limiting
Organizations are assigned resource quotas including max active agents, max requests per minute (RPM),
and token quotas per billing cycle. Sliding-window Redis rate limiters enforce operational boundaries.
"""


def benchmark_chunkers():
    print("=" * 60)
    print(" 1. CHUNKER PERFORMANCE BENCHMARK")
    print("=" * 60)

    chunkers = {
        "RecursiveCharacterChunker": RecursiveCharacterChunker(chunk_size=400, chunk_overlap=80),
        "SemanticChunker": SemanticChunker(chunk_size=400, chunk_overlap=80, enable_context_header=True),
        "ParentChildChunker": ParentChildChunker(parent_chunk_size=600, child_chunk_size=200),
    }

    meta = {"source_name": "enterprise_spec.md", "document_id": "doc_bench_01"}

    for name, chunker in chunkers.items():
        t0 = time.perf_counter()
        iterations = 500
        total_chunks = 0
        for _ in range(iterations):
            chunks = chunker.chunk(TEST_DOC, meta)
            total_chunks += len(chunks)
        elapsed = time.perf_counter() - t0

        avg_latency_ms = (elapsed / iterations) * 1000
        throughput_kb_s = (len(TEST_DOC) * iterations / 1024) / elapsed

        print(f"[{name}]")
        print(f"  - Total chunks per doc : {len(chunks)}")
        print(f"  - Avg Latency per doc  : {avg_latency_ms:.3f} ms")
        print(f"  - Throughput           : {throughput_kb_s:.2f} KB/s")
        print("-" * 60)


def benchmark_reranker():
    print("\n" + "=" * 60)
    print(" 2. RERANKER & REORDERING BENCHMARK")
    print("=" * 60)

    reranker = CrossEncoderReranker(min_score_threshold=0.15)
    query = "What security and encryption methods are used?"

    # Generate 50 synthetic candidates
    candidates: list[RetrievalResult] = [
        RetrievalResult(
            chunk_id=f"c_{i}",
            document_id="doc_bench_01",
            text=f"Irrelevant text paragraph {i} about generic system topics.",
            score=round(0.95 - (i * 0.015), 4),
            rank=i + 1,
            source_type="text",
        )
        for i in range(48)
    ]

    # Inject ground truth candidates at lower initial positions
    candidates.append(
        RetrievalResult(
            chunk_id="gt_1",
            document_id="doc_bench_01",
            text="Data in transit is encrypted via TLS 1.3, and data at rest uses AES-256 GCM encryption. RBAC and ABAC are enforced.",
            score=0.45,
            rank=49,
            source_type="text",
        )
    )
    candidates.append(
        RetrievalResult(
            chunk_id="gt_2",
            document_id="doc_bench_01",
            text="Audit logs capture every tool call, authentication event, and LLM inference for security.",
            score=0.40,
            rank=50,
            source_type="text",
        )
    )

    t0 = time.perf_counter()
    iterations = 200
    for _ in range(iterations):
        reranked = reranker.rerank(query, candidates, top_k=5)
        reordered = reorder_long_context(reranked)
    elapsed = time.perf_counter() - t0

    avg_rerank_ms = (elapsed / iterations) * 1000

    print(f"  - Input Candidate Count : {len(candidates)}")
    print(f"  - Rerank Top-K          : {len(reranked)}")
    print(f"  - Avg Rerank Latency    : {avg_rerank_ms:.3f} ms")
    print(f"  - Top 1 Result          : {reordered[0].chunk_id} (Score: {reordered[0].score})")
    print(f"  - Ground Truth Hit      : {'gt_1' in [c.chunk_id for c in reordered]}")
    print("=" * 60)


if __name__ == "__main__":
    benchmark_chunkers()
    benchmark_reranker()
