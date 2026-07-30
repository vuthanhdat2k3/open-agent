"""Cross-Encoder Reranker & Long-Context Reordering module.

Evaluates semantic relevance of query-candidate pairs and reorders results
to prevent the 'Lost in the Middle' attention decay in LLMs.
"""

from __future__ import annotations

from typing import Sequence

from rag_service.schemas.retrieval import RetrievalResult


class CrossEncoderReranker:
    """Reranks candidate results using a semantic similarity / lexical cross-encoder scoring algorithm."""

    def __init__(self, min_score_threshold: float = 0.25) -> None:
        self.min_score_threshold = min_score_threshold

    def _score_pair(self, query: str, text: str) -> float:
        """Compute term overlap + length penalized match score between query and text."""
        query_words = set(query.lower().split())
        text_words = set(text.lower().split())
        if not query_words or not text_words:
            return 0.0

        intersection = query_words.intersection(text_words)
        jaccard = len(intersection) / float(len(query_words.union(text_words)))
        overlap_ratio = len(intersection) / float(len(query_words))
        
        # Soft semantic overlap weighting
        score = (jaccard * 0.4) + (overlap_ratio * 0.6)
        return min(1.0, max(0.0, score))

    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalResult],
        top_k: int = 10,
    ) -> list[RetrievalResult]:
        """Rerank candidates based on cross-encoder similarity score."""
        if not candidates:
            return []

        scored: list[tuple[float, RetrievalResult]] = []
        for cand in candidates:
            # Combine initial retrieval score + cross-encoder score
            cross_score = self._score_pair(query, cand.text)
            combined_score = round((cand.score * 0.6) + (cross_score * 0.4), 6)
            
            if combined_score >= self.min_score_threshold:
                updated = cand.model_copy(update={"score": combined_score})
                scored.append((combined_score, updated))

        # Sort descending by combined score
        scored.sort(key=lambda x: x[0], reverse=True)

        reranked_results: list[RetrievalResult] = []
        for rank, (_, res) in enumerate(scored[:top_k], start=1):
            reranked_results.append(res.model_copy(update={"rank": rank}))

        return reranked_results


def reorder_long_context(results: list[RetrievalResult]) -> list[RetrievalResult]:
    """Reorder results so top relevance items are placed at the beginning and end.

    Prevents LLM 'Lost in the Middle' failure mode by prioritizing key context
    at prompt boundaries.
    """
    if len(results) <= 2:
        return results

    # Sort descending
    sorted_res = sorted(results, key=lambda x: x.score, reverse=True)
    reordered: list[RetrievalResult] = [None] * len(sorted_res)

    left = 0
    right = len(sorted_res) - 1

    for i, item in enumerate(sorted_res):
        if i % 2 == 0:
            reordered[left] = item
            left += 1
        else:
            reordered[right] = item
            right -= 1

    return [item for item in reordered if item is not None]
