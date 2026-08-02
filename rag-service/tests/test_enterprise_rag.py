"""Unit tests for Enterprise RAG components: Semantic/Parent-Child Chunking, Reranking, and Query Optimization."""

from __future__ import annotations


from rag_service.pipeline.chunker.parent_child import ParentChildChunker
from rag_service.pipeline.chunker.semantic import SemanticChunker
from rag_service.retrieval.query import QueryOptimizer
from rag_service.retrieval.reranker import CrossEncoderReranker, reorder_long_context
from rag_service.schemas.retrieval import RetrievalResult


def test_semantic_chunker():
    chunker = SemanticChunker(chunk_size=100, chunk_overlap=20, enable_context_header=True)
    text = "Paragraph 1: Enterprise RAG Architecture.\n\nParagraph 2: Deep Dive into Hybrid Search and Reranking."
    meta = {"source_name": "architecture.pdf"}

    chunks = chunker.chunk(text, meta)
    assert len(chunks) >= 1
    assert "[Context: Document architecture.pdf]" in chunks[0].text
    assert chunks[0].metadata.get("is_semantic") is True


def test_parent_child_chunker():
    chunker = ParentChildChunker(parent_chunk_size=300, child_chunk_size=60)
    text = (
        "OpenAgent Enterprise RAG System incorporates parent-child hierarchical chunking. "
        "The parent chunk holds full section context while child chunks target fine-grained vector retrieval."
    )
    meta = {"document_id": "doc_123"}

    children = chunker.chunk(text, meta)
    assert len(children) >= 1
    assert "parent_id" in children[0].metadata
    assert "parent_text" in children[0].metadata
    assert children[0].metadata.get("is_child") is True


def test_cross_encoder_reranker_and_reordering():
    reranker = CrossEncoderReranker(min_score_threshold=0.1)

    query = "Enterprise RAG Reranking"
    cand1 = RetrievalResult(
        chunk_id="c1",
        document_id="d1",
        text="Random unrelated recipe content about apple pie.",
        score=0.9,
        rank=1,
        source_type="text",
    )
    cand2 = RetrievalResult(
        chunk_id="c2",
        document_id="d2",
        text="Enterprise RAG Reranking optimizes semantic relevance score.",
        score=0.8,
        rank=2,
        source_type="text",
    )

    reranked = reranker.rerank(query, [cand1, cand2], top_k=2)
    assert len(reranked) >= 1
    assert reranked[0].chunk_id == "c2"

    reordered = reorder_long_context(reranked)
    assert len(reordered) == len(reranked)


def test_query_optimizer():
    query = "Compare Q1 revenue and Q2 revenue"
    decomp = QueryOptimizer.decompose_query(query)
    assert len(decomp) >= 2

    prompt = QueryOptimizer.generate_hyde_prompt("What is hybrid search?")
    assert "What is hybrid search?" in prompt
